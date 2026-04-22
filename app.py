import json
import os
import re
from pathlib import Path

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

load_dotenv()

from agents.qualifier import build_qualifier_system
from agents.interviewer import build_interview_system
from agents.analyzer import build_analyzer_system, build_analyzer_system_with_thinking
from agents.redteam import build_redteam_system
from agents.drafter import build_drafter_system

app = FastAPI()
MODEL = "claude-opus-4-7"
COMPLETE_MARKER = "[INTERVIEW_COMPLETE]"
sessions: dict = {}

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
    """Stream tokens to UI via send callback. Returns full collected text."""
    full_text = ""
    async with client.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    ) as stream:
        async for token in stream.text_stream:
            full_text += token
            await send({"type": "stream_token", "text": token, "stage": stage})
    return full_text


async def stream_silent(client: AsyncAnthropic, system: str, messages: list, max_tokens: int) -> str:
    """Stream without sending tokens to UI. Returns full collected text."""
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
) -> tuple[str, str, list]:
    """Call with extended thinking enabled. Returns (thinking_text, result_text, full_content_blocks)."""
    response = await client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        thinking={"type": "enabled", "budget_tokens": budget_tokens},
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


@app.get("/")
async def index():
    return HTMLResponse(Path("static/index.html").read_text(encoding="utf-8"))


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
        "language": "en",
        "question_count": 0,
        "busy": False,
        "greeted": False,
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
                    await send({"type": "agent_message", "text": greeting, "stage": "qualifier"})
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
        sessions.pop(session_id, None)


async def _dispatch(client, session, reqs, user_text, send):
    stage = session["stage"]
    session["messages"].append({"role": "user", "content": user_text})

    if stage == "qualifier":
        text = await stream_to_ws(client, build_qualifier_system(session["language"]), session["messages"], 1024, send, "qualifier")
        session["messages"].append({"role": "assistant", "content": text})
        try:
            parsed = extract_json(text)
            if "applies" in parsed:
                # Streamed text was JSON — remove bubble before transitioning
                await send({"type": "stream_abort"})
                await _handle_qualifier_result(parsed, session, reqs, client, send)
            else:
                await send({"type": "stream_end", "stage": "qualifier"})
        except ValueError:
            await send({"type": "stream_end", "stage": "qualifier"})

    elif stage == "interview":
        system = build_interview_system(session["qualifier_result"], reqs, session["question_count"], session["language"])
        text = await stream_to_ws(client, system, session["messages"], 2048, send, "interview")
        session["messages"].append({"role": "assistant", "content": text})
        session["question_count"] += 1

        if COMPLETE_MARKER in text:
            idx = text.find(COMPLETE_MARKER)
            closing = text[:idx].strip()
            # Replace bubble with just the closing message, stripping marker + JSON
            if closing:
                await send({"type": "stream_replace", "text": closing, "stage": "interview"})
            else:
                await send({"type": "stream_abort"})
            await send({"type": "stream_end", "stage": "interview"})
            try:
                findings = extract_json(text[idx + len(COMPLETE_MARKER):].strip())
                await _run_analysis_pipeline(findings, session, reqs, client, send)
            except ValueError:
                await send({"type": "error", "text": "Could not parse interview results."})
        else:
            await send({"type": "stream_end", "stage": "interview"})

    elif stage == "redteam":
        system = build_redteam_system(
            session["gap_analysis"], session["qualifier_result"], session["language"]
        )
        thinking_text, text, content_blocks = await call_with_thinking(client, system, session["messages"])
        # Store full content blocks (with thinking) so conversation threading works
        session["messages"].append({"role": "assistant", "content": content_blocks})

        verdict, prep = parse_after_json(text)
        if verdict and "verdict" in verdict:
            # Show auditor's reasoning before the verdict — most interesting thinking to reveal
            if thinking_text:
                await send({"type": "thinking_reveal", "text": thinking_text[:2000]})
            pre_json = text[:text.find("{")].strip() if "{" in text else ""
            if pre_json:
                await send({"type": "agent_message", "text": pre_json, "stage": "redteam"})
            session["redteam_result"] = {"verdict": verdict, "preparation": prep}
            await _run_drafter(session, client, send)
        else:
            await send({"type": "agent_message", "text": text, "stage": "redteam"})


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
        await send({"type": "stream_end", "stage": "interview"})


async def _run_analysis_pipeline(findings, session, reqs, client, send):
    session["interview_findings"] = findings
    lang = session["language"]

    await send({"type": "stage_change", "stage": "analyze", "label": "Analyzing"})

    system = build_analyzer_system_with_thinking(findings, reqs, lang)
    messages = [{"role": "user", "content": "Please analyze these interview findings and produce the complete gap analysis."}]
    thinking_text, text, _ = await call_with_thinking(client, system, messages)
    try:
        gaps = extract_json(text)
    except ValueError:
        await send({"type": "error", "text": "Could not parse gap analysis."})
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
    thinking_text, q1, content_blocks = await call_with_thinking(client, system, session["messages"])
    session["messages"].append({"role": "assistant", "content": content_blocks})
    await send({"type": "agent_message", "text": q1, "stage": "redteam"})


async def _run_drafter(session, client, send):
    await send({"type": "stage_change", "stage": "draft", "label": "Report"})

    system = build_drafter_system(
        session["gap_analysis"], session["qualifier_result"], session["language"]
    )
    messages = [{"role": "user", "content": "Please generate the policy outlines for the critical and high risk gaps."}]
    text = await stream_silent(client, system, messages, 4096)
    try:
        policies = extract_json(text)
    except ValueError:
        await send({"type": "error", "text": "Could not generate policy drafts."})
        return

    session["drafter_result"] = policies
    await send({
        "type": "complete",
        "data": {
            "qualifier_result": session["qualifier_result"],
            "interview_findings": session["interview_findings"],
            "gap_analysis": session["gap_analysis"],
            "redteam_result": session["redteam_result"],
            "drafter_result": policies,
            "language": session["language"],
        },
    })
