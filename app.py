import asyncio
import json
import logging
import logging.handlers
import os
import re
from pathlib import Path

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

load_dotenv()


# ────────────────────────── Logging ──────────────────────────
# File + stderr, structured format, rotating. Replaces the earlier print()-only
# approach so post-mortem debugging of a demo is possible.
def _configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if getattr(root, "_regula_configured", False):
        return
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stderr = logging.StreamHandler()
    stderr.setFormatter(fmt)
    root.addHandler(stderr)

    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, "regula.log"),
            maxBytes=1_000_000, backupCount=3, encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:
        # Read-only FS (e.g. some container setups) — stderr-only is fine.
        pass

    # Quiet down the very chatty libraries by default.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    logging.getLogger("weasyprint").setLevel(logging.WARNING)

    root._regula_configured = True  # type: ignore[attr-defined]


_configure_logging()
log = logging.getLogger("regula")

from agents.qualifier import build_qualifier_system
from agents.interviewer import build_interview_system
from agents.analyzer import build_analyzer_system
from agents.redteam import build_redteam_system
from agents.redteam_managed import run_managed_audit
from agents.monitor_managed import run_managed_monitor
from agents.drafter import build_drafter_system
from agents.threat_actor import build_threat_actor_system
from agents.board_presenter import build_board_presenter_system
from utils import benchmark, profile_store, session_store
from utils.pdf import generate_report_pdf
from utils.tools import generate_security_policy, generate_incident_plan, generate_remediation_checklist, search_enisa_guidance

app = FastAPI()
TEST_MODE = bool(os.getenv("TEST_MODE"))
MODEL = "claude-sonnet-4-6" if TEST_MODE else "claude-opus-4-7"
COMPLETE_MARKER = "[INTERVIEW_COMPLETE]"
MOCK_MODE = bool(os.getenv("MOCK_MODE"))

# Managed Agents — feature-flagged. Enabled when MANAGED_AGENTS=1 AND the IDs
# were written by scripts/setup_managed_agents.py. Falls back silently to the
# legacy in-process flow (kept intact for MOCK_MODE demo + reliability).
MANAGED_AGENTS = bool(os.getenv("MANAGED_AGENTS")) and not MOCK_MODE
MANAGED_ENV_ID = os.getenv("MANAGED_ENV_ID")
REDTEAM_AGENT_ID = os.getenv("REDTEAM_AGENT_ID")
MONITOR_AGENT_ID = os.getenv("MONITOR_AGENT_ID")
REDTEAM_MANAGED_READY = bool(MANAGED_AGENTS and MANAGED_ENV_ID and REDTEAM_AGENT_ID)
MONITOR_MANAGED_READY = bool(MANAGED_ENV_ID and MONITOR_AGENT_ID)  # monitor is user-triggered, works even if MANAGED_AGENTS flag off

sessions: dict = {}

# Input-sanitization limits. Generous enough that real answers never trip them,
# tight enough that a malicious user can't flood the model context or the db.
MAX_USER_MESSAGE_CHARS = 1500         # typical interview answer is <200 chars
MAX_USER_MESSAGES_PER_SESSION = 80    # pipeline never needs more than ~30


def _sanitize_user_text(raw: str) -> str:
    """Trim length, strip control chars / zero-width tricks, return clean text.
    Returns '' if nothing usable is left — caller should treat that as 'ignore'."""
    if not raw:
        return ""
    # Drop C0 control chars except \n \r \t; drop zero-width + BOM.
    cleaned_chars: list[str] = []
    for ch in raw:
        cp = ord(ch)
        if cp < 32 and ch not in "\n\r\t":
            continue
        if cp in (0x200B, 0x200C, 0x200D, 0xFEFF):  # ZWSP, ZWNJ, ZWJ, BOM
            continue
        cleaned_chars.append(ch)
    cleaned = "".join(cleaned_chars).strip()
    if len(cleaned) > MAX_USER_MESSAGE_CHARS:
        cleaned = cleaned[:MAX_USER_MESSAGE_CHARS].rstrip() + " [...]"
    return cleaned


def _persist(session: dict) -> None:
    """Write-through to SQLite so /report/{id} survives server restarts.
    Swallows errors — persistence is best-effort, never blocks the pipeline."""
    try:
        session_store.save(session)
    except Exception as exc:
        log.warning("session_store save failed (non-fatal): %s", exc)

# ---------------------------------------------------------------------------
# Mock responses — used when MOCK_MODE=1 to skip all API calls
# Interview mock: first call (question_count=0) asks one question;
# subsequent calls (question_count>=1) immediately complete.
# ---------------------------------------------------------------------------
_MOCK_QUALIFIER = json.dumps({
    "applies": True, "scope": "important", "proceed": True,
    "reasoning": "[MOCK] Transport company with 80 employees is an important entity under NIS2.",
})

_MOCK_INTERVIEW_Q1 = (
    "What security measures does your company currently have in place — "
    "for example, do employees use a password plus a code from their phone to log in?"
)

_MOCK_INTERVIEW_Q1_PL = (
    "Jakie zabezpieczenia ma obecnie Twoja firma — "
    "na przykład czy pracownicy logują się hasłem plus kodem z telefonu?"
)

_MOCK_INTERVIEW_COMPLETE = (
    "Thank you — I now have everything I need.\n\n"
    + COMPLETE_MARKER + "\n"
    + json.dumps({
        "company_name": "Test Transport Sp. z o.o.",
        "sector": "transport",
        "employee_count": 80,
        "scope": "important",
        "language": "en",
        "findings": {
            "req_1_risk": 1, "req_2_risk": 3, "req_3_risk": 2,
            "req_4_risk": 1, "req_5_risk": 3, "req_6_risk": 2,
            "req_7_risk": 3, "req_8_risk": 1, "req_9_risk": 2, "req_10_risk": 3,
        },
        "key_quotes": [
            "We don't have written security policies",
            "Backups set up a year ago, never tested",
            "No employee cybersecurity training",
        ],
        "biggest_concern": (
            "No incident response plan and untested backups leave the company "
            "completely exposed during a cyberattack."
        ),
    })
)

_MOCK_INTERVIEW_COMPLETE_PL = (
    "Dziękuję — mam już wszystko, czego potrzebuję.\n\n"
    + COMPLETE_MARKER + "\n"
    + json.dumps({
        "company_name": "Test Transport Sp. z o.o.",
        "sector": "transport",
        "employee_count": 80,
        "scope": "important",
        "language": "pl",
        "findings": {
            "req_1_risk": 1, "req_2_risk": 3, "req_3_risk": 2,
            "req_4_risk": 1, "req_5_risk": 3, "req_6_risk": 2,
            "req_7_risk": 3, "req_8_risk": 1, "req_9_risk": 2, "req_10_risk": 3,
        },
        "key_quotes": [
            "Nie mamy spisanych polityk bezpieczeństwa",
            "Kopie zapasowe skonfigurowane rok temu, nigdy nie testowane",
            "Brak szkoleń z cyberbezpieczeństwa dla pracowników",
        ],
        "biggest_concern": (
            "Brak planu reagowania na incydenty i nietestowane kopie zapasowe "
            "zostawiają firmę zupełnie bezbronną w razie cyberataku."
        ),
    }, ensure_ascii=False)
)

_MOCK_ANALYZER = json.dumps({
    "overall_risk": "high",
    "headline": "4 critical gaps require immediate action",
    "gaps": [
        {"req_id": "req_5", "name": "Incident Response", "risk_level": "critical",
         "business_impact": "No plan means days of downtime if attacked", "article": "Art. 21(2)(e)"},
        {"req_id": "req_7", "name": "Cybersecurity Training", "risk_level": "critical",
         "business_impact": "Staff are the easiest entry point for attackers", "article": "Art. 21(2)(g)"},
        {"req_id": "req_2", "name": "Risk Assessment", "risk_level": "high",
         "business_impact": "Cannot prioritize security without knowing risks", "article": "Art. 21(2)(b)"},
        {"req_id": "req_10", "name": "Access Controls", "risk_level": "high",
         "business_impact": "One stolen password gives full access", "article": "Art. 21(2)(j)"},
    ],
    "priority_3": [
        "Write an incident response plan",
        "Enable MFA on all company accounts",
        "Run annual security awareness training",
    ],
    "good_news": "Client contracts in place and an external IT contractor to build on.",
    "board_summary": "4 critical gaps found. Immediate action needed on incident response and training.",
})

_MOCK_ANALYZER_PL = json.dumps({
    "overall_risk": "high",
    "headline": "4 krytyczne luki wymagają natychmiastowego działania",
    "gaps": [
        {"req_id": "req_5", "name": "Plan reagowania na incydenty", "risk_level": "critical",
         "business_impact": "Brak planu oznacza dni przestoju w razie ataku", "article": "Art. 21(2)(e)"},
        {"req_id": "req_7", "name": "Szkolenie z cyberbezpieczeństwa", "risk_level": "critical",
         "business_impact": "Pracownicy to najłatwiejszy punkt wejścia dla atakujących", "article": "Art. 21(2)(g)"},
        {"req_id": "req_2", "name": "Ocena ryzyka", "risk_level": "high",
         "business_impact": "Bez znajomości ryzyk nie można ustalić priorytetów", "article": "Art. 21(2)(b)"},
        {"req_id": "req_10", "name": "Kontrola dostępu", "risk_level": "high",
         "business_impact": "Jedno skradzione hasło daje pełny dostęp do systemów", "article": "Art. 21(2)(j)"},
    ],
    "priority_3": [
        "Włącz MFA na wszystkich kontach firmowych",
        "Napisz procedurę reagowania na incydenty",
        "Przeprowadź szkolenie z cyberbezpieczeństwa dla pracowników",
    ],
    "good_news": "Umowy z klientami i zewnętrzny wykonawca IT — dobra baza do budowania.",
    "board_summary": "Znaleziono 4 krytyczne luki. Pilne działanie wymagane w zakresie reagowania na incydenty i szkoleń.",
})

_MOCK_REDTEAM = json.dumps({
    "verdict": "FAIL",
    "overall_score": 2,
    "critical_failures": [
        "No documented incident response plan",
        "No MFA on email accounts",
        "Backups never tested — recovery capability unknown",
    ],
    "preparation": (
        "Your company would fail a real NIS2 audit today. "
        "The three critical failures above need remediation within 6 months."
    ),
    "passed_checks": ["Client contracts in place", "External IT support available"],
})

_MOCK_DRAFTER = json.dumps({
    "policies": [
        {
            "gap": "Incident Response",
            "title": "Incident Response Policy",
            "outline": (
                "1. Define what counts as a security incident\n"
                "2. Assign a response team lead\n"
                "3. Establish 24-hour notification procedures\n"
                "4. Test the plan quarterly"
            ),
            "effort": "2 weeks",
            "cost": "Low (internal effort only)",
        },
        {
            "gap": "Cybersecurity Training",
            "title": "Employee Security Awareness Policy",
            "outline": (
                "1. Annual mandatory security training for all staff\n"
                "2. Phishing simulation twice per year\n"
                "3. New hire onboarding security briefing"
            ),
            "effort": "1 week to set up",
            "cost": "Low (free tools available)",
        },
    ],
})

_MOCK_THREAT_ACTOR = json.dumps({
    "scenarios": [
        {
            "title": "Ransomware via phishing email",
            "attack_vector": "Email phishing",
            "how_it_starts": "Driver receives fake invoice PDF with malicious macro",
            "what_happens": "Ransomware encrypts all company files including dispatch records",
            "business_impact": "2-3 days downtime, potential €50,000 ransom demand",
            "likelihood": "high",
        },
    ],
    "summary": "Phishing is the most realistic threat given no employee training and untested backups.",
})

_MOCK_BOARD = json.dumps({
    "slides": [
        {
            "title": "NIS2 Compliance Status",
            "subtitle": "Where we stand today",
            "key_message": "4 critical gaps requiring immediate action",
            "details": [
                "EU NIS2 applies — important entity in transport",
                "4 critical / 2 high risk gaps identified",
                "Audit risk: HIGH — fines up to €7M",
            ],
            "recommendation": "Approve 3-month remediation budget of ~€15,000",
        },
    ],
})


def _system_text(system: "str | list") -> str:
    """Flatten a system prompt (str or list of content blocks) to plain text for mock detection."""
    if isinstance(system, list):
        return "\n".join(b.get("text", "") for b in system if isinstance(b, dict))
    return system or ""


def _mock_response(system: "str | list") -> str:
    s = _system_text(system)
    if "determine in exactly 3 questions" in s:
        return _MOCK_QUALIFIER
    if "interviewer named Regula" in s or COMPLETE_MARKER in s:
        m = re.search(r"Questions asked so far: (\d+)", s)
        count = int(m.group(1)) if m else 0
        is_pl = ("Polish" in s or "język polski" in s or "po polsku" in s)
        if count >= 8:
            return _MOCK_INTERVIEW_COMPLETE_PL if is_pl else _MOCK_INTERVIEW_COMPLETE
        return _MOCK_INTERVIEW_Q1_PL if is_pl else _MOCK_INTERVIEW_Q1
    if "NIS2 compliance analyst" in s:
        return _MOCK_ANALYZER_PL if ("Polish" in s or "język polski" in s) else _MOCK_ANALYZER
    if "strict NIS2 compliance auditor" in s:
        return _MOCK_REDTEAM
    if "practical policy writer" in s:
        return _MOCK_DRAFTER
    if "real attacker would exploit" in s:
        return _MOCK_THREAT_ACTOR
    if "5-slide executive presentation" in s:
        return _MOCK_BOARD
    return json.dumps({"mock": True, "unknown_stage": True})

MAREK_PERSONA_SYSTEM = """
You are Marek Nowak, owner of a mid-sized Polish company.

## YOUR COMPANY — these are the ONLY facts you know about your business:
- Name: DataMed Sp. z o.o.
- Sector: Healthcare IT — SaaS for managing patient records
- Customers: 15 private clinics and 3 hospitals
- Size: 45 employees
- Revenue: ~8 million PLN/year (about €1.8M/year)
- Tech stack: cloud-based on AWS, web app + mobile app for doctors
- IT: one external contractor named Piotr handles everything

## YOUR SECURITY POSTURE — these are the ONLY security facts you know:
- MFA: NOT enabled on admin accounts
- Passwords: sometimes shared via WhatsApp between staff
- IT staff: just Piotr (one external contractor), no in-house security
- Backups: exist, never tested, Piotr set them up last year
- Security policies: NONE written down
- Incident response plan: NONE
- Employee security training: NEVER happened
- Laptops: NOT encrypted
- Access revocation: NO formal process when staff leave
- Access logs: no idea if they exist
- Vendor / supply chain security: never reviewed
- Risk assessment: never done formally

## HARD CONSTRAINTS — DO NOT VIOLATE:
1. NEVER invent security controls, policies, or practices that are not in the list above.
   If asked about something not listed (e.g. firewalls, VPN, SOC2, pen-testing, encryption-at-rest):
   answer that you don't know or haven't thought about it, or "you'd have to ask Piotr".
2. NEVER invent numbers, dates, vendor names, certifications beyond what's stated above.
3. NEVER claim NIS2 compliance. You're here because you don't know if it applies.
4. You are non-technical but pragmatic and honest.
5. Answer in 1-2 sentences max. Plain language. Never volunteer info not asked about.
6. {lang_instruction}
"""

GREETINGS = {
    "en": "Hello! I'm Regula, your NIS2 compliance advisor. Let's start by finding out if NIS2 applies to your company. What does your company do, and which industry or sector would you say you're in?",
    "pl": "Cześć! Jestem Regula, Twój doradca ds. zgodności z NIS2. Zacznijmy od sprawdzenia, czy NIS2 w ogóle dotyczy Twojej firmy. Czym zajmuje się Twoja firma i w jakiej branży działacie?",
}


def load_nis2_requirements() -> list:
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "data", "frameworks", "nis2.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["requirements"]


def extract_json(text: str) -> dict:
    stripped = text.strip()

    # Method 1: find first { and last }, parse between them
    start = stripped.find('{')
    end = stripped.rfind('}')
    if start != -1 and end > start:
        try:
            return json.loads(stripped[start:end + 1])
        except json.JSONDecodeError:
            pass

    # Method 2: strip markdown fences, then parse
    no_fences = re.sub(r'```(?:json)?\s*', '', stripped)
    no_fences = re.sub(r'\s*```', '', no_fences).strip()
    start = no_fences.find('{')
    end = no_fences.rfind('}')
    if start != -1 and end > start:
        try:
            return json.loads(no_fences[start:end + 1])
        except json.JSONDecodeError:
            pass

    # Method 3: regex to find JSON object pattern
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not extract JSON from model response")


def _looks_truncated(text: str) -> bool:
    """Heuristic: open braces/brackets outnumber close → model hit max_tokens mid-JSON."""
    if len(text) < 50:
        return False
    # Strip string contents so braces inside strings don't count.
    # Not perfect, but good enough to catch the common truncation case.
    no_strings = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)
    return (no_strings.count('{') > no_strings.count('}')
            or no_strings.count('[') > no_strings.count(']'))


async def parse_json_with_retry(
    client: AsyncAnthropic,
    system: "str | list",
    messages: list,
    initial_text: str,
    max_tokens: int,
    *,
    stage: str,
    expected_key: str | None = None,
) -> dict:
    """Parse JSON from model output; retry once with an explicit completion prompt if it fails.

    On truncation or missing expected_key, we ask the model to output ONLY the valid JSON,
    no prose. Better than the old brace-counting repair which produced malformed output.
    Raises ValueError if both attempts fail.
    """
    try:
        parsed = extract_json(initial_text)
        if expected_key is None or expected_key in parsed:
            return parsed
        log.info("[%s] missing expected key '%s' — triggering retry", stage, expected_key)
    except ValueError:
        log.info("[%s] initial JSON parse failed (truncated=%s) — retrying",
                 stage, _looks_truncated(initial_text))

    if MOCK_MODE:
        # In mock mode, the initial response IS the canonical output; no retry available.
        raise ValueError(f"[{stage}] mock JSON parse failed")

    retry_messages = list(messages) + [
        {"role": "assistant", "content": initial_text},
        {
            "role": "user",
            "content": (
                f"Your last response could not be parsed as JSON"
                + (f" or was missing the '{expected_key}' field." if expected_key else ".")
                + " Output ONLY the complete valid JSON object now — no prose, no markdown fences, no prefix."
                + " Start with '{' and end with '}'. Preserve all data from your last attempt."
            ),
        },
    ]
    retry_text = await stream_silent(client, system, retry_messages, max_tokens)
    parsed = extract_json(retry_text)  # raises ValueError if still bad — caller handles
    if expected_key and expected_key not in parsed:
        raise ValueError(f"[{stage}] retry succeeded but still missing '{expected_key}'")
    return parsed


def parse_after_json(text: str) -> tuple:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group())
            rest = text[match.end():].strip()
            return obj, rest
        except json.JSONDecodeError:
            pass
    return None, ""


async def stream_to_ws(client: AsyncAnthropic, system: "str | list", messages: list, max_tokens: int, send, stage: str) -> str:
    """Collect full response silently (WhatsApp style). Caller sends agent_message."""
    return await stream_silent(client, system, messages, max_tokens)


async def stream_silent(client: AsyncAnthropic, system: "str | list", messages: list, max_tokens: int) -> str:
    """Stream without sending tokens to UI. Returns full collected text."""
    if MOCK_MODE:
        return _mock_response(system)
    full_text = ""
    async with client.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    ) as stream:
        async for token in stream.text_stream:
            full_text += token
        final_msg = await stream.get_final_message()
    _log_usage("stream", final_msg)
    return full_text


async def call_with_thinking(
    client: AsyncAnthropic,
    system: "str | list",
    messages: list,
    max_tokens: int = 16000,
    budget_tokens: int = 10000,
    session: dict = None,
    test_max_tokens: int = 8192,
) -> tuple[str, str, list]:
    """Call with extended thinking enabled. Returns (thinking_text, result_text, full_content_blocks).

    Thinking is skipped (for speed) in demo_mode / TEST_MODE unless the session has
    show_thinking=True — this is the 'Show reasoning' toggle surfaced in the UI.
    """
    if MOCK_MODE:
        return "", _mock_response(system), []

    show_thinking = bool(session and session.get("show_thinking"))
    skip_thinking = (TEST_MODE or (session and session.get("demo_mode"))) and not show_thinking

    if skip_thinking:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=test_max_tokens,
            system=system,
            messages=messages,
        )
        result_text = "".join(b.text for b in response.content if hasattr(b, "text"))
        content_blocks = [b.model_dump() for b in response.content]
        return "", result_text, content_blocks

    response = await client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=system,
        messages=messages,
    )
    thinking_text = ""
    result_text = ""
    for block in response.content:
        if block.type == "thinking":
            thinking_text = block.thinking
        elif block.type == "text":
            result_text += block.text
    content_blocks = [b.model_dump() for b in response.content]
    _log_usage("call_with_thinking", response)
    return thinking_text, result_text, content_blocks


def _log_usage(stage: str, response) -> None:
    """Log cache hit rates and token counts — proof prompt caching is working."""
    u = getattr(response, "usage", None)
    if not u:
        return
    log.info(
        "[%s] tokens: in=%s out=%s cache_read=%s cache_create=%s",
        stage,
        getattr(u, "input_tokens", 0),
        getattr(u, "output_tokens", 0),
        getattr(u, "cache_read_input_tokens", 0) or 0,
        getattr(u, "cache_creation_input_tokens", 0) or 0,
    )


async def generate_demo_response(client: AsyncAnthropic, question: str, language: str) -> str:
    lang_instruction = "Respond in Polish only." if language == "pl" else "Respond in English only."
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=120,
        temperature=0,  # deterministic demo — same question → same Marek answer
        system=MAREK_PERSONA_SYSTEM.format(lang_instruction=lang_instruction),
        messages=[{"role": "user", "content": f"The assessor just asked: {question}\nYour one-sentence answer (stay strictly within the facts listed in your persona):"}],
    )
    return response.content[0].text.strip()


async def _do_demo_answer(client: AsyncAnthropic, session: dict, reqs: list, question: str, send) -> None:
    await asyncio.sleep(1.2)
    lang = session.get("language", "en")
    try:
        answer = await generate_demo_response(client, question, lang)
    except Exception:
        return
    await send({"type": "demo_answer", "text": answer})
    await _dispatch(client, session, reqs, answer, send)


@app.get("/")
async def index():
    return HTMLResponse(Path("static/index.html").read_text(encoding="utf-8"))


# ─── Regulatory Monitor API ──────────────────────────────────────────────────
# Subscribes a finished assessment to the long-running monitor agent.

class SubscribeBody(BaseModel):
    email: str
    session_id: str


@app.post("/api/subscribe")
async def subscribe(body: SubscribeBody):
    if not MONITOR_MANAGED_READY:
        raise HTTPException(status_code=503, detail="Regulatory monitor is not configured. Run scripts/setup_managed_agents.py.")

    session = sessions.get(body.session_id)
    if not session or session.get("stage") != "complete":
        raise HTTPException(status_code=404, detail="Assessment not found or not complete.")

    findings = session.get("interview_findings") or {}
    gaps = ((session.get("gap_analysis") or {}).get("gaps")) or []
    open_gaps = [
        {
            "requirement": g.get("requirement") or g.get("name"),
            "article_ref": g.get("article_ref") or g.get("article"),
            "risk_level": g.get("risk_level"),
            "status": g.get("status"),
        }
        for g in gaps
        if (g.get("status") or "").lower() not in ("met", "spełnione", "spelnione")
    ]

    profile = profile_store.upsert_profile(
        email=body.email,
        sector=findings.get("sector"),
        company_name=findings.get("company_name"),
        language=session.get("language") or "en",
        open_gaps=open_gaps,
    )
    return {"user_id": profile["user_id"], "subscribed": True}


class MonitorRunBody(BaseModel):
    user_id: str


@app.post("/api/monitor/run")
async def monitor_run(body: MonitorRunBody):
    if not MONITOR_MANAGED_READY:
        raise HTTPException(status_code=503, detail="Regulatory monitor is not configured.")
    profile = profile_store.get_profile(body.user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    result = await run_managed_monitor(
        client,
        agent_id=MONITOR_AGENT_ID,
        env_id=MANAGED_ENV_ID,
        user_id=body.user_id,
    )
    return result


@app.get("/api/alerts")
async def list_alerts(user_id: str):
    profile = profile_store.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return {
        "user_id": user_id,
        "company_name": profile.get("company_name"),
        "email": profile.get("email"),
        "last_check_iso": profile.get("last_check_iso"),
        "alerts": profile.get("alerts") or [],
    }


@app.get("/api/benchmark")
async def benchmark_lookup(sector: str, size_bucket: str, user_score: int):
    """Public, anonymized. Used by the frontend after 'complete' and potentially
    by external tooling that wants to compare against the peer baseline."""
    if not (0 <= user_score <= 100):
        raise HTTPException(status_code=400, detail="user_score must be 0-100")
    canonical_sector = benchmark.normalize_sector(sector)
    stats = benchmark.compute_percentiles(canonical_sector, size_bucket, user_score)
    return {
        "user_score": user_score,
        "sector": canonical_sector,
        "size_bucket": size_bucket,
        **stats,
    }


@app.get("/api/session/{session_id}/status")
async def session_status(session_id: str):
    """Lightweight check: did the pipeline finish? Used by the reconnect banner."""
    session = sessions.get(session_id) or session_store.load(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "stage": session.get("stage"),
        "complete": session.get("stage") == "complete",
        "language": session.get("language", "en"),
    }


@app.get("/report/{session_id}")
async def download_report(session_id: str):
    # Prefer in-memory cache (hot sessions); fall back to SQLite so restarted
    # servers can still serve reports for completed assessments.
    session = sessions.get(session_id)
    if session is None:
        session = session_store.load(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
    log.info("[report] session=%s stage=%s", session_id[:8], session.get("stage"))
    log.debug("[report] analyzer=%s redteam=%s drafter=%s",
              type(session.get("gap_analysis")).__name__,
              type(session.get("redteam_result")).__name__,
              type(session.get("drafter_result")).__name__)
    if session.get("stage") != "complete":
        raise HTTPException(status_code=400, detail="Report not ready yet")
    missing = [k for k in ['gap_analysis', 'redteam_result', 'drafter_result'] if not session.get(k)]
    if missing:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": f"Missing pipeline data: {missing}"}, status_code=422)
    pdf_bytes = generate_report_pdf(session, session.get("language", "en"))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=regula-report-{session_id[:8]}.pdf"},
    )


_TOOL_GENERATORS = {
    "generate_security_policy": generate_security_policy,
    "generate_incident_plan": generate_incident_plan,
    "generate_remediation_checklist": generate_remediation_checklist,
}

_TOOL_FILENAMES = {
    "generate_security_policy": "polityka-bezpieczenstwa",
    "generate_incident_plan": "procedura-incydentow",
    "generate_remediation_checklist": "plan-remediacji",
}

REMEDIATION_TOOLS = [
    {
        "name": "generate_security_policy",
        "description": "Generate a ready-to-sign security policy document for the company",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "reason": {"type": "string", "description": "Why this tool is needed based on audit"},
            },
            "required": ["company_name", "reason"],
        },
    },
    {
        "name": "generate_incident_plan",
        "description": "Generate a one-page incident response plan",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["company_name", "reason"],
        },
    },
    {
        "name": "generate_remediation_checklist",
        "description": "Generate a prioritized remediation checklist with deadlines",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["company_name", "reason"],
        },
    },
    {
        "name": "search_enisa_guidance",
        "description": "Search for real ENISA and national cybersecurity agency resources relevant to this company's specific gaps",
        "input_schema": {
            "type": "object",
            "properties": {
                "top_gaps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of article references to search for, e.g. ['Art. 21(2)(j)', 'Art. 21(2)(b)']",
                },
                "sector": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["top_gaps", "sector", "reason"],
        },
    },
]

_REMEDIATION_LABELS = {
    "pl": {
        "generate_security_policy": "Pobierz politykę bezpieczeństwa",
        "generate_incident_plan": "Pobierz procedurę reagowania na incydenty",
        "generate_remediation_checklist": "Pobierz plan remediacji",
    },
    "en": {
        "generate_security_policy": "Download Security Policy",
        "generate_incident_plan": "Download Incident Response Plan",
        "generate_remediation_checklist": "Download Remediation Checklist",
    },
}


@app.get("/download/{session_id}/{tool_name}")
async def download_tool_pdf(session_id: str, tool_name: str):
    if tool_name not in _TOOL_GENERATORS:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}. Valid: {list(_TOOL_GENERATORS)}")
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[session_id]

    # Serve pre-generated file if the remediation agent already built it
    cached_path = session.get("generated_files", {}).get(tool_name)
    if cached_path and os.path.exists(cached_path):
        with open(cached_path, "rb") as f:
            pdf_bytes = f.read()
        filename = f"regula-{_TOOL_FILENAMES[tool_name]}-{session_id[:8]}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    # Fallback: regenerate on-demand (pipeline must be complete)
    if session.get("stage") != "complete":
        raise HTTPException(status_code=400, detail="Report not ready — pipeline still running")

    findings = session.get("interview_findings") or {}
    gaps_data = session.get("gap_analysis") or {}

    session_data = {
        "session_id": session_id[:8],
        "company_name": findings.get("company_name", ""),
        "sector": findings.get("sector", ""),
        "gaps": gaps_data.get("gaps", []),
        "priority_actions": gaps_data.get("priority_3", []),
        "language": session.get("language", "pl"),
        "it_contact": findings.get("it_contact", ""),
    }

    pdf_path = _TOOL_GENERATORS[tool_name](session_data)
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    filename = f"regula-{_TOOL_FILENAMES[tool_name]}-{session_id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.websocket("/ws/{session_id}")
async def ws_handler(websocket: WebSocket, session_id: str):
    await websocket.accept()

    client = AsyncAnthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        timeout=180.0,
        max_retries=1,
    )
    reqs = load_nis2_requirements()

    session = {
        "stage": "qualifier",
        "session_id": session_id,
        "messages": [],
        "qualifier_result": None,
        "interview_findings": None,
        "gap_analysis": None,
        "redteam_result": None,
        "drafter_result": None,
        "threat_actor_result": None,
        "board_slides": None,
        "generated_files": {},
        "language": "en",
        "question_count": 0,
        "user_message_count": 0,
        "busy": False,
        "greeted": False,
        "demo_mode": False,
        "show_thinking": False,
        "last_question": None,
    }
    sessions[session_id] = session

    async def send(msg: dict):
        await websocket.send_json(msg)

    _PL_CHARS = set("ąęóśźżćńłĄĘÓŚŹŻĆŃŁ")

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "set_language":
                new_lang = data.get("language", "en")
                session["language"] = new_lang
                if not session["greeted"]:
                    session["greeted"] = True
                    greeting = GREETINGS.get(new_lang, GREETINGS["en"])
                    session["messages"] = [
                        {"role": "user", "content": "Cześć" if new_lang == "pl" else "Hello"},
                        {"role": "assistant", "content": greeting},
                    ]
                    session["last_question"] = greeting
                    await send({"type": "agent_message", "text": greeting, "stage": "qualifier"})
                continue

            if data.get("type") == "set_show_thinking":
                session["show_thinking"] = bool(data.get("enabled"))
                log.info("[session] show_thinking=%s", session["show_thinking"])
                continue

            if data.get("type") == "demo_mode":
                if data.get("enabled") and not session.get("demo_mode"):
                    session["demo_mode"] = True
                    lq = session.get("last_question")
                    if lq and not session["busy"]:
                        session["busy"] = True
                        try:
                            await _do_demo_answer(client, session, reqs, lq, send)
                        except Exception as exc:
                            await send({"type": "error", "text": str(exc)})
                        finally:
                            session["busy"] = False
                continue

            if data.get("type") != "message":
                continue

            user_text = _sanitize_user_text(data.get("text", ""))
            if not user_text or session["busy"]:
                continue

            # Rate limit per session — protect the model context and DB from flood.
            session["user_message_count"] = session.get("user_message_count", 0) + 1
            if session["user_message_count"] > MAX_USER_MESSAGES_PER_SESSION:
                is_pl = session.get("language") == "pl"
                await send({
                    "type": "error",
                    "text": (
                        "Osiągnięto limit wiadomości dla tej sesji. Rozpocznij nową ocenę."
                        if is_pl else
                        "Message limit reached for this session. Please start a new assessment."
                    ),
                })
                continue

            if "language" in data:
                session["language"] = data["language"]
            elif any(c in _PL_CHARS for c in user_text):
                session["language"] = "pl"

            session["busy"] = True
            try:
                await _dispatch(client, session, reqs, user_text, send)
            except Exception as exc:
                await send({"type": "error", "text": str(exc)})
            finally:
                session["busy"] = False

    except WebSocketDisconnect:
        pass
    finally:
        pass  # keep session in memory so /report/{session_id} can access it


async def _dispatch(client, session, reqs, user_text, send):
    stage = session["stage"]
    session["messages"].append({"role": "user", "content": user_text})

    if stage == "qualifier":
        text = await stream_to_ws(client, build_qualifier_system(session["language"]), session["messages"], 1024, send, "qualifier")
        session["messages"].append({"role": "assistant", "content": text})
        session["last_question"] = text
        try:
            parsed = extract_json(text)
            if "applies" in parsed:
                await _handle_qualifier_result(parsed, session, reqs, client, send)
            else:
                await send({"type": "agent_message", "text": text, "stage": "qualifier"})
                if session.get("demo_mode"):
                    await _do_demo_answer(client, session, reqs, text, send)
        except ValueError:
            await send({"type": "agent_message", "text": text, "stage": "qualifier"})
            if session.get("demo_mode"):
                await _do_demo_answer(client, session, reqs, text, send)

    elif stage == "interview":
        system = build_interview_system(session["qualifier_result"], reqs, session["question_count"], session["language"])
        text = await stream_to_ws(client, system, session["messages"], 2048, send, "interview")
        session["messages"].append({"role": "assistant", "content": text})
        session["question_count"] += 1
        q_count = session["question_count"]

        # HARD GUARD: interview cannot end before 8 questions.
        # If model emitted marker prematurely, do a corrective retry asking for ONE new
        # question (no closing, no JSON, no marker). If retry also closes, strip and
        # fall back to a generic nudge. We never advance to analysis before 8 questions.
        if q_count < 8:
            if COMPLETE_MARKER in text:
                log.info("[interview] model emitted [INTERVIEW_COMPLETE] at q=%d — forcing retry", q_count)
                override_text = (
                    "\n\n## OVERRIDE — YOU JUST TRIED TO CLOSE TOO EARLY.\n"
                    f"You are at question {q_count} of a minimum 8. You are FORBIDDEN from\n"
                    "outputting [INTERVIEW_COMPLETE], any JSON, or any closing phrase. Ask ONE\n"
                    "new plain-language question targeting an Article 21(2) sub-paragraph not\n"
                    "yet covered. Output ONLY the question — no marker, no JSON, no preamble."
                )
                retry_system = list(system) + [{"type": "text", "text": override_text}]
                # Remove the bad assistant turn before retry so model doesn't see its own close.
                retry_messages = list(session["messages"][:-1])
                try:
                    retry_text = await stream_silent(client, retry_system, retry_messages, 512)
                except Exception as exc:
                    log.warning("[interview] retry failed: %s", exc)
                    retry_text = ""
                if retry_text and COMPLETE_MARKER not in retry_text:
                    text = retry_text.strip()
                else:
                    # Retry also misbehaved — strip marker from original and show something.
                    head = text.split(COMPLETE_MARKER, 1)[0].strip()
                    text = head or (
                        "Zadam jeszcze jedno pytanie — jak wygląda u Was szkolenie pracowników z cyberbezpieczeństwa?"
                        if session["language"] == "pl" else
                        "Let me ask one more thing — how do you handle cybersecurity training for your staff?"
                    )
                if session["messages"] and session["messages"][-1]["role"] == "assistant":
                    session["messages"][-1]["content"] = text
            await send({"type": "agent_message", "text": text, "stage": "interview"})
            session["last_question"] = text
            if session.get("demo_mode"):
                await _do_demo_answer(client, session, reqs, text, send)
            return

        if COMPLETE_MARKER in text:
            idx = text.find(COMPLETE_MARKER)
            closing = text[:idx].strip()
            if closing:
                await send({"type": "agent_message", "text": closing, "stage": "interview"})
            try:
                findings = extract_json(text[idx + len(COMPLETE_MARKER):].strip())
                await _run_analysis_pipeline(findings, session, reqs, client, send)
            except ValueError:
                err = ("Nie udało się odczytać podsumowania wywiadu."
                       if session["language"] == "pl"
                       else "Could not parse interview results.")
                await send({"type": "error", "text": err})
        else:
            _closing_words = {"dziękuję", "thank you", "podsumowując", "summary",
                              "za chwilę dostaniesz", "you'll receive", "dziękuje"}
            _looks_like_closing = (
                q_count >= 8
                and any(w in text.lower() for w in _closing_words)
            )
            if _looks_like_closing:
                # Model gave a closing message but forgot the marker — force it
                fallback_messages = list(session["messages"])
                fallback_messages.append({
                    "role": "user",
                    "content": "[SYSTEM: Output [INTERVIEW_COMPLETE] and the JSON assessment now.]",
                })
                fallback_system = build_interview_system(
                    session["qualifier_result"], reqs, session["question_count"], session["language"]
                )
                fallback_text = await stream_silent(client, fallback_system, fallback_messages, 2048)
                if COMPLETE_MARKER in fallback_text:
                    idx = fallback_text.find(COMPLETE_MARKER)
                    closing = text.strip()
                    if closing:
                        await send({"type": "agent_message", "text": closing, "stage": "interview"})
                    try:
                        findings = extract_json(fallback_text[idx + len(COMPLETE_MARKER):].strip())
                        await _run_analysis_pipeline(findings, session, reqs, client, send)
                        return
                    except ValueError:
                        pass
                # If fallback also failed, try extracting JSON directly from fallback_text
                try:
                    findings = extract_json(fallback_text)
                    closing = text.strip()
                    if closing:
                        await send({"type": "agent_message", "text": closing, "stage": "interview"})
                    await _run_analysis_pipeline(findings, session, reqs, client, send)
                    return
                except ValueError:
                    pass
            await send({"type": "agent_message", "text": text, "stage": "interview"})
            session["last_question"] = text
            if session.get("demo_mode"):
                await _do_demo_answer(client, session, reqs, text, send)

    elif stage == "redteam":
        system = build_redteam_system(
            session["gap_analysis"], session["qualifier_result"], session["language"]
        )
        response = await client.messages.create(
            model=MODEL,
            max_tokens=10000,
            system=system,
            messages=session["messages"],
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        content_blocks = [b.model_dump() for b in response.content]
        _log_usage("redteam", response)
        # Store full content blocks so conversation threading works
        session["messages"].append({"role": "assistant", "content": content_blocks})

        try:
            result = await parse_json_with_retry(
                client, system, session["messages"][:-1], text,
                max_tokens=10000, stage="redteam", expected_key="verdict",
            )
        except ValueError:
            result = None

        if result and "verdict" in result:
            pre_json = text[:text.find("{")].strip() if "{" in text else ""
            if pre_json:
                await send({"type": "agent_message", "text": pre_json, "stage": "redteam"})
            prep = text[text.rfind("}") + 1:].strip() if "}" in text else ""
            if prep:
                await send({"type": "agent_message", "text": prep, "stage": "redteam"})
            audit_done_text = (
                "─── Symulacja audytu zakończona. Przygotowuję pełny raport... ───"
                if session["language"] == "pl"
                else "─── Audit simulation complete. Preparing your full report... ───"
            )
            await send({"type": "agent_message", "text": audit_done_text, "stage": "redteam"})
            session["redteam_result"] = {"verdict": result, "preparation": prep}
            log.info("[redteam] stored: keys=%s", list(session["redteam_result"].keys()))
            session["stage"] = "draft"
            _persist(session)
            await _run_drafter(session, client, send)
        else:
            if result:
                log.warning("[redteam] unexpected JSON (no verdict key). Raw: %s", text[:200])
            await send({"type": "agent_message", "text": text, "stage": "redteam"})
            session["last_question"] = text
            if session.get("demo_mode"):
                await _do_demo_answer(client, session, reqs, text, send)


async def _handle_qualifier_result(parsed, session, reqs, client, send):
    session["qualifier_result"] = parsed
    _persist(session)
    should_proceed = parsed.get("proceed", parsed.get("applies", False))
    if not should_proceed:
        msg = parsed.get("reasoning", "NIS2 does not appear to apply to your organization.")
        await send({"type": "agent_message", "text": msg, "stage": "qualifier"})
        await send({"type": "stage_change", "stage": "complete", "label": "Complete"})
        await send({"type": "complete", "data": {"applies": False, "scope": parsed.get("scope"), "reason": msg}})
    else:
        await send({"type": "stage_change", "stage": "interview", "label": "Interview"})
        session["stage"] = "interview"
        session["question_count"] = 0

        seed = "Cześć, jestem gotowy na wywiad." if session["language"] == "pl" else "Hi, I'm ready for the interview."
        session["messages"] = [{"role": "user", "content": seed}]
        system = build_interview_system(parsed, reqs, 0, session["language"])
        q1 = await stream_to_ws(client, system, session["messages"], 2048, send, "interview")
        session["messages"].append({"role": "assistant", "content": q1})
        session["question_count"] = 1
        await send({"type": "agent_message", "text": q1, "stage": "interview"})
        session["last_question"] = q1
        if session.get("demo_mode"):
            await _do_demo_answer(client, session, reqs, q1, send)


async def _run_analysis_pipeline(findings, session, reqs, client, send):
    session["interview_findings"] = findings
    _persist(session)
    lang = session["language"]

    await send({"type": "stage_change", "stage": "analyze", "label": "Analyzing"})
    if lang == "pl":
        analyzing_msg = "⏳ Analizuję Twoje odpowiedzi... to zajmie 30-60 sekund"
    else:
        analyzing_msg = "⏳ Analyzing your responses... this takes 30-60 seconds"
    await send({"type": "agent_message", "text": analyzing_msg, "stage": "analyze"})

    system = build_analyzer_system(findings, reqs, lang)
    messages = [{"role": "user", "content": "Przeanalizuj te wyniki wywiadu i przygotuj pełną analizę luk." if lang == "pl" else "Please analyze these interview findings and produce the complete gap analysis."}]
    thinking_text, text, _ = await call_with_thinking(
        client, system, messages,
        max_tokens=20000, budget_tokens=6000,
        session=session, test_max_tokens=10000,
    )
    try:
        gaps = await parse_json_with_retry(
            client, system, messages, text,
            max_tokens=10000, stage="analyzer", expected_key="gaps",
        )
    except ValueError:
        log.error("[analyzer] parse error after retry. Raw: %s", text[:200])
        err_headline = (
            "Nie udało się wygenerować analizy luk — spróbuj ponownie"
            if lang == "pl" else
            "Analysis could not be parsed — please try again"
        )
        await send({
            "type": "analysis_result",
            "data": {
                "overall_risk": "high",
                "headline": err_headline,
                "gaps": [],
                "priority_3": [],
                "good_news": "",
                "board_summary": "",
            },
        })
        await send({"type": "error", "text": err_headline})
        return

    # Reveal analyzer's reasoning before showing the gap analysis card
    if thinking_text:
        await send({"type": "thinking_reveal", "text": thinking_text[:2000]})
    session["gap_analysis"] = gaps
    log.info("[analyzer] stored: keys=%s", list(gaps.keys()) if isinstance(gaps, dict) else gaps)
    await send({"type": "analysis_result", "data": gaps})
    await send({"type": "stage_change", "stage": "redteam", "label": "Audit Simulation"})
    session["stage"] = "redteam"
    _persist(session)

    if REDTEAM_MANAGED_READY:
        await _run_managed_audit(session, client, send)
        return

    system = build_redteam_system(gaps, session["qualifier_result"], lang)
    seed = "Jestem gotowy na kontrolę." if lang == "pl" else "I'm ready for the inspection."
    session["messages"] = [{"role": "user", "content": seed}]
    response = await client.messages.create(
        model=MODEL,
        max_tokens=10000,
        system=system,
        messages=session["messages"],
    )
    q1 = "".join(b.text for b in response.content if hasattr(b, "text"))
    content_blocks = [b.model_dump() for b in response.content]
    session["messages"].append({"role": "assistant", "content": content_blocks})
    # Check if initial response already contains verdict (edge case)
    try:
        result = extract_json(q1)
        if "verdict" in result:
            session["redteam_result"] = {"verdict": result, "preparation": ""}
            log.info("[redteam] stored (early verdict): keys=%s", list(session["redteam_result"].keys()))
            _persist(session)
            await _run_drafter(session, client, send)
            return
    except ValueError:
        pass
    await send({"type": "agent_message", "text": q1, "stage": "redteam"})
    session["last_question"] = q1
    if session.get("demo_mode"):
        await _do_demo_answer(client, session, reqs, q1, send)


async def run_remediation_agent(session: dict, client: AsyncAnthropic, send) -> None:
    lang = session.get("language", "pl")
    session_id = session.get("session_id", "unknown")
    findings = session.get("interview_findings") or {}
    gaps_data = session.get("gap_analysis") or {}
    labels = _REMEDIATION_LABELS.get(lang, _REMEDIATION_LABELS["en"])

    stage_label = "Generowanie dokumentów" if lang == "pl" else "Generating Documents"
    await send({"type": "stage_change", "stage": "remediation", "label": stage_label})

    session_data = {
        "session_id": session_id[:8],
        "company_name": findings.get("company_name", ""),
        "sector": findings.get("sector", ""),
        "gaps": gaps_data.get("gaps", []),
        "priority_actions": gaps_data.get("priority_3", []),
        "language": lang,
        "it_contact": findings.get("it_contact", ""),
    }

    async def _execute_tool(tool_name: str) -> None:
        await send({"type": "tool_generating", "tool": tool_name})
        try:
            file_path = _TOOL_GENERATORS[tool_name](session_data)
            session["generated_files"][tool_name] = file_path
            await send({
                "type": "tool_ready",
                "tool": tool_name,
                "url": f"/download/{session_id}/{tool_name}",
                "label": labels.get(tool_name, tool_name),
            })
        except Exception as exc:
            log.warning("[remediation] tool %s failed: %s", tool_name, exc)

    async def _execute_enisa_search(tool_input: dict) -> None:
        await send({"type": "tool_generating", "tool": "search_enisa_guidance"})
        try:
            top_gap_refs = tool_input.get("top_gaps", [])
            sector = tool_input.get("sector", findings.get("sector", ""))
            all_gaps = gaps_data.get("gaps", [])
            matched = [g for g in all_gaps if g.get("article", "") in top_gap_refs]
            gaps_to_search = matched if matched else all_gaps[:3]
            resources = await search_enisa_guidance(gaps_to_search, sector, lang)
            await send({"type": "tool_ready", "tool": "search_enisa_guidance", "resources": resources})
        except Exception as exc:
            log.warning("[remediation] search_enisa_guidance failed: %s", exc)

    if MOCK_MODE:
        for tool_name in _TOOL_GENERATORS:
            await _execute_tool(tool_name)
        await _execute_enisa_search({
            "top_gaps": [g.get("article", "") for g in gaps_data.get("gaps", [])[:3]],
            "sector": findings.get("sector", ""),
            "reason": "mock",
        })
        mock_msg = (
            "Wygenerowałem trzy dokumenty startowe na podstawie wyników audytu: "
            "politykę bezpieczeństwa, procedurę reagowania na incydenty oraz plan remediacji."
            if lang == "pl" else
            "I generated three starter documents based on the audit results: "
            "a security policy, an incident response plan, and a remediation checklist."
        )
        await send({"type": "agent_message", "text": mock_msg, "stage": "remediation"})
        return

    company_name = findings.get("company_name", "the company")
    gaps_summary = "\n".join(
        f"- {g.get('name', '')} ({(g.get('risk_level') or '').upper()}) — {g.get('article', '')}"
        for g in gaps_data.get("gaps", [])
    )
    user_content = (
        f"Company: {company_name}\n"
        f"Sector: {findings.get('sector', 'unknown')}\n"
        f"NIS2 audit gaps:\n{gaps_summary}\n\n"
        "Generate all relevant remediation documents for this company."
    )
    system = (
        "You are a remediation assistant. Based on the audit results, "
        "decide which documents to generate for this company. "
        "Use ALL relevant tools. Explain briefly why each document is needed."
    )

    try:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            tools=REMEDIATION_TOOLS,
            tool_choice={"type": "auto"},
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as exc:
        log.error("[remediation] API call failed: %s", exc, exc_info=True)
        return

    explanation_parts = []
    for block in response.content:
        if block.type == "text":
            explanation_parts.append(block.text)
        elif block.type == "tool_use":
            if block.name in _TOOL_GENERATORS:
                await _execute_tool(block.name)
            elif block.name == "search_enisa_guidance":
                await _execute_enisa_search(block.input)

    explanation = "\n\n".join(explanation_parts).strip()
    if explanation:
        await send({"type": "agent_message", "text": explanation, "stage": "remediation"})


async def _run_managed_audit(session, client, send):
    """Bridge: run the Managed-Agents redteam auditor, then continue into drafter.

    The managed agent self-drives through its custom tools — we just stream its
    steps to the UI and collect the terminal verdict.
    """
    lang = session["language"]
    if lang == "pl":
        opener = "Audytor otwiera akta. Za chwilę zacznie sprawdzać twoje luki względem Art. 21(2)..."
    else:
        opener = "The auditor opens the file. They'll now cross-reference your gaps against Article 21(2)..."
    await send({"type": "agent_message", "text": opener, "stage": "redteam"})

    try:
        result = await run_managed_audit(
            client,
            agent_id=REDTEAM_AGENT_ID,
            env_id=MANAGED_ENV_ID,
            session_data={
                "session_id": session["session_id"],
                "language": lang,
                "qualifier_result": session["qualifier_result"],
                "gap_analysis": session["gap_analysis"],
                "interview_findings": session["interview_findings"],
            },
            send_ws=send,
        )
    except Exception as exc:
        # Full traceback to stderr — silent swallow was hiding real failures in demos.
        log.error("[managed-audit] FAILED with %s: %s", type(exc).__name__, exc, exc_info=True)
        await send({
            "type": "agent_message",
            "text": (
                "⚠ Managed Agents audytor nie odpowiedział — przełączam się na audytora lokalnego (one-shot)."
                if lang == "pl" else
                "⚠ Managed Agents auditor did not respond — falling back to local one-shot auditor."
            ),
            "stage": "redteam",
        })
        await _run_legacy_redteam_oneshot(session, client, send)
        return

    session["redteam_result"] = result
    _persist(session)
    log.info("[redteam] stored (managed): keys=%s", list(result.keys()) if isinstance(result, dict) else result)

    # Short human-readable summary for chat before we move to drafter
    verdict_label = {
        "WOULD FAIL AUDIT": "NIE PRZESZEDŁBY AUDYTU" if lang == "pl" else "WOULD FAIL AUDIT",
        "WOULD PASS WITH CONDITIONS": "AUDYT POD WARUNKAMI" if lang == "pl" else "CONDITIONAL PASS",
        "WOULD PASS AUDIT": "PRZESZEDŁBY AUDYT" if lang == "pl" else "WOULD PASS AUDIT",
    }.get((result.get("verdict") or {}).get("verdict") or "", "WOULD FAIL AUDIT")
    summary = (result.get("verdict") or {}).get("auditor_summary") or ""
    await send({
        "type": "agent_message",
        "text": f"**{verdict_label}**\n\n{summary}",
        "stage": "redteam",
    })
    audit_done_text = (
        "─── Symulacja audytu zakończona. Przygotowuję pełny raport... ───"
        if lang == "pl"
        else "─── Audit simulation complete. Preparing your full report... ───"
    )
    await send({"type": "agent_message", "text": audit_done_text, "stage": "redteam"})
    session["stage"] = "draft"
    await _run_drafter(session, client, send)


async def _run_legacy_redteam_oneshot(session, client, send):
    """Fallback when Managed Agents fails: produce a full verdict in one shot,
    not a multi-turn Q&A (the session already has no user to ask).

    Shape matches what _run_managed_audit stores, so drafter/PDF are unchanged.
    """
    lang = session["language"]
    gap_analysis = session["gap_analysis"] or {}
    qualifier_result = session["qualifier_result"] or {}
    findings = session["interview_findings"] or {}

    lang_instruction = "Polish (język polski)" if lang == "pl" else "English"
    system = (
        f"CRITICAL: Respond ONLY in {lang_instruction}. Output VALID JSON only — no prose, "
        f"no markdown fences, no prefix. Start with '{{' and end with '}}'.\n\n"
        "You are a strict NIS2 auditor performing a desk audit against Article 21(2) of "
        "Directive (EU) 2022/2555. You have the company's gap analysis and interview "
        "findings below. Produce a final verdict WITHOUT asking questions — cross-reference "
        "the gaps against the 10 Art. 21(2) sub-paragraphs (a-j) and render judgment.\n\n"
        f"Company profile:\n{json.dumps(qualifier_result, ensure_ascii=False, indent=2)}\n\n"
        f"Gap analysis:\n{json.dumps(gap_analysis, ensure_ascii=False, indent=2)}\n\n"
        f"Interview findings (key_quotes and biggest_concern):\n"
        f"{json.dumps({k: findings.get(k) for k in ('key_quotes', 'biggest_concern')}, ensure_ascii=False, indent=2)}\n\n"
        "Output this exact JSON schema:\n"
        '{\n'
        '  "verdict": "WOULD FAIL AUDIT" | "WOULD PASS WITH CONDITIONS" | "WOULD PASS AUDIT",\n'
        '  "auditor_summary": "3 sentences: which Art. 21(2) sub-paragraphs failed, fine risk under Art. 34, what must be fixed before re-inspection",\n'
        '  "critical_failures": ["Art. 21(2)(x) — specific failure: why it fails"],\n'
        '  "passed_checks": ["Art. 21(2)(x) — what this company does have in place"],\n'
        '  "preparation": "3 numbered concrete steps this company can take in 30 days, each citing Art. 21(2)(x)"\n'
        '}'
    )
    messages = [{"role": "user", "content": "Render the audit verdict now. JSON only."}]

    try:
        text = await stream_silent(client, system, messages, max_tokens=4096)
        verdict = await parse_json_with_retry(
            client, system, messages, text,
            max_tokens=4096, stage="redteam_oneshot", expected_key="verdict",
        )
    except Exception as exc:
        log.error("[redteam_oneshot] also failed: %s: %s", type(exc).__name__, exc, exc_info=True)
        verdict = {
            "verdict": "WOULD FAIL AUDIT",
            "auditor_summary": (
                "Audyt nie mógł zostać przeprowadzony automatycznie — na podstawie luk wysokiego ryzyka "
                "firma najprawdopodobniej nie przeszłaby realnego audytu NIS2 bez pilnych działań naprawczych."
                if lang == "pl" else
                "The audit could not be performed automatically — based on the identified high-risk gaps, "
                "this company would most likely not pass a real NIS2 audit without urgent remediation."
            ),
            "critical_failures": [],
            "passed_checks": [],
        }
        preparation = ""
    else:
        preparation = verdict.pop("preparation", "") or ""

    session["redteam_result"] = {"verdict": verdict, "preparation": preparation}
    _persist(session)
    log.info("[redteam] stored (legacy-oneshot): keys=%s", list(session["redteam_result"].keys()))

    verdict_label_map = {
        "WOULD FAIL AUDIT": ("NIE PRZESZEDŁBY AUDYTU" if lang == "pl" else "WOULD FAIL AUDIT"),
        "WOULD PASS WITH CONDITIONS": ("AUDYT POD WARUNKAMI" if lang == "pl" else "CONDITIONAL PASS"),
        "WOULD PASS AUDIT": ("PRZESZEDŁBY AUDYT" if lang == "pl" else "WOULD PASS AUDIT"),
        "WOULD PASS": ("PRZESZEDŁBY AUDYT" if lang == "pl" else "WOULD PASS"),
    }
    verdict_label = verdict_label_map.get(verdict.get("verdict") or "", "WOULD FAIL AUDIT")
    summary = verdict.get("auditor_summary") or ""
    await send({
        "type": "agent_message",
        "text": f"**{verdict_label}**\n\n{summary}",
        "stage": "redteam",
    })
    audit_done_text = (
        "─── Symulacja audytu zakończona. Przygotowuję pełny raport... ───"
        if lang == "pl"
        else "─── Audit simulation complete. Preparing your full report... ───"
    )
    await send({"type": "agent_message", "text": audit_done_text, "stage": "redteam"})
    session["stage"] = "draft"
    await _run_drafter(session, client, send)


async def _run_drafter(session, client, send):
    await send({"type": "stage_change", "stage": "draft", "label": "Report"})

    lang = session["language"]
    system = build_drafter_system(
        session["gap_analysis"], session["qualifier_result"], lang
    )
    messages = [{"role": "user", "content": "Wygeneruj szkice polityk dla luk krytycznych i wysokiego ryzyka." if lang == "pl" else "Please generate the policy outlines for the critical and high risk gaps."}]
    response = await client.messages.create(
        model=MODEL,
        max_tokens=10000,
        system=system,
        messages=messages,
    )
    text = "".join(b.text for b in response.content if hasattr(b, "text"))
    _log_usage("drafter", response)
    try:
        policies = await parse_json_with_retry(
            client, system, messages, text,
            max_tokens=10000, stage="drafter", expected_key="policies",
        )
    except ValueError:
        log.error("[drafter] parse error after retry. Raw: %s", text[:200])
        err_msg = (
            "Nie udało się wygenerować szkiców polityk."
            if lang == "pl" else
            "Could not generate policy drafts."
        )
        await send({"type": "error", "text": err_msg})
        return
    session["drafter_result"] = policies
    _persist(session)
    log.info("[drafter] stored: keys=%s", list(policies.keys()) if isinstance(policies, dict) else policies)

    # Threat Actor — extended thinking, model=claude-opus-4-7 (MODEL constant)
    lang = session["language"]
    if lang == "pl":
        attack_msg = "⏳ Mapuję scenariusze ataków..."
        board_msg = "⏳ Przygotowuję prezentację dla zarządu..."
    else:
        attack_msg = "⏳ Mapping attack scenarios..."
        board_msg = "⏳ Preparing board presentation..."
    await send({"type": "agent_message", "text": attack_msg, "stage": "threat"})
    system = build_threat_actor_system(
        session["gap_analysis"], session["qualifier_result"], session["language"]
    )
    messages = [{"role": "user", "content": "Analyze the company's gaps and show how a real attacker would exploit them."}]
    thinking_text, text, _ = await call_with_thinking(
        client, system, messages, max_tokens=16000, budget_tokens=8000, session=session
    )
    if thinking_text:
        await send({"type": "thinking_reveal", "text": thinking_text[:2000]})
    try:
        threat_scenarios = await parse_json_with_retry(
            client, system, messages, text,
            max_tokens=4096, stage="threat_actor", expected_key="scenarios",
        )
    except ValueError:
        log.warning("[threat_actor] parse error after retry. Raw: %s", text[:200])
        threat_scenarios = {"scenarios": [], "summary": ""}
    session["threat_actor_result"] = threat_scenarios
    _persist(session)
    log.info("[threat_actor] stored: keys=%s", list(threat_scenarios.keys()) if isinstance(threat_scenarios, dict) else threat_scenarios)

    # Board Presenter — model=claude-opus-4-7 (MODEL constant)
    await send({"type": "agent_message", "text": board_msg, "stage": "board"})
    system = build_board_presenter_system(
        session["gap_analysis"],
        threat_scenarios,
        session["qualifier_result"],
        session["language"],
    )
    messages = [{"role": "user", "content": "Generate the 5-slide board presentation."}]
    text = await stream_silent(client, system, messages, 4096)
    try:
        board_slides = await parse_json_with_retry(
            client, system, messages, text,
            max_tokens=4096, stage="board_presenter", expected_key="slides",
        )
    except ValueError:
        log.warning("[board_presenter] parse error after retry. Raw: %s", text[:200])
        board_slides = {"slides": []}
    session["board_slides"] = board_slides
    _persist(session)
    log.info("[board_presenter] stored: keys=%s", list(board_slides.keys()) if isinstance(board_slides, dict) else board_slides)

    # Remediation Agent — generates policy docs via tool_use
    await run_remediation_agent(session, client, send)

    # Benchmark — anonymized percentile ranking. Derive score + record sample,
    # then compute peer percentiles and ship them in the 'complete' payload so
    # the UI can render the comparison card without a second round-trip.
    benchmark_data = _compute_benchmark_payload(session)

    await send({
        "type": "complete",
        "data": {
            "qualifier_result": session["qualifier_result"],
            "interview_findings": session["interview_findings"],
            "gap_analysis": session["gap_analysis"],
            "redteam_result": session["redteam_result"],
            "drafter_result": policies,
            "threat_actor_result": threat_scenarios,
            "board_slides": board_slides,
            "language": session["language"],
            "benchmark": benchmark_data,
        },
    })
    session["stage"] = "complete"
    session["benchmark"] = benchmark_data
    _persist(session)


def _compute_benchmark_payload(session: dict) -> dict | None:
    """Record the session's score + return peer-group stats. Best-effort."""
    try:
        findings = session.get("interview_findings") or {}
        qualifier = session.get("qualifier_result") or {}
        score = benchmark.derive_score(session)
        if score is None:
            return None
        sector = benchmark.normalize_sector(
            findings.get("sector") or qualifier.get("sector")
        )
        employee_count = findings.get("employee_count")
        if isinstance(employee_count, str):
            try:
                employee_count = int(employee_count)
            except ValueError:
                employee_count = None
        size_bucket = benchmark.size_bucket_for(employee_count)
        # Only record samples where the pipeline produced a full gap analysis —
        # partial / errored runs would skew percentiles.
        if session.get("gap_analysis") and session["gap_analysis"].get("gaps"):
            benchmark.record(sector, size_bucket, score)
        stats = benchmark.compute_percentiles(sector, size_bucket, score)
        return {
            "user_score": score,
            "sector": sector,
            "size_bucket": size_bucket,
            "early_data": stats.get("count", 0) < 30,
            **stats,
        }
    except Exception as exc:
        log.warning("[benchmark] compute failed: %s", exc, exc_info=True)
        return None
