# Regula — NIS2 Compliance Assessment Agent

## Problem
EU business owners (Poland + whole EU) don't know if NIS2 applies to them 
or where their gaps are. Consultants cost €1,500-4,000. Regula does it in 
15 minutes, in plain language, for free.

## What we build
8-agent pipeline: Qualifier → Interviewer → Analyzer → Red Team (Managed Agents) → Drafter → Threat Actor → Board Presenter → Remediation (tool-use) → PDF
Plus a standalone Regulatory Monitor (Managed Agents) that watches sources for gap-relevant alerts.

## Stack
- Python 3.11+
- FastAPI
- anthropic SDK, model: claude-opus-4-7
- python-dotenv
- WeasyPrint (PDF, add later)
- Simple HTML/JS frontend (add Friday)

## Project structure
regula/
├── app.py                    # FastAPI + WebSocket pipeline (single entry point)
├── agents/
│   ├── qualifier.py
│   ├── interviewer.py
│   ├── analyzer.py
│   ├── redteam.py            # legacy one-shot auditor (fallback)
│   ├── redteam_managed.py    # Managed Agents auditor (primary)
│   ├── monitor_managed.py    # Regulatory monitor (Managed Agents)
│   ├── drafter.py
│   ├── threat_actor.py
│   └── board_presenter.py
├── data/frameworks/
│   ├── nis2.json             # summarised index used by analyzer/drafter
│   └── nis2_directive.json   # verbatim Art. 21(2) text (EUR-Lex)
├── utils/{pdf.py, profile_store.py, tools.py}
├── templates/report.html     # PDF report (WeasyPrint)
├── static/index.html         # landing + chat SPA
├── scripts/setup_managed_agents.py
├── .env
└── requirements.txt

## Agent flow
1. Qualifier: 3 questions → JSON {applies, scope, proceed}
2. Interviewer: 10-15 plain-language questions → JSON {findings, key_quotes, biggest_concern}
3. Analyzer: gaps[] with risk_level critical/high/medium/low + business impact language
4. Red Team: simulates real NIS2 auditor attacking company's gaps → JSON {verdict, critical_failures}
5. Drafter: plain-language policy outlines for top gaps → JSON {policies[]}

## Run modes
- `uvicorn app:app --reload` — production (Opus 4.7, Extended Thinking on)
- `TEST_MODE=1 uvicorn app:app --reload` — fast/cheap (Sonnet 4.6, no Extended Thinking)
- `MOCK_MODE=1 uvicorn app:app --reload` — no API calls at all (instant mock responses)

## Key rules
- Model: claude-opus-4-7 for ALL agents (Sonnet 4.6 when TEST_MODE=1)
- Language: user picks PL or EN at start, entire pipeline responds in that language
- NIS2 requirements HARDCODED in nis2.json (10 requirements from Art.21) — never hallucinate
- Interviewer asks ONE question at a time
- All language must be plain business language — no legal jargon
- Output disclaimer: "Draft starting point for legal review — not a final compliance document"

## API key
In .env as ANTHROPIC_API_KEY

## Testing
- Unit tests: `python -m pytest tests/ -v`
- Mock pipeline: `MOCK_MODE=1 uvicorn app:app --reload` (no API calls, instant) → open browser → click "Historia Marka"
- Smoke test (automated): start server above, then `python tests/mock_pipeline.py`
- Full demo: `uvicorn app:app --reload` → click "Historia Marka"
