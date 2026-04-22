# Regula — NIS2 Compliance Assessment Agent

> "What you do before calling the lawyer."

Built for the Cerebral Valley "Built with Opus 4.7" Hackathon.

## What it does

Regula is a multi-agent AI system that assesses a company's NIS2
compliance through natural conversation — and then generates the
remediation documents to fix the gaps found.

**The problem:** 130,000+ companies in the EU must comply with NIS2.
Most don't know if it applies to them, what they're missing, or where to start.
A compliance consultant costs €200/hour. Regula takes 15 minutes and is free.

**ChatGPT answers questions. Regula asks the questions you should be asking yourself.**

## Pipeline (8 agents)

1. **Qualifier** — Determines if NIS2 applies directly (Annex I/II) or via supply chain pressure (Art. 21(2)(d))
2. **Interviewer** — Conducts a structured compliance interview (10-14 questions)
3. **Analyzer** — Extended Thinking gap analysis against 10 NIS2 Art. 21(2) requirements
4. **Red Team Auditor** — Simulates a real government audit, cites specific articles, issues PASS/FAIL verdict
5. **Threat Actor** — Extended Thinking: personalized attack scenarios based on YOUR specific gaps
6. **Board Presenter** — 5-slide executive deck with compliance score gauge
7. **Policy Drafter** — Generates draft policy documents for critical gaps
8. **Remediation Agent** — tool_use: generates ready-to-download policy docs, incident plans, remediation checklists

## Key features

- **Grounded in real NIS2 directive text** — Art. 21 exact text + Annex I/II sectors from EUR-Lex
- **Extended Thinking** — Analyzer, Threat Actor use adaptive thinking for deep reasoning
- **Supply chain indirect scope** — Small companies supplying NIS2-covered clients get flagged (Art. 21(2)(d))
- **Bilingual** — Full PL/EN support, language auto-detected
- **Demo mode** — "Marek's story" button: Sonnet 4.6 plays the role of a Polish truck company owner
- **PDF report** — Full 7-section compliance report, downloadable after assessment
- **Remediation documents** — Security policy, incident response plan, remediation checklist (PDF)
- **Mock mode** — Full pipeline in 5 seconds for testing (MOCK_MODE=1)
- **Chat locked after completion** — clean UX, reload for new session

## Tech stack

- **Backend:** FastAPI + WebSocket (Python)
- **AI:** Claude Opus 4.7 (all agents), Claude Sonnet 4.6 (demo persona)
- **Extended Thinking:** `thinking={"type": "adaptive"}, output_config={"effort": "high"}`
- **PDF:** WeasyPrint + Jinja2
- **Frontend:** Vanilla JS + Tailwind CSS
- **NIS2 grounding:** EUR-Lex directive PDF parsed with pypdf → nis2_directive.json

## Quick start

```bash
git clone https://github.com/posgame3/regula
cd regula
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn app:app --reload
# Open http://localhost:8000
```

## Testing

```bash
# Unit tests
python -m pytest tests/ -v

# Mock pipeline — full run in ~5 seconds, no API calls
MOCK_MODE=1 python tests/mock_pipeline.py --serve

# Mock mode with browser
MOCK_MODE=1 uvicorn app:app --reload
# Open http://localhost:8000 → click "Historia Marka" / "Watch Marek's story"
```

## Project structure

```
regula/
├── app.py                         # FastAPI app, WebSocket handler, pipeline orchestration
├── agents/
│   ├── qualifier.py               # NIS2 applicability check (Annex I/II + supply chain)
│   ├── interviewer.py             # 10-14 question compliance interview
│   ├── analyzer.py                # Gap analysis with Extended Thinking
│   ├── redteam.py                 # Simulated NIS2 auditor (PASS/FAIL verdict)
│   ├── threat_actor.py            # Attack scenarios with Extended Thinking
│   ├── board_presenter.py         # 5-slide executive deck + compliance score
│   └── drafter.py                 # Policy outline generator
├── utils/
│   ├── pdf.py                     # Full compliance report PDF (WeasyPrint + Jinja2)
│   └── tools.py                   # Remediation tool functions (policy, incident, checklist)
├── templates/
│   ├── report.html                # 7-section PDF compliance report template
│   └── tools/
│       ├── policy.html            # Security policy (A4, 3 pages)
│       ├── incident.html          # Incident response plan (A4, 1-2 pages)
│       └── checklist.html         # Remediation checklist table (A4, 1 page)
├── data/frameworks/nis2.json      # 10 NIS2 Art. 21(2) requirements (hardcoded, never hallucinated)
├── static/index.html              # Single-page frontend (Tailwind CSS, vanilla JS)
├── tests/
│   ├── test_parsing.py            # Unit tests for JSON extraction
│   └── mock_pipeline.py           # End-to-end smoke test via WebSocket
└── requirements.txt
```

## Output

For each company, Regula produces:

- **Qualification result** — applies yes/no, entity type (essential/important), supply chain flag
- **Gap analysis card** — risk level per NIS2 requirement, top 3 priority actions
- **Audit simulation** — PASS / FAIL / CONDITIONS verdict, critical failures cited by article
- **Threat scenarios** — real attack chains mapped to the company's specific gaps
- **Board deck** — 5 slides with compliance score gauge, cost of action vs. inaction
- **Policy drafts** — plain-language outlines for critical/high gaps
- **Remediation documents** (PDF download):
  - Information Security Policy (A4, 3 pages)
  - Incident Response Plan with CSIRT NASK contacts and 24h notification template
  - NIS2 Remediation Checklist with deadlines by risk level
- **Full PDF report** — all of the above in one downloadable document

---

> Regula output is a draft starting point for legal review — not a final compliance document.
> MIT License — see [LICENSE](LICENSE)
