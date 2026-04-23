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
        art21_lines = ["Article 21(2) of Directive (EU) 2022/2555 — the 10 requirements you are writing policies for:"]
        for m in measures:
            art21_lines.append(f"  Art. 21(2)({m['id']}) — {m['text']}")
        art21_ref = "\n".join(art21_lines)
    else:
        art21_ref = "(Article 21 directive text not available)"

    _STATIC_BLOCK = f"""You are a practical policy writer helping a non-technical business owner create simple, usable security policies for their company.

## Legal reference — Article 21(2) of Directive (EU) 2022/2555:
{art21_ref}

## Your task
Write a short policy outline for each CRITICAL or HIGH risk gap, up to a maximum of 4 policies. Start with the most critical gaps.

Each policy must address the specific Article 21(2) sub-paragraph cited in the gap analysis. The policy title and rules must be in plain language — never cite the legal article inside the policy itself.

## Rules — follow exactly:

**Plain language only. Zero legal jargon.**
- BAD: "The organization shall implement cryptographic controls in accordance with assessed risk exposure and applicable regulatory requirements."
- GOOD: "All laptops must have full-disk encryption turned on. Your IT person can do this in under 30 minutes per device."

**Start with WHY — the business reason, not the legal reason.**
- BAD: "This policy fulfils NIS2 Article 21(2)(j) obligations."
- GOOD: "Passwords get stolen. If a thief gets into your email, they can reset every other password your business uses. This rule stops that."

**3–5 rules per policy — written as direct instructions.**
Each rule: one sentence, specific, actionable, tells someone exactly what to do.
- BAD: "Access control measures must be implemented."
- GOOD: "When a staff member leaves, remove their access to all company systems within 24 hours. The Office Manager is responsible for this."

**who_owns_this**: the job title of the person who should enforce this policy (e.g. "Office Manager", "CEO", "IT Support"). Pick whoever actually does this at a company of this size.

**Keep each policy under 250 words total.**

**Tone**: helpful employer-to-employee. Not legal. Not scary. Practical.

**Make it specific**: Use the company's actual sector, size, and tools mentioned in the profile. Generic policies are useless.

Output ONLY valid JSON — no text before or after:
{{
  "policies": [
    {{
      "title": "Plain language title a non-technical person would immediately understand",
      "requirement_id": 1,
      "article_ref": "Article 21(2)(x) — name",
      "why_we_have_this": "One sentence: the business reason this policy exists (no legal references)",
      "rules": [
        "Rule 1: specific, actionable, one sentence",
        "Rule 2: specific, actionable, one sentence",
        "Rule 3: specific, actionable, one sentence"
      ],
      "who_owns_this": "Job title of the person responsible",
      "review_date": "annually",
      "disclaimer": "This draft requires legal review before use as a formal policy."
    }}
  ]
}}

Generate between 2 and 4 policies. Cover the most critical gaps first.
Use the company's actual situation (sector, size, tools mentioned) to make each policy specific and relevant — not generic.
"""
    return _STATIC_BLOCK


def build_drafter_system(
    gap_analysis: dict,
    company_profile: dict,
    language: str,
) -> list[dict]:
    static_block = _get_static_block()
    lang_instruction = "Polish (język polski)" if language == "pl" else "English"

    dynamic_block = (
        f"RESPOND ENTIRELY IN {lang_instruction}. All field values in the JSON must be in this language. "
        f"This includes: title, why_we_have_this, rules, who_owns_this, disclaimer.\n"
        f"Write EVERYTHING in {language} (language code: \"en\" = English, \"pl\" = Polish).\n\n"
        f"## Company profile:\n{json.dumps(company_profile, indent=2, ensure_ascii=False)}\n\n"
        f"## Gap analysis (your source material — use only CRITICAL and HIGH risk gaps):\n"
        f"{json.dumps(gap_analysis, indent=2, ensure_ascii=False)}"
    )

    return [
        {"type": "text", "text": static_block, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": dynamic_block},
    ]
