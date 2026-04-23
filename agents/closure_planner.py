import json
import pathlib

_DIRECTIVE_PATH = pathlib.Path(__file__).parent.parent / "data" / "frameworks" / "nis2_directive.json"

# Module-level cache — computed once per process lifetime.
_STATIC_BLOCK: str | None = None


def _load_art21_measures() -> list:
    if _DIRECTIVE_PATH.exists():
        data = json.loads(_DIRECTIVE_PATH.read_text())
        return data.get("article_21_measures", {}).get("measures", [])
    return []


def _get_static_block() -> str:
    global _STATIC_BLOCK
    if _STATIC_BLOCK is not None:
        return _STATIC_BLOCK

    measures = _load_art21_measures()
    if measures:
        art21_lines = [
            "Article 21(2) of Directive (EU) 2022/2555 — the 10 requirements whose gaps you are closing:",
        ]
        for m in measures:
            art21_lines.append(f"  Art. 21(2)({m['id']}) — {m['text']}")
        art21_ref = "\n".join(art21_lines)
    else:
        art21_ref = "(Article 21 directive text not available)"

    _STATIC_BLOCK = f"""You are a NIS2 closure engineer. You are NOT writing a report or a consulting deliverable — you are writing an operations runbook that a real IT admin executes Tuesday morning, step by step.

## Legal reference:
{art21_ref}

## Your job
For each of the top gaps you are given, produce a day-by-day closure plan specific to the company's actual tech stack. No generic "implement MFA" advice — exact admin URLs, exact commands, exact verification steps.

## Stack detection — non-negotiable
Before writing the plan for each gap, infer the company's stack from the interview key_quotes and transcript excerpt you are given.

Match hints to stacks:
- "Gmail", "Google", "Workspace", "G Suite", "Google Drive" → Google Workspace
- "Outlook", "Office 365", "Microsoft 365", "O365", "Teams", "SharePoint", "OneDrive" → Microsoft 365
- "Okta", "Auth0", "OneLogin" → dedicated IdP
- "Slack", "Discord" → chat
- "Jira", "Linear", "Asana", "Monday" → task tracking
- "AWS", "Azure", "GCP" → cloud
- "on-prem", "own server", "data center", "w serwerowni" → on-premises

Confidence levels:
- high: explicit mention of a specific product
- medium: domain or generic brand mention without clear version
- low: no stack signals at all — in this case, write a generic plan and say so in `stack_disclaimer`

Never fabricate a stack. If you guess, say you are guessing in `stack_disclaimer`.

## Day-sequencing rules
- 7 to 14 days total per plan. Never longer.
- Maximum 2 concrete steps per day. No step should take more than 2 hours.
- Day 1-2: setup in admin panel, pilot group of 3-5 people.
- Day 3-7: phased rollout to the rest of the company.
- Day 8-14: verification, documentation, integration with other policies.
- Each step must include a `verification` field — a concrete way to check it actually worked.

## Stack-specific URL library — use ONLY these (do not invent):

### Google Workspace
- Admin console: https://admin.google.com
- 2-Step Verification: https://admin.google.com/ac/security/2sv
- Security dashboard: https://admin.google.com/ac/security
- Backup / Vault: https://vault.google.com
- User groups / OU: https://admin.google.com/ac/ou
- Reports / audit log: https://admin.google.com/ac/reporting

### Microsoft 365 / Entra ID
- Admin center: https://admin.microsoft.com
- Conditional Access / MFA: https://entra.microsoft.com/#view/Microsoft_AAD_ConditionalAccess
- Security center: https://security.microsoft.com
- Compliance center: https://compliance.microsoft.com
- Backup (via Purview): https://compliance.microsoft.com
- PowerShell for Entra: `Connect-MgGraph -Scopes "User.ReadWrite.All"`

### Generic (unknown stack) — say so
- "Check with your IT provider" or "Consult your admin panel documentation"

If the inferred stack is not in the library, fall back to Generic and flag it.

## Templates — pre-drafted, copy-paste ready
Every plan must include:
- `board_email`: 5-8 sentences. Subject line + body. Includes the specific EUR budget request and the legal reference.
- `team_announcement`: 3-5 sentences, casual tone. Tells the team what is happening, when, and what they need to do.

## Definition of Done
Objective, checkable bullets. Not "fully deployed" — "100% of users show enrolled in 2SV report, verified in admin.google.com/ac/reporting".

## Output — ONLY valid JSON, no text before or after:
{{
  "closure_plans": [
    {{
      "gap_id": 1,
      "article_ref": "Article 21(2)(x) — name",
      "gap_name_plain": "One-line plain language name of the gap",
      "detected_stack": {{
        "identity": "Google Workspace | Microsoft 365 | Okta | Unknown",
        "email": "same",
        "evidence": "Short quote from interview that led to this inference",
        "confidence": "high | medium | low"
      }},
      "stack_disclaimer": "If stack is Unknown or low confidence, tell the user how to adapt. Empty string otherwise.",
      "timeline_days": 10,
      "total_effort_hours": 6,
      "cost_eur_range": "0-200",
      "owner_role": "IT Administrator / Office Manager / CEO — whoever fits a company this size",
      "days": [
        {{
          "day": 1,
          "duration_min": 20,
          "title": "Short action title — verb-first",
          "steps": [
            "Concrete step with exact URL or command",
            "Second step if needed"
          ],
          "verification": "How you know this step actually worked — one sentence"
        }}
      ],
      "board_email": "Subject: ...\\n\\nDear board,\\n\\n...(5-8 sentences, specific budget in EUR, timeline, legal ref)",
      "team_announcement": "Hi team, starting Monday we are enabling X. Here is what you need to do: ...",
      "definition_of_done": [
        "Objective, verifiable bullet 1",
        "Objective, verifiable bullet 2",
        "Objective, verifiable bullet 3"
      ]
    }}
  ]
}}

Generate exactly one closure plan per gap you receive (top 3 critical/high gaps). Keep the JSON valid and complete — no trailing commas, no comments inside JSON.
"""
    return _STATIC_BLOCK


def _serialize_transcript_excerpt(messages: list, max_turns: int = 40) -> str:
    """Trim the interview transcript to the first N turns for stack detection."""
    if not messages:
        return "(no transcript available)"
    lines = []
    for m in messages[:max_turns]:
        role = m.get("role", "?")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
            )
        if not isinstance(content, str):
            content = str(content)
        # Trim each message to avoid bloating the prompt
        content = content.strip().replace("\n", " ")
        if len(content) > 300:
            content = content[:300] + "..."
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def build_closure_planner_system(
    top_gaps: list,
    key_quotes: list,
    transcript_excerpt: list,
    company_profile: dict,
    language: str,
) -> list[dict]:
    static_block = _get_static_block()
    lang_instruction = "Polish (język polski)" if language == "pl" else "English"

    transcript_text = _serialize_transcript_excerpt(transcript_excerpt)
    quotes_text = "\n".join(f"- \"{q}\"" for q in (key_quotes or [])) or "(no key quotes captured)"
    gaps_text = json.dumps(top_gaps, ensure_ascii=False, indent=2)

    dynamic_block = (
        f"RESPOND ENTIRELY IN {lang_instruction}. All text fields in the JSON must be in this language. "
        f"This includes: gap_name_plain, stack_disclaimer, evidence, title, steps, verification, "
        f"board_email, team_announcement, definition_of_done, owner_role.\n"
        f"The stack identity field (Google Workspace / Microsoft 365 / Okta / Unknown) stays in English "
        f"because those are product names.\n\n"
        f"## Company profile:\n{json.dumps(company_profile, ensure_ascii=False, indent=2)}\n\n"
        f"## Top gaps to close (one plan per gap):\n{gaps_text}\n\n"
        f"## Interview key quotes (mine for stack signals):\n{quotes_text}\n\n"
        f"## Interview transcript excerpt (first 40 turns — more stack signals may be here):\n{transcript_text}"
    )

    return [
        {"type": "text", "text": static_block, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": dynamic_block},
    ]
