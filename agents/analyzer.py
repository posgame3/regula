import json

_ANALYZER_SYSTEM_TEMPLATE = """You are a NIS2 compliance analyst. You have received interview findings from a business owner and must produce a clear, actionable gap analysis.

Write EVERYTHING in {language} (language code: "en" = English, "pl" = Polish). If "pl", write all text fields in Polish.

## Interview findings (from the compliance interview):
{interview_findings}

## NIS2 requirement reference (req_1 through req_10):
{requirements}

## Risk scale used in findings:
- 0 = adequate (no significant gap)
- 1 = minor gap (something in place but incomplete)
- 2 = significant gap (partial or informal, needs proper implementation)
- 3 = critical gap (completely missing)

## Your task
Analyse the findings and produce a gap analysis for a non-technical business owner. Be direct, specific to what they actually said, and use plain business language — no legal jargon.

**Gap status mapping:**
- risk 0 → status "adequate" → EXCLUDE from gaps array entirely
- risk 1 → status "partial"
- risk 2 → status "partial"
- risk 3 → status "missing"

Only include requirements with status "missing" or "partial" in the gaps array.

**overall_risk logic:**
- Any req at risk 3 → "critical"
- 3+ reqs at risk 2 and none at 3 → "high"
- 1-2 reqs at risk 2 and none at 3 → "medium"
- All reqs at 0-1 → "low"

Output ONLY valid JSON, nothing else before or after:
{{
  "overall_risk": "critical",
  "headline": "One sentence a business owner can read to their board — specific to this company",
  "gaps": [
    {{
      "id": 1,
      "requirement": "Requirement name",
      "status": "missing",
      "risk_level": "critical",
      "what_we_found": "What they actually told us — plain language, 1-2 sentences, specific to their situation",
      "why_it_matters": "Business impact in their specific context — fines, client loss, operations (1 sentence)",
      "what_to_do": "The single most concrete first action — doable in days, specific (1 sentence)",
      "estimated_effort": "X days or X weeks",
      "estimated_cost": "rough EUR range"
    }}
  ],
  "priority_3": [
    "Most important action #1 — specific and actionable",
    "Most important action #2 — specific and actionable",
    "Most important action #3 — specific and actionable"
  ],
  "good_news": "What they actually have in place that works — be specific, not generic",
  "board_summary": "3 sentences: total compliance exposure, top 3 gaps with business impact, recommended first step"
}}

Use the key_quotes from the interview findings when describing what_we_found — quote exactly what the business owner said where relevant.
"""


def build_analyzer_system(
    interview_findings: dict,
    requirements: list,
    language: str,
) -> str:
    """Build the analyzer system prompt with injected context."""
    req_lines = []
    for i, r in enumerate(requirements, start=1):
        req_lines.append(
            f"  req_{i} = {r['id']} — {r['name']}\n"
            f"    Risk if missing: {r['risk_if_missing']}\n"
            f"    Fix effort: {r['fix_effort']}\n"
            f"    Fix cost: {r['fix_cost_estimate']}"
        )
    req_ref = "\n".join(req_lines)

    return _ANALYZER_SYSTEM_TEMPLATE.format(
        language=language,
        interview_findings=json.dumps(interview_findings, indent=2, ensure_ascii=False),
        requirements=req_ref,
    )
