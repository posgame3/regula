import os
from datetime import datetime

import markdown as md_lib
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def generate_report_pdf(session_data: dict, language: str) -> bytes:
    env = Environment(
        loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("report.html")
    redteam_result = session_data.get("redteam_result")
    redteam_html = None
    if isinstance(redteam_result, str):
        redteam_html = md_lib.markdown(redteam_result, extensions=["tables"])

    html_content = template.render(
        session=session_data,
        language=language,
        date=datetime.now().strftime("%Y-%m-%d"),
        redteam_html=redteam_html,
    )
    return HTML(string=html_content, base_url=BASE_DIR).write_pdf()
