import asyncio
import json
import os
import re
from pathlib import Path

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response

load_dotenv()

from agents.qualifier import build_qualifier_system
from agents.interviewer import build_interview_system
from agents.analyzer import build_analyzer_system, build_analyzer_system_with_thinking
from agents.redteam import build_redteam_system
from agents.drafter import build_drafter_system
from agents.threat_actor import build_threat_actor_system
from agents.board_presenter import build_board_presenter_system
from utils.pdf import generate_report_pdf

app = FastAPI()
MODEL = "claude-opus-4-7"
COMPLETE_MARKER = "[INTERVIEW_COMPLETE]"
MOCK_MODE = bool(os.getenv("MOCK_MODE"))
sessions: dict = {}

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


def _mock_response(system: str) -> str:
    if "determine in exactly 3 questions" in system:
        return _MOCK_QUALIFIER
    if "interviewer named Regula" in system or COMPLETE_MARKER in system:
        m = re.search(r"Questions asked so far: (\d+)", system)
        count = int(m.group(1)) if m else 0
        return _MOCK_INTERVIEW_COMPLETE if count >= 1 else _MOCK_INTERVIEW_Q1
    if "NIS2 compliance analyst" in system:
        return _MOCK_ANALYZER_PL if ("Polish" in system or "język polski" in system) else _MOCK_ANALYZER
    if "strict NIS2 compliance auditor" in system:
        return _MOCK_REDTEAM
    if "practical policy writer" in system:
        return _MOCK_DRAFTER
    if "real attacker would exploit" in system:
        return _MOCK_THREAT_ACTOR
    if "5-slide executive presentation" in system:
        return _MOCK_BOARD
    return json.dumps({"mock": True, "unknown_stage": True})

MAREK_PERSONA_SYSTEM = """\
You are Marek, owner of a Polish road freight company (80 employees, \
transport sector). You are being interviewed about your company's \
cybersecurity. Your situation:
- No written security policies — everything is informal
- External IT contractor who comes when something breaks
- Company Gmail accounts, no MFA or two-step verification
- Backups set up by IT guy a year ago, never tested
- No employee cybersecurity training ever
- NDAs with clients but nothing specific about IT security
- Laptops are standard consumer devices, no encryption
- If systems went down, would need 2-3 days to recover
- You are not technical — you don't know jargon

Rules:
- Answer in {language}
- ONE sentence only — short, direct, realistic
- Use natural business owner language, no technical terms
- Be honest about gaps without being defensive
- Never volunteer information you weren't asked about
- If asked about something you don't have: say so simply
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


async def stream_to_ws(client: AsyncAnthropic, system: str, messages: list, max_tokens: int, send, stage: str) -> str:
    """Collect full response silently (WhatsApp style). Caller sends agent_message."""
    return await stream_silent(client, system, messages, max_tokens)


async def stream_silent(client: AsyncAnthropic, system: str, messages: list, max_tokens: int) -> str:
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
    return full_text


async def call_with_thinking(
    client: AsyncAnthropic,
    system: str,
    messages: list,
    max_tokens: int = 16000,
    budget_tokens: int = 10000,
    session: dict = None,
) -> tuple[str, str, list]:
    """Call with extended thinking enabled. Returns (thinking_text, result_text, full_content_blocks).
    In demo mode, skips extended thinking for speed."""
    if MOCK_MODE:
        return "", _mock_response(system), []
    if session and session.get("demo_mode"):
        response = await client.messages.create(
            model=MODEL,
            max_tokens=8192,
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
    # Convert SDK objects to dicts so they can be passed back as conversation history
    content_blocks = [b.model_dump() for b in response.content]
    return thinking_text, result_text, content_blocks


async def generate_demo_response(client: AsyncAnthropic, question: str, language: str) -> str:
    lang_name = "Polish" if language == "pl" else "English"
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=100,
        system=MAREK_PERSONA_SYSTEM.format(language=lang_name),
        messages=[{"role": "user", "content": f"The assessor just asked: {question}\nYour one-sentence answer:"}],
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


@app.get("/report/{session_id}")
async def download_report(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[session_id]
    if session.get("stage") != "complete":
        raise HTTPException(status_code=400, detail="Report not ready yet")
    pdf_bytes = generate_report_pdf(session, session.get("language", "en"))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=regula-report-{session_id[:8]}.pdf"},
    )


@app.websocket("/ws/{session_id}")
async def ws_handler(websocket: WebSocket, session_id: str):
    await websocket.accept()

    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    reqs = load_nis2_requirements()

    session = {
        "stage": "qualifier",
        "messages": [],
        "qualifier_result": None,
        "interview_findings": None,
        "gap_analysis": None,
        "redteam_result": None,
        "drafter_result": None,
        "threat_actor_result": None,
        "board_slides": None,
        "language": "en",
        "question_count": 0,
        "busy": False,
        "greeted": False,
        "demo_mode": False,
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
                        {"role": "user", "content": "Hello"},
                        {"role": "assistant", "content": greeting},
                    ]
                    session["last_question"] = greeting
                    await send({"type": "agent_message", "text": greeting, "stage": "qualifier"})
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

            user_text = data.get("text", "").strip()
            if not user_text or session["busy"]:
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
        if sessions.get(session_id, {}).get("stage") != "complete":
            sessions.pop(session_id, None)


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

        if COMPLETE_MARKER in text:
            idx = text.find(COMPLETE_MARKER)
            closing = text[:idx].strip()
            if closing:
                await send({"type": "agent_message", "text": closing, "stage": "interview"})
            try:
                findings = extract_json(text[idx + len(COMPLETE_MARKER):].strip())
                await _run_analysis_pipeline(findings, session, reqs, client, send)
            except ValueError:
                await send({"type": "error", "text": "Could not parse interview results."})
        else:
            _closing_words = {"dziękuję", "thank you", "podsumowując", "summary",
                              "za chwilę dostaniesz", "you'll receive", "dziękuje"}
            _looks_like_closing = (
                session["question_count"] >= 10
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
        thinking_text, text, content_blocks = await call_with_thinking(client, system, session["messages"], session=session)
        # Store full content blocks (with thinking) so conversation threading works
        session["messages"].append({"role": "assistant", "content": content_blocks})

        try:
            result = extract_json(text)
        except ValueError:
            result = None

        if result and "verdict" in result:
            # Show auditor's reasoning before the verdict — most interesting thinking to reveal
            if thinking_text:
                await send({"type": "thinking_reveal", "text": thinking_text[:2000]})
            pre_json = text[:text.find("{")].strip() if "{" in text else ""
            if pre_json:
                await send({"type": "agent_message", "text": pre_json, "stage": "redteam"})
            prep = text[text.rfind("}") + 1:].strip() if "}" in text else ""
            if prep:
                await send({"type": "agent_message", "text": prep, "stage": "redteam"})
            await send({
                "type": "agent_message",
                "text": "─── Audit simulation complete. Preparing your full report... ───",
                "stage": "redteam",
            })
            session["redteam_result"] = {"verdict": result, "preparation": prep}
            session["stage"] = "draft"
            await _run_drafter(session, client, send)
        else:
            if result:
                print(f"[redteam] unexpected JSON (no verdict key). Raw: {text[:200]}")
            await send({"type": "agent_message", "text": text, "stage": "redteam"})
            session["last_question"] = text
            if session.get("demo_mode"):
                await _do_demo_answer(client, session, reqs, text, send)


async def _handle_qualifier_result(parsed, session, reqs, client, send):
    session["qualifier_result"] = parsed
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

        seed = "Hi, I'm ready for the interview."
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
    lang = session["language"]

    await send({"type": "stage_change", "stage": "analyze", "label": "Analyzing"})
    if lang == "pl":
        analyzing_msg = "⏳ Analizuję Twoje odpowiedzi... to zajmie 30-60 sekund"
    else:
        analyzing_msg = "⏳ Analyzing your responses... this takes 30-60 seconds"
    await send({"type": "agent_message", "text": analyzing_msg, "stage": "analyze"})

    system = build_analyzer_system_with_thinking(findings, reqs, lang)
    messages = [{"role": "user", "content": "Please analyze these interview findings and produce the complete gap analysis."}]
    thinking_text, text, _ = await call_with_thinking(client, system, messages, session=session)
    try:
        gaps = extract_json(text)
        if "gaps" not in gaps:
            print(f"[analyzer] unexpected JSON (no gaps key). Raw: {text[:200]}")
            raise ValueError("no gaps key")
    except ValueError:
        print(f"[analyzer] parse error. Raw: {text[:200]}")
        await send({
            "type": "analysis_result",
            "data": {
                "overall_risk": "high",
                "headline": "Analysis could not be parsed — please try again",
                "gaps": [],
                "priority_3": [],
                "good_news": "",
                "board_summary": "",
            },
        })
        return

    # Reveal analyzer's reasoning before showing the gap analysis card
    if thinking_text:
        await send({"type": "thinking_reveal", "text": thinking_text[:2000]})
    session["gap_analysis"] = gaps
    await send({"type": "analysis_result", "data": gaps})
    await send({"type": "stage_change", "stage": "redteam", "label": "Audit Simulation"})
    session["stage"] = "redteam"

    system = build_redteam_system(gaps, session["qualifier_result"], lang)
    seed = "I'm ready for the inspection."
    session["messages"] = [{"role": "user", "content": seed}]
    thinking_text, q1, content_blocks = await call_with_thinking(client, system, session["messages"], session=session)
    session["messages"].append({"role": "assistant", "content": content_blocks})
    # Check if initial response already contains verdict (edge case)
    try:
        result = extract_json(q1)
        if "verdict" in result:
            session["redteam_result"] = {"verdict": result, "preparation": ""}
            await _run_drafter(session, client, send)
            return
    except ValueError:
        pass
    await send({"type": "agent_message", "text": q1, "stage": "redteam"})
    session["last_question"] = q1
    if session.get("demo_mode"):
        await _do_demo_answer(client, session, reqs, q1, send)


async def _run_drafter(session, client, send):
    await send({"type": "stage_change", "stage": "draft", "label": "Report"})

    system = build_drafter_system(
        session["gap_analysis"], session["qualifier_result"], session["language"]
    )
    messages = [{"role": "user", "content": "Please generate the policy outlines for the critical and high risk gaps."}]
    text = await stream_silent(client, system, messages, 4096)
    try:
        policies = extract_json(text)
        if "policies" not in policies:
            print(f"[drafter] unexpected JSON (no policies key). Raw: {text[:200]}")
            raise ValueError("no policies key")
    except ValueError:
        print(f"[drafter] parse error. Raw: {text[:200]}")
        await send({"type": "error", "text": "Could not generate policy drafts."})
        return
    session["drafter_result"] = policies

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
    _, text, _ = await call_with_thinking(
        client, system, messages, max_tokens=16000, budget_tokens=8000, session=session
    )
    try:
        threat_scenarios = extract_json(text)
        if "scenarios" not in threat_scenarios:
            print(f"[threat_actor] unexpected JSON (no scenarios key). Raw: {text[:200]}")
            threat_scenarios = {"scenarios": [], "summary": ""}
    except ValueError:
        print(f"[threat_actor] parse error. Raw: {text[:200]}")
        threat_scenarios = {"scenarios": [], "summary": ""}
    session["threat_actor_result"] = threat_scenarios

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
        board_slides = extract_json(text)
        if "slides" not in board_slides:
            print(f"[board_presenter] unexpected JSON (no slides key). Raw: {text[:200]}")
            board_slides = {"slides": []}
    except ValueError:
        print(f"[board_presenter] parse error. Raw: {text[:200]}")
        board_slides = {"slides": []}
    session["board_slides"] = board_slides

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
        },
    })
    session["stage"] = "complete"
