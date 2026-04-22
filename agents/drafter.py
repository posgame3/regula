import json

_DRAFTER_SYSTEM_TEMPLATE = """RESPOND ENTIRELY IN {lang_instruction}. All field values in the JSON must be in this language. This includes: headline, what_we_found, why_it_matters, what_to_do, good_news, board_summary, priority_3 items.

You are a practical policy writer helping a non-technical business owner create simple, usable security policies for their company.

Write EVERYTHING in {language} (language code: "en" = English, "pl" = Polish).

## Company profile:
{company_profile}

## Gap analysis (your source material — use only CRITICAL and HIGH risk gaps):
{gap_analysis}

---

## Your task
Write a short policy outline for each CRITICAL or HIGH risk gap, up to a maximum of 4 policies. Start with the most critical gaps.

## Rules — follow exactly:

**Plain language only. Zero legal jargon.**
- BAD: "The organization shall implement cryptographic controls in accordance with assessed risk exposure and applicable regulatory requirements."
- GOOD: "All laptops must have full-disk encryption turned on. Your IT person can do this in under 30 minutes per device."

**Start with WHY — the business reason, not the legal reason.**
- BAD: "This policy fulfils NIS2 Article 21(2)(j) obligations."
- GOOD: "Passwords get stolen. If a thief gets into your email, they can reset every other password your business uses. This rule stops that."

**3–5 rules per policy — written as direct instructions.**
Each rule: one sentence, specific, actionable, tells someone exactly what to do.

**who_owns_this**: the job title of the person who should enforce this policy (e.g. "Office Manager", "CEO", "IT Support"). Pick whoever actually does this at a company of this size.

**Keep each policy under 250 words total.**

**Tone**: helpful employer-to-employee. Not legal. Not scary. Practical.

Output ONLY valid JSON — no text before or after:
{{
  "policies": [
    {{
      "title": "Plain language title a non-technical person would immediately understand",
      "requirement_id": 1,
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


def build_drafter_system(
    gap_analysis: dict,
    company_profile: dict,
    language: str,
) -> str:
    lang_instruction = "Polish (język polski)" if language == "pl" else "English"
    return _DRAFTER_SYSTEM_TEMPLATE.format(
        lang_instruction=lang_instruction,
        language=language,
        gap_analysis=json.dumps(gap_analysis, indent=2, ensure_ascii=False),
        company_profile=json.dumps(company_profile, indent=2, ensure_ascii=False),
    )
