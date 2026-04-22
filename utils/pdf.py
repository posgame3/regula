import os
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def generate_report_pdf(session_data: dict, language: str) -> bytes:
    env = Environment(
        loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("report.html")
    html_content = template.render(
        session=session_data,
        language=language,
        date=datetime.now().strftime("%Y-%m-%d"),
    )
    return HTML(string=html_content, base_url=BASE_DIR).write_pdf()
