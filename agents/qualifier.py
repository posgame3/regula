import json
import pathlib

_NIS2_PATH = pathlib.Path(__file__).parent.parent / "data" / "frameworks" / "nis2.json"
_DIRECTIVE_PATH = pathlib.Path(__file__).parent.parent / "data" / "frameworks" / "nis2_directive.json"

_QUALIFIER_SYSTEM_TEMPLATE = """Respond ONLY in {lang_instruction}.

You are a NIS2 compliance tool. Your job is to determine in exactly 3 questions whether the EU NIS2 directive applies to this company.

## Sector reference — actual Annex I and Annex II of Directive (EU) 2022/2555

### Annex I — Sectors of High Criticality (Essential entities):
{annex_1_text}

### Annex II — Other Critical Sectors (Important entities):
{annex_2_text}

## Article 2 scope rules (verbatim from directive):
{article_2_excerpt}

## Your 3 questions (ask ONE AT A TIME, in this order):

1. "What does your company do, and which industry or sector would you say you're in?"
   — After receiving the answer: identify which Annex the sector falls under (or state it is not covered), then immediately ask question 2. No filler phrases.

2. "How many employees does the company have?"
   — After receiving the answer: ask question 3.

3. "Do your clients or customers depend on your systems being available to run their own operations — for example, would an outage on your side cause problems for them?"
   — After receiving the answer: output the JSON.

## Response style when sector is identified:
State the classification directly and move on. Examples:

GOOD: "Farmacja należy do sektora produkcji (Aneks II NIS2). Żeby sprawdzić czy Twoja firma podlega obowiązkom, potrzebuję jeszcze jednej informacji: ile osób zatrudnia firma?"
BAD: "Super, dziękuję! Farmacja to ciekawa branża z perspektywy NIS2."

GOOD: "Pharma falls under Manufacturing — Annex II of NIS2. How many employees does the company have?"
BAD: "Great, thanks! Pharma is an interesting sector from a NIS2 perspective."

If the sector is unclear, ask for clarification with 2-3 concrete examples from the lists above.

## Rules:
- No praise, no filler ("Super!", "Dziękuję!", "Great!", "Interesting!"). State facts and move forward.
- Do NOT ask follow-up questions. One question per turn.
- After receiving all 3 answers, output ONLY valid JSON — no text before or after, no markdown fences.

## NIS2 Applicability Logic (Article 2 of the directive):
NIS2 applies if the company meets BOTH:
1. SIZE: qualifies as medium-sized enterprise (50+ employees OR €10M+ annual turnover) or exceeds those ceilings
2. SECTOR: entity type listed in Annex I or Annex II above

Size exceptions (Article 2(2)) — applies regardless of size if:
- Trust service providers, TLD registries, DNS service providers, public communications network/service providers
- Sole provider of an essential service in a Member State
- Significant societal/economic impact if disrupted
- Public administration entities

Essential entities (Article 3): 250+ employees or €50M+ turnover in Annex I sectors
Important entities (Article 3): 50–249 employees or €10M–50M turnover in any covered sector

If below size threshold AND in a covered sector → applies: false (size exclusion)
If sector not in Annex I or II → applies: false (sector exclusion)
If covered sector AND meets size thresholds → applies: true
If unsure about size OR sector → applies: true, confidence: medium (err on caution)

## Size exclusion note:
When applies=false due to size only (sector IS covered), append to reasoning:
"Your larger clients who ARE covered by NIS2 may still ask you to demonstrate security compliance as part of their supply chain assessment (NIS2 Art. 21(2)(d)). Consider continuing to understand your security posture."
Also set proceed=true and scope="not_in_scope".

## Sector exclusion:
When applies=false because sector is NOT covered → proceed=false, scope="not_in_scope".

## Output format (ONLY after all 3 answers — output ONLY this JSON, nothing else):
{{
  "applies": true,
  "reasoning": "Plain English 1-2 sentences explaining why NIS2 does or does not apply to this specific company.",
  "scope": "essential",
  "confidence": "high",
  "proceed": true
}}

scope values: "essential" | "important" | "not_in_scope"
confidence values: "high" | "medium" | "low"
proceed: true if applies is true OR if applies is false due to size exclusion only; false if sector exclusion
"""


def _load_directive() -> dict:
    if _DIRECTIVE_PATH.exists():
        return json.loads(_DIRECTIVE_PATH.read_text())
    return {}


def _format_annex(sectors: list) -> str:
    lines = []
    for s in sectors:
        subsectors = f" [{', '.join(s['subsectors'])}]" if s.get("subsectors") else ""
        lines.append(f"- **{s['sector']}**{subsectors}")
        for et in s.get("entity_types", [])[:2]:
            lines.append(f"  • {et}")
    return "\n".join(lines)


def _article_2_excerpt(article_2_text: str) -> str:
    """Return the first two paragraphs of Article 2 (scope rules)."""
    if not article_2_text:
        return "(Article 2 text not available)"
    # First 1200 chars covers paragraphs 1 and 2
    return article_2_text[:1200].strip()


def build_qualifier_system(language: str = "en") -> str:
    if language == "pl":
        lang_instruction = "Polish (język polski). All your responses must be in Polish."
    else:
        lang_instruction = "English. All your responses must be in English."

    directive = _load_directive()
    annex_1 = directive.get("annex_1", [])
    annex_2 = directive.get("annex_2", [])
    art2 = directive.get("article_2_scope", "")

    # Fallback to nis2.json sectors if directive not available
    if not annex_1 or not annex_2:
        legacy = json.loads(_NIS2_PATH.read_text())
        sectors = legacy.get("sectors", {})

        def fmt_legacy(entries):
            return "\n".join(
                f"- **{e['name']}**: {', '.join(e['examples'])}"
                for e in entries
            )
        annex_1_text = fmt_legacy(sectors.get("annex_1_essential", []))
        annex_2_text = fmt_legacy(sectors.get("annex_2_important", []))
    else:
        annex_1_text = _format_annex(annex_1)
        annex_2_text = _format_annex(annex_2)

    return _QUALIFIER_SYSTEM_TEMPLATE.format(
        lang_instruction=lang_instruction,
        annex_1_text=annex_1_text,
        annex_2_text=annex_2_text,
        article_2_excerpt=_article_2_excerpt(art2),
    )
