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
        art21_lines = ["Article 21(2) of Directive (EU) 2022/2555 — the 10 requirements underlying all gaps in this presentation:"]
        for m in measures:
            art21_lines.append(f"  Art. 21(2)({m['id']}) — {m['text']}")
        art21_ref = "\n".join(art21_lines)
    else:
        art21_ref = "(Article 21 directive text not available)"

    _STATIC_BLOCK = f"""You generate a 5-slide executive presentation for a non-technical CEO/board.

## Legal context for slides:
{art21_ref}

## Score formula:
Start at 100. Subtract 15 for each critical gap, 8 for each high gap, 3 for each medium gap.
Minimum score: 5. Never show a score of 0.

## Slide-by-slide guidance:
- Slide 1: Make NIS2 concrete — use the company's sector to explain what's at stake (fines up to €10M or 2% global revenue, plus operational disruption)
- Slide 2: Score with context — explain what it means for their specific sector and size
- Slide 3: 30-day actions — specific, owned, costed. Each action should map to an Art. 21(2) sub-paragraph
- Slide 4: Numbers only — actual EUR estimates from the gap analysis, not ranges if avoidable
- Slide 5: One clear board-level ask — budget approval, hire decision, or vendor engagement

## NIS2 penalty regime — cite in Slide 1 and Slide 4:
Under Article 32/34 of Directive (EU) 2022/2555:
- Essential entities (energy, transport, health, banking, digital infrastructure, water, Annex I): administrative fines up to €10,000,000 or 2% of total worldwide annual turnover, whichever is higher
- Important entities (postal, waste, manufacturing, food, chemicals, research, digital providers, Annex II): fines up to €7,000,000 or 1.4% of total worldwide annual turnover
- Senior management personal liability: temporary prohibition from exercising managerial functions (Art. 32(7))
- Supervisory authority may impose: binding instructions, mandatory security audits, public disclosure of the incident
- Enforcement timeline: member states are required to apply NIS2 from October 2024 — supervisory visits are actively beginning

## Slide quality criteria:
- Slide 1 bullets: explain NIS2 in terms of this company's sector (healthcare → patient data, transport → operational continuity, etc.)
- Slide 2 score: calculate exactly using formula (100 - 15×critical - 8×high - 3×medium), never round to 0 or 100
- Slide 3 actions: each action must name the responsible person by job title (not "management"), a realistic EUR cost range (show DIY/in-house cost first, then external consultant cost — many NIS2 fixes cost €0–500 in-house), and time commitment in days not months
- Slide 4 numbers: split cost_of_action into DIY range (company does it internally) and external range (hired consultant). Most MFA, backup, and policy fixes can be done in-house for under €1,000. Use actual estimates from the gap analysis for inaction: both the fine exposure AND the realistic incident recovery cost for this sector
- Slide 5 recommendation: one sentence, specific ask, includes a success metric ("within 30 days", "by Q3", "hire one person")

## Rules:
- Plain language only. Board members are non-technical.
- Every bullet must be specific to THIS company (use their sector, size, actual gaps)
- Speaker notes are what the presenter says out loud — conversational, 2-3 sentences
- Use active voice. "You need to..." not "It is recommended that..."

## Output format — ONLY valid JSON, no text before or after:
{{
  "slides": [
    {{
      "number": 1,
      "title": "What is NIS2 and what's at stake for us",
      "bullets": ["3-4 plain language bullets specific to their sector"],
      "speaker_note": "what to say out loud (2-3 conversational sentences)"
    }},
    {{
      "number": 2,
      "title": "Our current compliance score",
      "score": 0,
      "score_label": "plain label e.g. Requires immediate attention",
      "bullets": ["what we have, what we are missing — specific to this company"],
      "speaker_note": "..."
    }},
    {{
      "number": 3,
      "title": "Top 3 actions in the next 30 days",
      "actions": [
        {{"action": "specific plain text", "owner": "role", "effort": "X days", "cost": "EUR range", "article_ref": "Art. 21(2)(x)"}}
      ],
      "speaker_note": "..."
    }},
    {{
      "number": 4,
      "title": "Cost of action vs. cost of inaction",
      "cost_of_action": "DIY/in-house range vs. external consultant range — e.g. 'DIY: €500–2,000 · External: €15,000–25,000'",
      "cost_of_inaction": "fine exposure + realistic incident cost for their sector",
      "speaker_note": "..."
    }},
    {{
      "number": 5,
      "title": "Recommended next step",
      "recommendation": "one clear ask from the board — specific and actionable",
      "speaker_note": "..."
    }}
  ]
}}
"""
    return _STATIC_BLOCK


def build_board_presenter_system(
    gap_analysis: dict,
    threat_scenarios: dict,
    company_profile: dict,
    language: str,
) -> list[dict]:
    static_block = _get_static_block()
    lang_instruction = "Polish (język polski)" if language == "pl" else "English"

    dynamic_block = (
        f"RESPOND ENTIRELY IN {lang_instruction}. All field values in the JSON must be in this language. "
        f"This includes: slide titles, bullets, actions, recommendations, speaker_notes, score_label. Never switch to English.\n\n"
        f"Company profile:\n{json.dumps(company_profile, ensure_ascii=False, indent=2)}\n\n"
        f"Gap analysis:\n{json.dumps(gap_analysis, ensure_ascii=False, indent=2)}\n\n"
        f"Threat scenarios:\n{json.dumps(threat_scenarios, ensure_ascii=False, indent=2)}"
    )

    return [
        {"type": "text", "text": static_block, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": dynamic_block},
    ]
