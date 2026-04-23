import json
import logging
import os
import re
from datetime import datetime

import markdown as md_lib
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NIS2_PATH = os.path.join(BASE_DIR, "data", "frameworks", "nis2.json")
log = logging.getLogger(__name__)


def _load_nis2() -> dict:
    """Load the framework index once — cheap, file is ~15 KB."""
    try:
        with open(_NIS2_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"requirements": [], "directive_url": "", "directive": ""}


def _strip_code_fences(text: str) -> str:
    return '\n'.join(
        line for line in text.split('\n')
        if not re.match(r'^\s*```\w*\s*$', line)
    )


def generate_report_pdf(session_data: dict, language: str) -> bytes:
    try:
        env = Environment(
            loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")),
            autoescape=select_autoescape(["html"]),
        )
        template = env.get_template("report.html")
        redteam_result = session_data.get("redteam_result")
        redteam_html = None
        if isinstance(redteam_result, str):
            redteam_result = _strip_code_fences(redteam_result)
            redteam_html = md_lib.markdown(redteam_result, extensions=["tables"])

        if session_data.get("gap_analysis") and session_data["gap_analysis"].get("gaps"):
            for gap in session_data["gap_analysis"]["gaps"]:
                cost = gap.get("estimated_cost") or ""
                if cost and len(cost) > 30:
                    match = re.search(r'[\d\s][\d\s]*[–\-][\d\s]*[\d\s]*EUR', cost)
                    gap["cost_short"] = match.group(0).strip() if match else cost[:25]
                else:
                    gap["cost_short"] = cost or "—"

        nis2 = _load_nis2()
        html_content = template.render(
            session=session_data,
            language=language,
            date=datetime.now().strftime("%Y-%m-%d"),
            redteam_html=redteam_html,
            nis2_requirements=nis2.get("requirements", []),
            nis2_directive_url=nis2.get("directive_url", "https://eur-lex.europa.eu/eli/dir/2022/2555/oj"),
        )
        return HTML(string=html_content, base_url=BASE_DIR).write_pdf()
    except Exception as e:
        log.error("PDF generation failed: %s", e, exc_info=True)
        raise
