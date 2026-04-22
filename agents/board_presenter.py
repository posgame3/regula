import json

BOARD_PRESENTER_SYSTEM = """\
You generate a 5-slide executive presentation for a non-technical CEO/board.
Write in {language} (pl or en).

Score formula: start at 100, subtract 15 for each critical gap, 8 for each high gap.

Output JSON:
{{
  "slides": [
    {{
      "number": 1,
      "title": "What is NIS2 and what's at stake for us",
      "bullets": ["3-4 plain language bullets"],
      "speaker_note": "what to say out loud (2-3 sentences)"
    }},
    {{
      "number": 2,
      "title": "Our current compliance score",
      "score": 0,
      "score_label": "plain label e.g. Requires immediate attention",
      "bullets": ["what we have, what we are missing"],
      "speaker_note": "..."
    }},
    {{
      "number": 3,
      "title": "Top 3 actions in the next 30 days",
      "actions": [
        {{"action": "plain text", "owner": "role", "effort": "X days", "cost": "EUR range"}}
      ],
      "speaker_note": "..."
    }},
    {{
      "number": 4,
      "title": "Cost of action vs. cost of inaction",
      "cost_of_action": "total EUR estimate for top 3 fixes",
      "cost_of_inaction": "fine exposure + realistic incident cost for their sector",
      "speaker_note": "..."
    }},
    {{
      "number": 5,
      "title": "Recommended next step",
      "recommendation": "one clear ask from the board",
      "speaker_note": "..."
    }}
  ]
}}

Company profile:
{company_profile}

Gap analysis:
{gap_analysis}

Threat scenarios:
{threat_scenarios}
"""


def build_board_presenter_system(
    gap_analysis: dict,
    threat_scenarios: dict,
    company_profile: dict,
    language: str,
) -> str:
    return BOARD_PRESENTER_SYSTEM.format(
        language=language,
        company_profile=json.dumps(company_profile, ensure_ascii=False, indent=2),
        gap_analysis=json.dumps(gap_analysis, ensure_ascii=False, indent=2),
        threat_scenarios=json.dumps(threat_scenarios, ensure_ascii=False, indent=2),
    )
