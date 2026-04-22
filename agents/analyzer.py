import json
import pathlib

_DIRECTIVE_PATH = pathlib.Path(__file__).parent.parent / "data" / "frameworks" / "nis2_directive.json"

# Maps req_N index (1-based) to Art. 21(2) letter and canonical name
_ART21_MAP = [
    ("a", "Policies on risk analysis and information system security"),
    ("b", "Incident handling"),
    ("c", "Business continuity, backup management and disaster recovery, and crisis management"),
    ("d", "Supply chain security"),
    ("e", "Security in network and information systems acquisition, development and maintenance"),
    ("f", "Policies and procedures to assess the effectiveness of cybersecurity risk-management measures"),
    ("g", "Basic cyber hygiene practices and cybersecurity training"),
    ("h", "Policies and procedures regarding the use of cryptography and encryption"),
    ("i", "Human resources security, access control policies and asset management"),
    ("j", "Multi-factor authentication or continuous authentication solutions, secured communications"),
]


def _load_art21_measures() -> list:
    if _DIRECTIVE_PATH.exists():
        data = json.loads(_DIRECTIVE_PATH.read_text())
        return data.get("article_21_measures", {}).get("measures", [])
    return []


def _format_art21_ref(measures: list) -> str:
    if not measures:
        return "(Article 21 directive text not available)"
    lines = ["Article 21(2) of Directive (EU) 2022/2555 — exact text:"]
    for m in measures:
        lines.append(f"  Art. 21(2)({m['id']}) — {m['text']}")
    return "\n".join(lines)


def _article_ref(req_index: int) -> str:
    """Return 'Article 21(2)(x) — Name' for req index 1-10."""
    if 1 <= req_index <= len(_ART21_MAP):
        letter, name = _ART21_MAP[req_index - 1]
        return f"Article 21(2)({letter}) — {name}"
    return f"Article 21(2) — Requirement {req_index}"


_ANALYZER_SYSTEM_TEMPLATE = """You are a NIS2 compliance analyst. You have received interview findings and must produce a clear, actionable gap analysis grounded in the exact text of Directive (EU) 2022/2555.

Write EVERYTHING in {language} (language code: "en" = English, "pl" = Polish). If "pl", write all text fields in Polish.

## Legal reference — Article 21(2) of Directive (EU) 2022/2555:
{art21_reference}

## Interview findings:
{interview_findings}

## Requirement mapping (req_N → Article 21(2) sub-paragraph):
{req_mapping}

## Risk scale:
- 0 = adequate (no significant gap)
- 1 = minor gap (something in place but incomplete)
- 2 = significant gap (partial or informal, needs proper implementation)
- 3 = critical gap (completely missing)

## Your task
Analyse the findings and produce a gap analysis for a non-technical business owner. Be direct, specific to what they actually said, and use plain business language.

**Every gap must cite the specific Article 21(2) sub-paragraph** it falls under (e.g. "Article 21(2)(j) — Multi-factor authentication"). Use the exact wording from the directive as reference for what is required, but explain the gap in plain language.

**Gap status mapping:**
- risk 0 → EXCLUDE from gaps array entirely
- risk 1 or 2 → status "partial"
- risk 3 → status "missing"

Only include requirements with risk 1-3 in the gaps array.

**overall_risk logic:**
- Any req at risk 3 → "critical"
- 3+ reqs at risk 2 and none at 3 → "high"
- 1-2 reqs at risk 2 and none at 3 → "medium"
- All reqs at 0-1 → "low"

CRITICAL: Output ONLY valid JSON. No markdown fences, no text before or after. Start with {{ end with }}.
{{
  "overall_risk": "critical",
  "headline": "One sentence a business owner can read to their board — specific to this company",
  "gaps": [
    {{
      "id": 1,
      "article_ref": "Article 21(2)(b) — Incident handling",
      "requirement": "Short plain-language name",
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
    "Most important action #1 — specific and actionable, cite the article",
    "Most important action #2 — specific and actionable, cite the article",
    "Most important action #3 — specific and actionable, cite the article"
  ],
  "good_news": "What they actually have in place that works — be specific, not generic",
  "board_summary": "3 sentences: total compliance exposure under Art. 21 NIS2, top 3 gaps with business impact, recommended first step"
}}

Use key_quotes from the interview findings when writing what_we_found — quote exactly what the business owner said where relevant.
article_ref must follow the format: "Article 21(2)(x) — [name]" using the exact sub-paragraph letter.
"""


def build_analyzer_system_with_thinking(
    interview_findings: dict,
    requirements: list,
    language: str,
) -> str:
    """Variant that hints the model to use its full reasoning capacity."""
    return build_analyzer_system(interview_findings, requirements, language)


def build_analyzer_system(
    interview_findings: dict,
    requirements: list,
    language: str,
) -> str:
    art21_measures = _load_art21_measures()
    art21_ref = _format_art21_ref(art21_measures)

    # Build req mapping: req_1 → Art. 21(2)(a) — Name, with legacy fix effort/cost
    req_lines = []
    for i, r in enumerate(requirements, start=1):
        article = _article_ref(i)
        req_lines.append(
            f"  req_{i} = {article}\n"
            f"    Fix effort: {r.get('fix_effort', 'unknown')}\n"
            f"    Fix cost: {r.get('fix_cost_estimate', 'unknown')}"
        )
    req_mapping = "\n".join(req_lines)

    return _ANALYZER_SYSTEM_TEMPLATE.format(
        language=language,
        art21_reference=art21_ref,
        interview_findings=json.dumps(interview_findings, indent=2, ensure_ascii=False),
        req_mapping=req_mapping,
    )
