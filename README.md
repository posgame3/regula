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
4. **Red Team Auditor** — Simulates a real government audit, cites specific articles, issues PASS/FAIL verdict. **Now runs as a Claude Managed Agent** that self-drives through custom tools (see below).
5. **Threat Actor** — Extended Thinking: personalized attack scenarios based on YOUR specific gaps
6. **Board Presenter** — 5-slide executive deck with compliance score gauge
7. **Policy Drafter** — Generates draft policy documents for critical gaps
8. **Remediation Agent** — tool_use: generates ready-to-download policy docs, incident plans, remediation checklists

## Two Claude Managed Agents (new)

Built on Claude's Managed Agents beta (`managed-agents-2026-04-01`) — Anthropic runs the
agent loop, we define the tools, and Opus 4.7 self-drives.

### 1. Iterative Auditor (replaces one-shot Red Team)

Instead of a single prompt + JSON response, the auditor now runs as a persistent
Managed Agent with four custom tools:

- `lookup_requirement(article_ref)` — returns Art. 21(2) sub-paragraph text from EUR-Lex
- `lookup_gap(requirement_name)` — cross-references the analyzer's findings
- `lookup_interview_answer(topic)` — pulls relevant company answers from the interview
- `finalize_verdict(verdict, summary, critical_failures, passed_checks, preparation)` — terminal tool

The agent decides on its own which requirements to drill into, cross-references
the company's answers against each article, and only issues a verdict after
investigating 4–6 sub-paragraphs. Typical run: **13 tool invocations** — not a single
prompt, but a real audit trace.

Enable via `MANAGED_AGENTS=1` in `.env` after running the setup script.
Falls back to the legacy in-process flow when disabled (so `MOCK_MODE` stays fast).

### 2. Regulatory Monitor (new feature)

A second Managed Agent that runs **after** the assessment is done. User enters
their email, gets subscribed, and the monitor periodically (demo: on-demand)
does the following:

- Calls `lookup_user_profile()` to see the company's sector, language, and open gaps
- Runs 2–4 targeted `web_search` queries for NIS2 / CSIRT / regulatory news relevant to that sector
- Queues an alert via `queue_alert()` **only** when a finding touches one of the user's specific open gaps
- Calls `finalize_run()` to close the session

The alerts include source URLs, severity, and which of the user's gaps they relate to — delivered
in the user's language. Zero alerts is a perfectly valid run.

Endpoints:
- `POST /api/subscribe` — after assessment, save email + gaps as a monitoring profile
- `POST /api/monitor/run` — trigger one monitor pass (scheduled in production)
- `GET /api/alerts?user_id=...` — list all alerts queued for a user

## Key features

- **Grounded in real NIS2 directive text** — Art. 21 exact text + Annex I/II sectors from EUR-Lex
- **Extended Thinking** — Analyzer and Threat Actor use adaptive thinking for deep reasoning
- **Supply chain indirect scope** — Small companies supplying NIS2-covered clients get flagged (Art. 21(2)(d))
- **Bilingual** — Full PL/EN support, language auto-detected
- **Demo mode** — "Marek's story" button: Sonnet 4.6 plays the role of a Polish truck company owner
- **PDF report, redesigned** — Full 7-section compliance report in the editorial landing-page
  design language (Archivo + IBM Plex Mono, paper/ink/signal palette, flat layout)
- **Remediation documents** — Security policy, incident response plan, remediation checklist (PDF)
- **Mock mode** — Full pipeline in 5 seconds for testing (`MOCK_MODE=1`)

## Tech stack

- **Backend:** FastAPI + WebSocket (Python)
- **AI:** Claude Opus 4.7 (all agents), Claude Sonnet 4.6 (demo persona)
- **Managed Agents:** `client.beta.agents` / `client.beta.sessions` with custom tools + built-in `web_search`
- **Extended Thinking:** `thinking={"type": "adaptive"}, output_config={"effort": "high"}`
- **PDF:** WeasyPrint + Jinja2, Archivo + IBM Plex Mono TTFs embedded
- **Frontend:** Vanilla JS + Tailwind CSS
- **NIS2 grounding:** EUR-Lex directive PDF parsed with pypdf → `data/frameworks/nis2_directive.json`
- **Profile store:** JSON file-backed (`data/profiles.json`, gitignored)

## Quick start

```bash
git clone https://github.com/posgame3/regula
cd regula
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...

uvicorn app:app --reload
# Open http://localhost:8000
```

### Enabling the Managed Agents features

```bash
# 1. One-time: create the auditor + monitor agents and environment.
#    This writes MANAGED_ENV_ID, REDTEAM_AGENT_ID, MONITOR_AGENT_ID into .env.
python scripts/setup_managed_agents.py

# 2. Flip the feature flag on, then run as usual.
echo "MANAGED_AGENTS=1" >> .env
uvicorn app:app --reload
```

The setup script is idempotent — re-running it reuses existing IDs unless you
pass `--force`.

### Testing modes

```bash
# Unit tests (no server needed)
python -m pytest tests/ -v

# Mock pipeline — full pipeline in 5 seconds, no API calls
MOCK_MODE=1 uvicorn app:app --reload
# then click "Historia Marka" / "Watch Marek's story"
```

Note: `MOCK_MODE=1` automatically disables `MANAGED_AGENTS` so the mock demo
stays fast and offline.

## Architecture

```
User → WebSocket → Qualifier → Interviewer → Analyzer (🧠)
     → Red Team (👤) → Threat Actor (🧠) → Board Presenter
     → Drafter → Remediation Agent (🔧) → PDF Report
                                    ↓
                          Subscribe → Monitor (👤 + 🌐)
                                         ↓
                                      Mailbox

🧠 = Extended Thinking  |  🔧 = tool_use  |  👤 = Managed Agent  |  🌐 = web_search
```

## Project layout

```
regula/
├── app.py                           # FastAPI + WebSocket + /api endpoints
├── agents/
│   ├── qualifier.py
│   ├── interviewer.py
│   ├── analyzer.py
│   ├── redteam.py                   # legacy single-prompt auditor (fallback)
│   ├── redteam_managed.py           # Managed-Agents iterative auditor
│   ├── monitor_managed.py           # Managed-Agents regulatory monitor
│   ├── threat_actor.py
│   ├── board_presenter.py
│   └── drafter.py
├── scripts/
│   ├── fetch_nis2.py
│   └── setup_managed_agents.py      # one-time agent + environment creation
├── data/frameworks/
│   ├── nis2.json                    # requirements index
│   └── nis2_directive.json          # full directive text
├── utils/
│   ├── pdf.py                       # WeasyPrint report generator
│   ├── tools.py
│   └── profile_store.py             # JSON-backed user profile + alerts
├── templates/report.html            # redesigned PDF template (Archivo / IBM Plex Mono)
├── static/
│   ├── fonts/                       # Archivo + IBM Plex Mono TTFs (embedded in PDFs)
│   └── index.html                   # landing + chat + mailbox UI
└── tests/
```

## Disclaimer

Regula output is a draft starting point for legal review —
not a final compliance document. Always consult a qualified
legal or cybersecurity professional before implementing.

## License

MIT — open source, self-hostable. Your answers never leave your server.

---

Built with Claude Opus 4.7 | Cerebral Valley Hackathon 2026
