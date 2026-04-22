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

```bash
# Unit tests (no server needed)
python -m pytest tests/ -v

# Mock pipeline — full pipeline in 5 seconds, no API calls
MOCK_MODE=1 uvicorn app:app --reload
# then click "Historia Marka" / "Watch Marek's story"

# Automated smoke test
MOCK_MODE=1 python tests/mock_pipeline.py --serve
```

## Architecture

```
User → WebSocket → Qualifier → Interviewer → Analyzer (🧠)
     → Red Team → Threat Actor (🧠) → Board Presenter
     → Drafter → Remediation Agent (🔧) → PDF Report

🧠 = Extended Thinking  |  🔧 = tool_use
```

## Disclaimer

Regula output is a draft starting point for legal review —
not a final compliance document. Always consult a qualified
legal or cybersecurity professional before implementing.

## License

MIT — open source, self-hostable. Your answers never leave your server.

---

Built with Claude Opus 4.7 | Cerebral Valley Hackathon 2026
