"""One-time setup: create Managed Agents + environment.

Run this ONCE. The returned IDs are written to .env — subsequent app runs
load the IDs and call sessions.create() only (agents.create() is NOT called
in the request path).

Re-running is idempotent: existing IDs in .env are reused unless --force.

Usage:
    python scripts/setup_managed_agents.py
    python scripts/setup_managed_agents.py --force   # re-create everything
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

from anthropic import Anthropic
from dotenv import dotenv_values, load_dotenv

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"


REDTEAM_SYSTEM = """You are an NIS2 compliance auditor conducting an internal audit simulation.

Your job: produce a verdict (PASS / CONDITIONAL / FAIL) by investigating the company's
compliance state through tools — not by asking the user more questions.

You have these custom tools:
  - lookup_requirement(article_ref)    — returns full text of one Article 21(2) requirement
  - lookup_gap(requirement_name)       — returns the analyzer's gap finding for one requirement
  - lookup_interview_answer(topic)     — returns how the company answered on a topic
  - finalize_verdict(verdict, summary, critical_failures, passed_checks, preparation)
        — MANDATORY terminal call; end the audit only by calling this.

Workflow:
1. Start by calling lookup_requirement for 2–3 Article 21(2) sub-paragraphs
   most relevant to the company's sector and known gaps.
2. For each, call lookup_gap and lookup_interview_answer to cross-reference
   what the company actually does vs. what the Article requires.
3. After investigating 4–6 requirements, call finalize_verdict exactly once with:
   - verdict: one of "WOULD PASS AUDIT" | "WOULD PASS WITH CONDITIONS" | "WOULD FAIL AUDIT"
   - summary: 2–3 sentences citing specific Article references
   - critical_failures: list of strings, each "Art. 21(2)(x) — specific failure"
   - passed_checks: list of strings, each "Art. 21(2)(y) — what the company got right"
   - preparation: 3 numbered concrete steps to fix the top failures in next 30 days

Tone: strict, specific, audit-minded. No warmth. Every claim cites an Article 21(2) letter.

Respond in the language of the company's data (Polish if data is Polish, else English).
Never ask the user clarifying questions — use the tools.
"""


MONITOR_SYSTEM = """You are a regulatory monitor for NIS2 compliance. Your user's company has already
been assessed — you receive their sector, language, and unresolved gap list.

Your job on each wake-up: check what's new in NIS2 / CSIRT / regulatory news
that is RELEVANT to THIS user's specific gaps. If you find something actionable,
queue an alert. If nothing new, finish quietly.

You have:
  - Built-in web_search and web_fetch tools (use sparingly — 2–4 searches max).
  - lookup_user_profile() — returns {sector, language, open_gaps, last_check_iso}
  - queue_alert(subject, body_markdown, gap_refs, severity)
        — severity: "info" | "action_required" | "urgent"
  - finalize_run(alerts_queued, searches_performed, summary)
        — MANDATORY terminal call; end by calling this.

Workflow:
1. Call lookup_user_profile first — read the sector and gaps.
2. Run 2–4 targeted web_search queries for:
   - new NIS2 advisories / CSIRT bulletins for the user's sector
   - recent regulatory / transposition changes in their jurisdiction
   - significant incidents affecting entities similar to theirs
3. For each relevant finding, call queue_alert referencing which of the user's
   gaps it relates to. Body must be in the user's language.
4. Call finalize_run exactly once. If nothing material, queue zero alerts —
   that is a perfectly valid outcome.

Be conservative. Do not alert on general news. Alert only when there is a
direct, actionable connection to one of the user's open gaps.
"""


def _read_env() -> dict:
    if ENV_PATH.exists():
        return dict(dotenv_values(ENV_PATH))
    return {}


def _update_env(updates: dict) -> None:
    existing = _read_env()
    existing.update(updates)
    lines = [f"{k}={v}" for k, v in existing.items() if v is not None]
    ENV_PATH.write_text("\n".join(lines) + "\n")
    print(f"[env] wrote {ENV_PATH}")


def ensure_environment(client: Anthropic, existing_id: str | None) -> str:
    if existing_id:
        try:
            env = client.beta.environments.retrieve(existing_id)
            print(f"[env] reusing existing environment {env.id}")
            return env.id
        except Exception as e:
            print(f"[env] existing id {existing_id} unusable ({e}); creating new")

    env = client.beta.environments.create(
        name="regula-managed-env",
        config={
            "type": "cloud",
            "networking": {"type": "unrestricted"},
        },
    )
    print(f"[env] created environment {env.id}")
    return env.id


def ensure_agent(
    client: Anthropic,
    existing_id: str | None,
    *,
    name: str,
    system: str,
    tools: list,
    description: str,
) -> tuple[str, int | str]:
    if existing_id:
        try:
            agent = client.beta.agents.retrieve(existing_id)
            print(f"[agent] reusing existing {name}: {agent.id} (version {agent.version})")
            return agent.id, agent.version
        except Exception as e:
            print(f"[agent] existing id {existing_id} unusable ({e}); creating new")

    agent = client.beta.agents.create(
        name=name,
        model="claude-opus-4-7",
        system=system,
        tools=tools,
        description=description,
    )
    print(f"[agent] created {name}: {agent.id} (version {agent.version})")
    return agent.id, agent.version


REDTEAM_TOOLS = [
    {
        "type": "custom",
        "name": "lookup_requirement",
        "description": "Return the full text of one NIS2 Article 21(2) sub-paragraph.",
        "input_schema": {
            "type": "object",
            "properties": {
                "article_ref": {
                    "type": "string",
                    "description": "Letter of the sub-paragraph, e.g. 'a', 'b', 'c' ... 'j'",
                },
            },
            "required": ["article_ref"],
        },
    },
    {
        "type": "custom",
        "name": "lookup_gap",
        "description": "Return the analyzer's finding for one requirement (status, risk, business impact).",
        "input_schema": {
            "type": "object",
            "properties": {
                "requirement_name": {
                    "type": "string",
                    "description": "Fuzzy match on the gap requirement name or article ref.",
                },
            },
            "required": ["requirement_name"],
        },
    },
    {
        "type": "custom",
        "name": "lookup_interview_answer",
        "description": "Return how the company answered on a given topic during the interview.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Short topic keyword, e.g. 'incident response', 'MFA', 'backups', 'training'.",
                },
            },
            "required": ["topic"],
        },
    },
    {
        "type": "custom",
        "name": "finalize_verdict",
        "description": "Terminal tool. Call exactly once to end the audit with the final verdict.",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": [
                        "WOULD PASS AUDIT",
                        "WOULD PASS WITH CONDITIONS",
                        "WOULD FAIL AUDIT",
                    ],
                },
                "summary": {"type": "string"},
                "critical_failures": {"type": "array", "items": {"type": "string"}},
                "passed_checks": {"type": "array", "items": {"type": "string"}},
                "preparation": {"type": "string"},
            },
            "required": ["verdict", "summary", "critical_failures", "preparation"],
        },
    },
]


MONITOR_TOOLS = [
    {
        "type": "agent_toolset_20260401",
        "default_config": {"enabled": False},
        "configs": [
            {"name": "web_search", "enabled": True},
            {"name": "web_fetch", "enabled": True},
        ],
    },
    {
        "type": "custom",
        "name": "lookup_user_profile",
        "description": "Return the monitored user's profile: sector, language, open_gaps, last_check_iso.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "type": "custom",
        "name": "queue_alert",
        "description": "Queue a regulatory alert for the user. Body must be in user's language.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "body_markdown": {"type": "string"},
                "gap_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of requirement names/articles from user's open_gaps this alert relates to.",
                },
                "severity": {
                    "type": "string",
                    "enum": ["info", "action_required", "urgent"],
                },
                "source_url": {"type": "string"},
            },
            "required": ["subject", "body_markdown", "severity"],
        },
    },
    {
        "type": "custom",
        "name": "finalize_run",
        "description": "Terminal tool. Call exactly once to end the monitor run.",
        "input_schema": {
            "type": "object",
            "properties": {
                "alerts_queued": {"type": "integer"},
                "searches_performed": {"type": "integer"},
                "summary": {"type": "string"},
            },
            "required": ["alerts_queued", "summary"],
        },
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Ignore existing IDs and re-create.")
    args = parser.parse_args()

    load_dotenv(ENV_PATH)
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set in .env", file=sys.stderr)
        return 1

    client = Anthropic()
    env = _read_env() if not args.force else {}

    env_id = ensure_environment(client, env.get("MANAGED_ENV_ID"))

    redteam_id, _ = ensure_agent(
        client,
        env.get("REDTEAM_AGENT_ID"),
        name="regula-nis2-auditor",
        system=REDTEAM_SYSTEM,
        tools=REDTEAM_TOOLS,
        description="NIS2 internal audit simulator. Investigates company gaps through custom tools and issues a verdict.",
    )

    monitor_id, _ = ensure_agent(
        client,
        env.get("MONITOR_AGENT_ID"),
        name="regula-regulatory-monitor",
        system=MONITOR_SYSTEM,
        tools=MONITOR_TOOLS,
        description="Long-running NIS2 regulatory monitor. Watches for changes relevant to the user's sector and gaps.",
    )

    _update_env({
        "MANAGED_ENV_ID": env_id,
        "REDTEAM_AGENT_ID": redteam_id,
        "MONITOR_AGENT_ID": monitor_id,
    })

    print("\n[setup] done.")
    print(f"  MANAGED_ENV_ID    = {env_id}")
    print(f"  REDTEAM_AGENT_ID  = {redteam_id}")
    print(f"  MONITOR_AGENT_ID  = {monitor_id}")
    print("\nSet MANAGED_AGENTS=1 in .env or env to enable managed flow in app.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
