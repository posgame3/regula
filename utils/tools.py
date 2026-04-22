import os
import uuid
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOLS_TPL_DIR = os.path.join(BASE_DIR, "templates", "tools")


def _render_pdf(template_name: str, context: dict, tool_name: str) -> str:
    env = Environment(
        loader=FileSystemLoader(_TOOLS_TPL_DIR),
        autoescape=select_autoescape(["html"]),
    )
    html_content = env.get_template(template_name).render(**context)
    session_id = context.get("session_id", uuid.uuid4().hex[:8])
    path = f"/tmp/regula_{session_id}_{tool_name}.pdf"
    HTML(string=html_content, base_url=BASE_DIR).write_pdf(path)
    return path


def generate_security_policy(session_data: dict) -> str:
    context = {
        "company_name": session_data.get("company_name", ""),
        "sector": session_data.get("sector", ""),
        "gaps": session_data.get("gaps", []),
        "priority_actions": session_data.get("priority_actions", []),
        "language": session_data.get("language", "pl"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "session_id": session_data.get("session_id", uuid.uuid4().hex[:8]),
    }
    return _render_pdf("policy.html", context, "policy")


def generate_incident_plan(session_data: dict) -> str:
    context = {
        "company_name": session_data.get("company_name", ""),
        "it_contact": session_data.get("it_contact", ""),
        "sector": session_data.get("sector", ""),
        "gaps": session_data.get("gaps", []),
        "language": session_data.get("language", "pl"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "session_id": session_data.get("session_id", uuid.uuid4().hex[:8]),
    }
    return _render_pdf("incident.html", context, "incident")


def generate_remediation_checklist(session_data: dict) -> str:
    context = {
        "company_name": session_data.get("company_name", ""),
        "sector": session_data.get("sector", ""),
        "gaps": session_data.get("gaps", []),
        "priority_actions": session_data.get("priority_actions", []),
        "language": session_data.get("language", "pl"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "session_id": session_data.get("session_id", uuid.uuid4().hex[:8]),
    }
    return _render_pdf("checklist.html", context, "checklist")
