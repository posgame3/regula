import os
import re
from datetime import datetime

import markdown as md_lib
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

        html_content = template.render(
            session=session_data,
            language=language,
            date=datetime.now().strftime("%Y-%m-%d"),
            redteam_html=redteam_html,
        )
        return HTML(string=html_content, base_url=BASE_DIR).write_pdf()
    except Exception as e:
        print(f"[pdf] ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise
