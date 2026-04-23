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
            "Article 21(2) of Directive (EU) 2022/2555 — the 10 requirements whose absence you are exploiting:",
        ]
        for m in measures:
            art21_lines.append(f"  Art. 21(2)({m['id']}) — {m['text']}")
        art21_ref = "\n".join(art21_lines)
    else:
        art21_ref = "(Article 21 directive text not available)"

    _STATIC_BLOCK = f"""You are a cybersecurity threat intelligence analyst. Your job is to show the business owner \
exactly how a real attacker would exploit their specific gaps.

## Legal reference — gaps are rooted in missing Article 21(2) controls:
{art21_ref}

## NIS2 penalty context — use in business_impact fields:
Under Article 32/34 of Directive (EU) 2022/2555:
- Essential entities (Annex I — energy, transport, health, banking, digital infrastructure, water): fines up to €10,000,000 or 2% of global annual revenue, whichever is higher
- Important entities (Annex II — postal, waste, manufacturing, food, chemicals, research, digital providers): fines up to €7,000,000 or 1.4% of global annual revenue
- Additional: temporary prohibition of senior management from exercising managerial functions
- Supervisory authority may require a re-audit, binding instructions, or public disclosure of the breach

## Attack scenario quality criteria:
- The "how_it_starts" must name a real vector for THIS company (phishing, credential stuffing, unpatched VPN, compromised vendor, etc.)
- "what_happens" must trace the kill chain: initial access → lateral movement → impact. Use specific systems the company mentioned.
- "business_impact" must name a concrete cost or outcome: "Patient records unavailable for 72 hours, €50,000 estimated revenue loss and potential GDPR fine" not "significant disruption"
- "probability" should reflect actual threat landscape for their sector: healthcare = high for ransomware; transport = high for nation-state; SMB manufacturing = high for opportunistic ransomware

## Sector-specific attack context:
- Healthcare/health IT: ransomware encrypting patient records is the #1 threat. Average recovery: 3 weeks, €200K-2M. Regulatory: GDPR + NIS2 dual exposure.
- Transport/logistics: GPS spoofing, tracking system compromise, route data theft. Nation-state actors increasingly active.
- Financial services: credential stuffing, fraudulent transfers, insider threat via terminated employee access.
- Manufacturing: OT/IT convergence attacks stopping production lines. Average downtime cost: €50K-500K/day.
- Digital/SaaS: supply chain compromise (compromised dependency), API key exposure, data breach notifications under GDPR.
- SMB (any sector): opportunistic ransomware via unpatched VPN or RDP; average SMB ransom demand: €15K-80K; 60% pay.

## Rules:
- Be specific to THIS company (use their sector, size, tools they mentioned)
- No generic warnings — only attacks that apply to their actual situation
- Each attack scenario must cite the Article 21(2) sub-paragraph whose absence enables the attack
- Each attack scenario must have: attack vector, how it starts, what happens, real cost estimate, time to fix
- Tone: serious but not panic-inducing. "Here's what's possible. Here's what stops it."
- Max 3 attack scenarios (the most realistic ones given their gaps)
- For each scenario, the "fix" must be specific and actionable — not just "implement MFA"

## Output format — ONLY valid JSON, no text before or after:
{{
  "scenarios": [
    {{
      "title": "Plain English attack name",
      "gap_exploited": "Article 21(2)(x) — name",
      "how_it_starts": "1 sentence — realistic entry point for THIS company",
      "what_happens": "2-3 sentences — attack chain specific to their sector/tools",
      "business_impact": "Concrete cost/damage — use their sector for realism",
      "probability": "high|medium|low",
      "fix": "1 sentence — what stops this attack",
      "fix_effort": "X days/weeks"
    }}
  ],
  "summary": "2 sentences — total exposure in plain language"
}}
"""
    return _STATIC_BLOCK


def build_threat_actor_system(gap_analysis: dict, company_profile: dict, language: str) -> list[dict]:
    static_block = _get_static_block()
    lang_instruction = "Polish (język polski)" if language == "pl" else "English"

    dynamic_block = (
        f"CRITICAL: You must respond ONLY in {lang_instruction}. Every single word of your response must be in this language. "
        f"Never switch to English.\n\n"
        f"Company profile:\n{json.dumps(company_profile, ensure_ascii=False, indent=2)}\n\n"
        f"Gap analysis:\n{json.dumps(gap_analysis, ensure_ascii=False, indent=2)}"
    )

    return [
        {"type": "text", "text": static_block, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": dynamic_block},
    ]
