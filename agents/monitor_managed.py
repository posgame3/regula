"""Managed-Agents implementation of the on-demand Regulatory Monitor.

User-triggered: invoked by POST /api/monitor/run from the in-app mailbox after
a user subscribes with their email. Agent uses built-in web_search / web_fetch
plus custom tools to query the user's profile and queue alerts.
Terminal tool: finalize_run.

No scheduler, no SMTP delivery — the "subscription" is a saved monitoring
profile, not a push subscription. APScheduler + SMTP would be the natural
next step to turn this into a true background service (out of scope for this
release).
"""
from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable

from anthropic import AsyncAnthropic

from utils import metrics, profile_store


MonitorWsSend = Callable[[dict], Awaitable[None]]


async def run_managed_monitor(
    client: AsyncAnthropic,
    *,
    agent_id: str,
    env_id: str,
    user_id: str,
    send_ws: MonitorWsSend | None = None,
) -> dict:
    """Run one monitor pass for user_id. Returns the run summary.

    Emits 'monitor_step' ws events for live UI updates.
    """
    profile = profile_store.get_profile(user_id)
    if not profile:
        raise ValueError(f"No profile for user_id={user_id}")

    session = await client.beta.sessions.create(
        agent=agent_id,
        environment_id=env_id,
        title=f"monitor — {profile.get('company_name') or user_id[:12]}",
    )

    kickoff = _build_kickoff(profile)
    final_summary: dict | None = None
    alerts_queued: list[dict] = []
    searches_seen = 0

    stream = await client.beta.sessions.events.stream(session_id=session.id)
    async with stream:
        await client.beta.sessions.events.send(
            session_id=session.id,
            events=[{
                "type": "user.message",
                "content": [{"type": "text", "text": kickoff}],
            }],
        )

        async for event in stream:
            etype = getattr(event, "type", None)

            if etype == "agent.tool_use":
                # Built-in tools (web_search / web_fetch) run server-side — we just observe.
                tool_name = getattr(event, "name", None) or getattr(event, "tool_name", None)
                if tool_name == "web_search":
                    searches_seen += 1
                metrics.incr_managed_tool(f"monitor.{tool_name}" if tool_name else "monitor.unknown")
                if send_ws:
                    inp = getattr(event, "input", {}) or {}
                    await send_ws({
                        "type": "monitor_step",
                        "tool": tool_name,
                        "input": inp,
                        "source": "builtin",
                    })
                continue

            if etype == "agent.custom_tool_use":
                tool_name = getattr(event, "name", None) or getattr(event, "tool_name", None)
                tool_input = getattr(event, "input", {}) or {}
                tool_use_id = getattr(event, "id", None)

                metrics.incr_managed_tool(f"monitor.{tool_name}" if tool_name else "monitor.unknown")

                if send_ws:
                    await send_ws({
                        "type": "monitor_step",
                        "tool": tool_name,
                        "input": tool_input,
                        "source": "custom",
                    })

                if tool_name == "lookup_user_profile":
                    result_payload = _sanitize_profile_for_agent(profile)
                elif tool_name == "queue_alert":
                    alert = _queue_alert(user_id, tool_input)
                    alerts_queued.append(alert)
                    result_payload = {"ok": True, "alert_id": alert["id"]}
                elif tool_name == "finalize_run":
                    final_summary = dict(tool_input)
                    result_payload = {"ok": True, "recorded": True}
                else:
                    result_payload = {"error": f"Unknown tool: {tool_name}"}

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
                    continue
                break

    await _wait_until_not_running(client, session.id)
    try:
        await client.beta.sessions.archive(session_id=session.id)
    except Exception:
        pass

    profile_store.mark_checked(user_id)

    return {
        "user_id": user_id,
        "alerts_queued": len(alerts_queued),
        "alerts": alerts_queued,
        "searches_performed": searches_seen,
        "summary": (final_summary or {}).get("summary") or "",
        "session_id": session.id,
    }


async def _wait_until_not_running(client: AsyncAnthropic, session_id: str, *, max_wait_s: float = 2.0):
    delay = 0.15
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


def _sanitize_profile_for_agent(profile: dict) -> dict:
    """Expose only fields the agent should see (not email addresses)."""
    return {
        "sector": profile.get("sector"),
        "language": profile.get("language"),
        "company_name": profile.get("company_name"),
        "open_gaps": profile.get("open_gaps") or [],
        "last_check_iso": profile.get("last_check_iso"),
    }


def _queue_alert(user_id: str, tool_input: dict) -> dict:
    alert = {
        "subject": tool_input.get("subject") or "(no subject)",
        "body_markdown": tool_input.get("body_markdown") or "",
        "gap_refs": tool_input.get("gap_refs") or [],
        "severity": tool_input.get("severity") or "info",
        "source_url": tool_input.get("source_url"),
    }
    saved = profile_store.append_alert(user_id, alert)
    return saved or alert


def _build_kickoff(profile: dict) -> str:
    lang = profile.get("language") or "en"
    return (
        f"Wake up. It's a scheduled regulatory-monitor run. "
        f"Language of output: {lang} (pl=Polish, en=English). "
        f"Follow your system prompt: call lookup_user_profile first, then run 2–4 targeted "
        f"web_search queries for NIS2 / CSIRT / regulatory news relevant to THIS user's "
        f"sector and open gaps, then queue alerts (only when genuinely actionable), then finalize_run. "
        f"Be conservative — zero alerts is acceptable if nothing material found."
    )
