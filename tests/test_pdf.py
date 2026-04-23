"""End-to-end PDF generation smoke test.

Why: the PDF is the primary demo artifact. WeasyPrint + Jinja2 + font embedding
is the kind of thing that silently breaks (missing font file, template typo,
new field unused) and we only find out when a judge clicks Download.

Coverage: render the report for a realistic finished-session payload in both
PL and EN, assert that a non-trivial PDF comes back.
"""
from __future__ import annotations

from utils.pdf import generate_report_pdf


def _fake_session() -> dict:
    return {
        "session_id": "testsess",
        "language": "en",
        "stage": "complete",
        "qualifier_result": {
            "applies": True,
            "scope": "important",
            "confidence": "high",
            "reasoning": "Transport / road freight, 80 employees, active in Poland.",
        },
        "interview_findings": {
            "company_name": "Test Transport Sp. z o.o.",
            "sector": "transport",
            "employee_count": 80,
            "scope": "important",
            "language": "en",
            "key_quotes": [
                "We don't have written security policies",
                "Backups set up a year ago, never tested",
            ],
            "biggest_concern": "No incident response plan and untested backups.",
        },
        "gap_analysis": {
            "overall_risk": "high",
            "headline": "4 critical gaps require immediate action.",
            "gaps": [
                {
                    "id": 1,
                    "article_ref": "Art. 21(2)(b) — Incident handling",
                    "requirement": "Incident response plan",
                    "status": "missing",
                    "risk_level": "critical",
                    "what_we_found": "No written plan.",
                    "why_it_matters": "Regulators will flag this immediately.",
                    "what_to_do": "Draft a one-page plan this week.",
                    "estimated_effort": "2 weeks",
                    "estimated_cost": "€0–2,000",
                },
                {
                    "id": 2,
                    "article_ref": "Art. 21(2)(j) — Multi-factor authentication",
                    "requirement": "MFA on admin accounts",
                    "status": "missing",
                    "risk_level": "critical",
                    "what_we_found": "Passwords only.",
                    "why_it_matters": "One stolen password gives full access.",
                    "what_to_do": "Turn on MFA in Microsoft 365 this afternoon.",
                    "estimated_effort": "1 day",
                    "estimated_cost": "€0",
                },
            ],
            "priority_3": [
                "Enable MFA across all business accounts (Art. 21(2)(j)).",
                "Write a one-page incident response plan (Art. 21(2)(b)).",
                "Test a backup restore this month (Art. 21(2)(c)).",
            ],
            "good_news": "Contracts and an external IT contractor in place.",
            "board_summary": "4 critical gaps. Immediate action needed.",
        },
        "redteam_result": {
            "verdict": {
                "verdict": "WOULD FAIL AUDIT",
                "auditor_summary": "Three critical Art. 21(2) failures. Fine exposure up to €7M.",
                "critical_failures": [
                    "Art. 21(2)(b) — no incident response plan.",
                    "Art. 21(2)(j) — no MFA on privileged accounts.",
                ],
                "passed_checks": [],
            },
            "preparation": "1. Enable MFA. 2. Draft IR plan. 3. Test backup.",
        },
        "drafter_result": {
            "policies": [
                {
                    "title": "Incident Response Policy",
                    "who_owns_this": "IT contractor + CEO",
                    "review_date": "annually",
                    "effort": "2 weeks",
                    "cost": "Low",
                    "why_we_have_this": "Required by Art. 21(2)(b).",
                    "rules": ["Report incidents within 24 hours.", "Keep incident log."],
                },
            ],
        },
        "threat_actor_result": {
            "scenarios": [
                {
                    "title": "Ransomware via phishing",
                    "attack_vector": "Email phishing",
                    "how_it_starts": "Driver opens fake invoice PDF.",
                    "what_happens": "Files encrypted.",
                    "business_impact": "2–3 days downtime.",
                    "likelihood": "high",
                }
            ],
            "summary": "Phishing + no training = realistic attack path.",
        },
        "board_slides": {
            "slides": [
                {"number": 1, "title": "Status", "key_message": "4 critical gaps"},
                {"number": 2, "title": "Score", "score": 34},
            ],
        },
    }


def _assert_valid_pdf(pdf_bytes: bytes) -> None:
    assert isinstance(pdf_bytes, bytes), f"expected bytes, got {type(pdf_bytes)}"
    assert pdf_bytes.startswith(b"%PDF"), "output is not a PDF (missing %PDF header)"
    # Should be well over 10 KB — anything smaller means sections didn't render.
    assert len(pdf_bytes) > 20_000, f"PDF suspiciously small: {len(pdf_bytes)} bytes"


def test_pdf_generates_english():
    pdf = generate_report_pdf(_fake_session(), "en")
    _assert_valid_pdf(pdf)


def test_pdf_generates_polish():
    session = _fake_session()
    session["language"] = "pl"
    pdf = generate_report_pdf(session, "pl")
    _assert_valid_pdf(pdf)


def test_pdf_includes_legal_basis_appendix():
    """The Art. 21(2) appendix should be injected by generate_report_pdf via nis2.json."""
    import io
    from pypdf import PdfReader

    pdf_bytes = generate_report_pdf(_fake_session(), "en")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    all_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "eur-lex.europa.eu" in all_text, (
        "EUR-Lex URL missing from rendered PDF — legal-basis appendix did not render"
    )
    # Every one of the 10 Art. 21(2) sub-paragraphs must appear in the appendix table.
    for letter in "abcdefghij":
        assert f"Art. 21(2)({letter})" in all_text, (
            f"Art. 21(2)({letter}) missing from PDF — appendix table incomplete"
        )
