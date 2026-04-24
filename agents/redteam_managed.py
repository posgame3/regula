"""Managed-Agents implementation of the Red Team auditor.

The agent runs on Anthropic's orchestration layer (we do not drive the loop).
We host the tool implementations client-side: the agent emits
`agent.custom_tool_use` events, we look up data from session_data, and reply
with `user.custom_tool_result`.

Entry point: run_managed_audit(client, agent_id, env_id, session_data, send_ws)
Returns: {"verdict": {...}, "preparation": str} in the same shape the existing
non-managed flow produces, so the rest of the pipeline (drafter, PDF) is unchanged.
"""
from __future__ import annotations

import asyncio
import difflib
import json
import logging
import pathlib
from typing import Any, Awaitable, Callable

from anthropic import AsyncAnthropic

from utils import metrics

log = logging.getLogger("regula")

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
_DIRECTIVE_PATH = BASE_DIR / "data" / "frameworks" / "nis2_directive.json"


# ───────────────────── Tool implementations (host-side) ─────────────────────


def _load_article_21_measures() -> list[dict]:
    if not _DIRECTIVE_PATH.exists():
        return []
    data = json.loads(_DIRECTIVE_PATH.read_text())
    return data.get("article_21_measures", {}).get("measures", [])


_MEASURES = _load_article_21_measures()


def tool_lookup_requirement(article_ref: str) -> dict:
    ref = article_ref.lower().strip().strip("()")
    ref = ref.replace("art.", "").replace("21(2)", "").strip("() ")
    for m in _MEASURES:
        if m.get("id", "").lower() == ref:
            return {
                "article": f"Art. 21(2)({m['id']}) — Directive (EU) 2022/2555",
                "text": m.get("text", "").strip(),
            }
    return {
        "error": f"No Article 21(2) sub-paragraph matches '{article_ref}'. Valid letters: a–j.",
        "available": [m.get("id") for m in _MEASURES],
    }


def tool_lookup_gap(requirement_name: str, session_data: dict) -> dict:
    gaps = (session_data.get("gap_analysis") or {}).get("gaps") or []
    if not gaps:
        return {"error": "No gap analysis available."}

    q = requirement_name.lower()
    # Score each gap by substring overlap with requirement name or article ref.
    scored = []
    for gap in gaps:
        name = (gap.get("requirement") or gap.get("name") or "").lower()
        article = (gap.get("article_ref") or gap.get("article") or "").lower()
        score = max(
            _similarity(q, name),
            _similarity(q, article),
            1.0 if q in name or q in article else 0.0,
        )
        scored.append((score, gap))
    scored.sort(key=lambda x: x[0], reverse=True)
    top_score, top = scored[0]
    if top_score < 0.3:
        return {
            "error": f"No gap matches '{requirement_name}' well.",
            "available_requirements": [g.get("requirement") or g.get("name") for g in gaps],
        }
    return {
        "requirement": top.get("requirement") or top.get("name"),
        "article_ref": top.get("article_ref") or top.get("article"),
        "status": top.get("status"),
        "risk_level": top.get("risk_level"),
        "what_to_do": top.get("what_to_do"),
        "business_impact": top.get("business_impact"),
        "estimated_effort": top.get("estimated_effort"),
        "estimated_cost": top.get("estimated_cost"),
    }


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def tool_lookup_interview_answer(topic: str, session_data: dict) -> dict:
    findings = session_data.get("interview_findings") or {}
    if not findings:
        return {"error": "No interview findings available."}

    topic_lower = topic.lower()
    matches: list[dict] = []

    # 1. Direct key matches
    for key, val in findings.items():
        if key in ("messages", "key_quotes", "biggest_concern"):
            continue
        if topic_lower in key.lower() or (isinstance(val, str) and topic_lower in val.lower()):
            matches.append({"field": key, "value": val})

    # 2. Key quotes that mention the topic
    key_quotes = findings.get("key_quotes") or []
    if isinstance(key_quotes, list):
        for q in key_quotes:
            qstr = q if isinstance(q, str) else json.dumps(q, ensure_ascii=False)
            if topic_lower in qstr.lower():
                matches.append({"quote": qstr})

    # 3. Biggest concern
    bc = findings.get("biggest_concern")
    if isinstance(bc, str) and topic_lower in bc.lower():
        matches.append({"biggest_concern": bc})

    if not matches:
        # Still give a structured snapshot so the auditor has something to reason on.
        return {
            "note": f"No direct mention of '{topic}'. Snapshot of findings follows.",
            "company_name": findings.get("company_name"),
            "sector": findings.get("sector"),
            "size": findings.get("size"),
            "biggest_concern": findings.get("biggest_concern"),
            "key_quotes_preview": (key_quotes[:3] if isinstance(key_quotes, list) else []),
        }

    return {"matches": matches[:8]}


# ────────────────────────── Session runner ──────────────────────────


AuditWsSend = Callable[[dict], Awaitable[None]]


async def run_managed_audit(
    client: AsyncAnthropic,
    *,
    agent_id: str,
    env_id: str,
    session_data: dict,
    send_ws: AuditWsSend | None = None,
) -> dict:
    """Run one audit session end-to-end. Returns the redteam_result dict.

    Emits 'auditor_step' ws events as tools are invoked so the UI can show
    the auditor thinking/working live.
    """
    lang = session_data.get("language", "en")
    company_profile = session_data.get("qualifier_result") or {}
    gap_analysis = session_data.get("gap_analysis") or {}

    # Create a session under the pre-created agent. Agent has system prompt + tools.
    session = await client.beta.sessions.create(
        agent=agent_id,
        environment_id=env_id,
        title=f"NIS2 audit — {session_data.get('session_id', 'unknown')[:8]}",
    )

    # Build kickoff message with context the auditor needs.
    kickoff = _build_kickoff_message(company_profile, gap_analysis, lang)

    # Open stream FIRST, then send kickoff (stream-first ordering — docs Pattern 7).
    # We use async context manager + a task for sending.
    verdict_payload: dict | None = None

    stream = await client.beta.sessions.events.stream(session_id=session.id)
    async with stream:
        await client.beta.sessions.events.send(
            session_id=session.id,
            events=[{
                "type": "user.message",
                "content": [{"type": "text", "text": kickoff}],
            }],
        )

        try:
            async with asyncio.timeout(300):
                async for event in stream:
                    etype = getattr(event, "type", None)

                    if etype == "agent.custom_tool_use":
                        tool_name = getattr(event, "name", None) or getattr(event, "tool_name", None)
                        tool_input = getattr(event, "input", {}) or {}
                        tool_use_id = getattr(event, "id", None)

                        metrics.incr_managed_tool(f"redteam.{tool_name}" if tool_name else "redteam.unknown")

                        # UI progress event
                        if send_ws:
                            await send_ws({
                                "type": "auditor_step",
                                "tool": tool_name,
                                "input": tool_input,
                                "stage": "redteam",
                            })

                        # Dispatch tool — may capture terminal verdict
                        result_payload = _dispatch_tool(tool_name, tool_input, session_data)
                        if tool_name == "finalize_verdict":
                            verdict_payload = tool_input  # capture the full verdict input
                            result_payload = {"ok": True, "verdict_recorded": True}

                        await client.beta.sessions.events.send(
                            session_id=session.id,
                            events=[{
                                "type": "user.custom_tool_result",
                                "custom_tool_use_id": tool_use_id,
                                "content": [{
                                    "type": "text",
                                    "text": json.dumps(result_payload, ensure_ascii=False),
                                }],
                            }],
                        )
                        continue

                    if etype == "session.status_terminated":
                        break

                    if etype == "session.status_idle":
                        stop_reason = getattr(event, "stop_reason", None)
                        stop_type = getattr(stop_reason, "type", None) if stop_reason else None
                        if stop_type == "requires_action":
                            # still waiting on us; don't break
                            continue
                        # end_turn or retries_exhausted — we're done
                        break
        except asyncio.TimeoutError:
            log.error("[managed-audit] stream timed out after 300s — triggering legacy fallback")
            raise ValueError("managed audit timed out")

    # Post-idle settle: wait until sessions.retrieve shows non-running
    await _wait_until_not_running(client, session.id)
    try:
        await client.beta.sessions.archive(session_id=session.id)
    except Exception:
        pass

    if verdict_payload is None:
        # Agent gave up or crashed — return a safe fallback so drafter still runs.
        return {
            "verdict": {
                "verdict": "WOULD FAIL AUDIT",
                "auditor_summary": (
                    "Audyt zakończony bez werdyktu — audytor przerwał sesję."
                    if lang == "pl"
                    else "Audit ended without a verdict — auditor session terminated early."
                ),
                "critical_failures": [],
            },
            "preparation": "",
        }

    return _build_redteam_result(verdict_payload)


async def _wait_until_not_running(client: AsyncAnthropic, session_id: str, *, max_wait_s: float = 10.0):
    """Pattern 6 — post-idle status-write race. Poll until the session leaves 'running'.

    Bumped from 2s to 10s so network jitter on Anthropic's side doesn't cause us to
    archive a still-running session (which would orphan tokens and break finalize).
    """
    delay = 0.25
    waited = 0.0
    while waited < max_wait_s:
        try:
            s = await client.beta.sessions.retrieve(session_id=session_id)
            if getattr(s, "status", "") != "running":
                return
        except Exception:
            return
        await asyncio.sleep(delay)
        waited += delay


def _dispatch_tool(name: str | None, raw_input: dict, session_data: dict) -> dict:
    """Return the payload the agent sees as the tool result.
    Terminal capture of finalize_verdict is handled by the caller."""
    if name == "lookup_requirement":
        return tool_lookup_requirement(raw_input.get("article_ref", ""))
    if name == "lookup_gap":
        return tool_lookup_gap(raw_input.get("requirement_name", ""), session_data)
    if name == "lookup_interview_answer":
        return tool_lookup_interview_answer(raw_input.get("topic", ""), session_data)
    if name == "finalize_verdict":
        return {"ok": True, "verdict_recorded": True}
    return {"error": f"Unknown tool: {name}"}


def _build_kickoff_message(company_profile: dict, gap_analysis: dict, lang: str) -> str:
    """Seed message sent to the auditor agent. Includes the data it will cross-reference."""
    lang_note = "Polish" if lang == "pl" else "English"
    profile_json = json.dumps(company_profile, ensure_ascii=False, indent=2)
    gaps_compact = {
        "overall_risk": gap_analysis.get("overall_risk"),
        "headline": gap_analysis.get("headline"),
        "gaps": [
            {
                "requirement": g.get("requirement") or g.get("name"),
                "article_ref": g.get("article_ref") or g.get("article"),
                "status": g.get("status"),
                "risk_level": g.get("risk_level"),
            }
            for g in (gap_analysis.get("gaps") or [])
        ],
    }
    gaps_json = json.dumps(gaps_compact, ensure_ascii=False, indent=2)
    return (
        f"Company profile (NIS2 qualifier output):\n{profile_json}\n\n"
        f"Gap-analysis summary (only the index — use lookup_gap to drill):\n{gaps_json}\n\n"
        f"Respond in {lang_note}. Begin the audit now. "
        f"Remember: investigate via tools, then call finalize_verdict. "
        f"Do not ask the user follow-up questions."
    )


def _build_redteam_result(verdict_payload: dict) -> dict:
    """Shape returned by finalize_verdict → what the rest of the app expects."""
    return {
        "verdict": {
            "verdict": verdict_payload.get("verdict") or "WOULD FAIL AUDIT",
            "auditor_summary": verdict_payload.get("summary") or "",
            "critical_failures": verdict_payload.get("critical_failures") or [],
            "passed_checks": verdict_payload.get("passed_checks") or [],
        },
        "preparation": verdict_payload.get("preparation") or "",
    }
