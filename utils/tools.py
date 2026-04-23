import asyncio
import os
import urllib.parse
import uuid
from datetime import datetime

import requests
from bs4 import BeautifulSoup
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


_FALLBACK_RESOURCES = {
    "pl": [
        {
            "title": "ENISA SME Guide — Bezpieczeństwo IT dla MŚP",
            "url": "https://www.enisa.europa.eu/topics/cybersecurity-education/awareness-raising/cyber-security-month/2021-campaign/sme-quiz",
            "description": "Przewodnik ENISA dla małych i średnich przedsiębiorstw",
        },
        {
            "title": "CERT Polska — Materiały szkoleniowe",
            "url": "https://cert.pl/materialy/",
            "description": "Materiały edukacyjne i ostrzeżenia CERT Polska",
        },
        {
            "title": "ENISA — Narzędzie samooceny NIS2",
            "url": "https://www.enisa.europa.eu/topics/nis-directive",
            "description": "Oficjalne zasoby ENISA dotyczące dyrektywy NIS2",
        },
    ],
    "en": [
        {
            "title": "ENISA NIS2 Directive Resources",
            "url": "https://www.enisa.europa.eu/topics/nis-directive",
            "description": "Official ENISA resources for NIS2 compliance",
        },
        {
            "title": "ENISA Guidelines on Cybersecurity Measures",
            "url": "https://www.enisa.europa.eu/publications",
            "description": "Practical ENISA publications on cybersecurity good practices",
        },
        {
            "title": "ENISA Cybersecurity Guide for SMEs",
            "url": "https://www.enisa.europa.eu/publications/enisa-cybersecurity-guide-for-smes",
            "description": "Step-by-step cybersecurity guide tailored for small businesses",
        },
    ],
}


def _scrape_ddg(query: str, language: str) -> list:
    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    resp = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Regula/1.0)"},
        timeout=8,
    )
    if resp.status_code != 200:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    results = []
    for link in soup.select(".result__a")[:6]:
        href = link.get("href", "")
        if "uddg=" in href:
            href = urllib.parse.unquote(href.split("uddg=")[-1].split("&")[0])
        title = link.get_text(strip=True)
        parent = link.find_parent(class_="result__body") or link.find_parent()
        snippet_el = parent.find(class_="result__snippet") if parent else None
        description = snippet_el.get_text(strip=True) if snippet_el else ""

        target_domains = ("enisa.europa.eu", "cert.pl") if language == "pl" else ("enisa.europa.eu",)
        if href and any(d in href for d in target_domains):
            results.append({"title": title, "url": href, "description": description})
            if len(results) >= 2:
                break
    return results


async def search_enisa_guidance(gaps: list, sector: str, language: str) -> list:
    """Search for real ENISA/CERT resources for the company's specific gaps."""
    queries = []
    for gap in gaps[:3]:
        article = gap.get("article_ref", "") or gap.get("article", "") if isinstance(gap, dict) else str(gap)
        if language == "pl":
            queries.append(f"ENISA NIS2 {article} {sector} szablon site:enisa.europa.eu OR site:cert.pl")
        else:
            queries.append(f"ENISA NIS2 {article} {sector} template site:enisa.europa.eu")

    results = []
    seen_urls: set = set()

    for query in queries:
        try:
            hits = await asyncio.to_thread(_scrape_ddg, query, language)
            for hit in hits:
                if hit["url"] not in seen_urls:
                    seen_urls.add(hit["url"])
                    results.append(hit)
        except Exception:
            continue

    return results if results else _FALLBACK_RESOURCES.get(language, _FALLBACK_RESOURCES["en"])


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
