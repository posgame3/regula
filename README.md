# Regula — NIS2 Compliance Assessment Agent

> "What you do before calling the lawyer."

Built for the **Cerebral Valley "Built with Opus 4.7" Hackathon** (2026).

Live demo: https://regula.gotowywniosek.pl/
Repo: https://github.com/posgame3/regula

---

## The problem

The EU's NIS2 Directive (Directive (EU) 2022/2555) took effect in October 2024
and dramatically expanded the scope of mandatory cybersecurity regulation. The
European Commission's own impact assessment estimates **~160,000 companies**
across the EU now fall under it — up from roughly 3,500 under NIS1.

Most of them don't know it.

- A small hospital supplier, a regional logistics operator, a mid-size software
  house selling to banks — all now need a documented risk-management programme
  under **Article 21(2)**, covering ten specific measures from incident response
  to supply-chain security to cryptography.
- Fines go up to **€10 million or 2% of global turnover**, whichever is higher.
- The cheapest path to clarity today is a compliance consultant at ~€200/hour.
  Most SMEs quote €1,500–€4,000 for a basic gap assessment.

**Regula replaces that first consultant visit.** It does the boring part —
figuring out whether NIS2 applies to you, asking the right questions about
what you have in place, comparing your answers to Article 21(2) verbatim text,
and producing the draft documents you'd hand to a lawyer — in 15 minutes,
in plain Polish or English, for free.

> ChatGPT answers questions. Regula asks the questions you should be
> asking yourself.

---

## Why NIS2, not "cybersecurity"?

NIS2 Article 21(2) is not paperwork. It enumerates **ten mandatory security
controls**: incident handling, business continuity and backup discipline,
supply-chain security, vulnerability management, cryptography, access
management, multifactor authentication, cyber-hygiene training, and
incident reporting. These are the same controls a real attacker probes for
and a real auditor checks. Compliance with Article 21 *is* a real
cybersecurity uplift — with legal teeth that "best practice" alone never has.

Regula does **not** replace your SOC, EDR, vulnerability scanner, or
penetration tester. It tells you which of those ten controls you are missing,
models how an attacker would exploit each gap, and produces the documents
required to close them. Compliance is the legal frame; cybersecurity is the
actual outcome.

---

## What makes it a hackathon project (not a consulting tool)

Regula is a demonstration of five Claude Opus 4.7 capabilities working
together in one pipeline:

| Capability | Where it shows up |
|---|---|
| **Extended Thinking** (adaptive, summarized) | Analyzer and Threat Actor agents — reasoning is surfaced in the UI behind a "Show reasoning" toggle |
| **Managed Agents** (beta `managed-agents-2026-04-01`) | Red Team Auditor + Regulatory Monitor — Anthropic runs the loop, we define the tools |
| **Prompt caching** (`cache_control: ephemeral`) | All 8 in-process agents, with per-call `cache_read_input_tokens` logged for honest measurement |
| **Tool use** (parallel, deterministic) | Remediation stage: 4 PDF generators + ENISA search run concurrently via `asyncio.gather` + `asyncio.to_thread` |
| **Streaming** (WebSocket) | Every agent response streams to the browser; the full pipeline is a live conversation, not a batch job |

The pipeline is **grounded in the real directive**: EUR-Lex's verbatim Art. 21(2)
text and Annex I/II sector list ship with the repo (`data/frameworks/`). The
model is never asked "what are the NIS2 requirements" — it's always
`lookup_requirement("b")` returning the exact EUR-Lex sentence.

---

## Live demo — what to click

1. Open https://regula.gotowywniosek.pl/ (or run locally, see below).
2. Pick language (PL / EN).
3. Either:
   - **"Watch Marek's story" / "Historia Marka"** — a Sonnet 4.6 persona
     (Marek, a Polish truck-company owner) plays the user, so you can watch
     the whole 8–9-minute pipeline end-to-end without typing. Best for demos.
   - **Chat mode** — answer in your own words. ~10–14 short questions.
4. Watch the stage bar on the right move through: `qualify → interview →
   analyze → redteam (👤 managed) → threat (🧠) → board → drafter + closure
   (∥ concurrent) → remediation (🔧 tool use) → complete`.
5. At "complete", download the PDFs: main report + security policy + incident
   plan + remediation checklist + gap closure plan.
6. Optional: enter an email to subscribe to the **Regulatory Monitor**, then
   click "Run now" in the mailbox to watch a second Managed Agent
   web-search NIS2/CSIRT news for alerts relevant to your gaps.

---

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

For long assessments, add WebSocket keepalive so the browser tab doesn't get
dropped mid-pipeline:

```bash
uvicorn app:app --reload --ws-ping-interval 30 --ws-ping-timeout 60
```

### Run modes

| Env var | Model | API calls | Use case |
|---|---|---|---|
| (none) | Opus 4.7 | real | production / submission demo |
| `TEST_MODE=1` | Sonnet 4.6 | real | fast iteration, Extended Thinking off |
| `MOCK_MODE=1` | — | **none** | instant mock pipeline (~5 s), offline demos |

```bash
TEST_MODE=1 uvicorn app:app --reload   # cheap, full pipeline, real model
MOCK_MODE=1 uvicorn app:app --reload   # no API key needed, for video recording
```

### Enabling Managed Agents (Red Team + Monitor)

```bash
# 1. One-time: create the two agents + shared environment in your Anthropic
#    workspace. This writes MANAGED_ENV_ID, REDTEAM_AGENT_ID, MONITOR_AGENT_ID
#    into your .env.
python scripts/setup_managed_agents.py

# 2. Flip the flag and run as usual.
echo "MANAGED_AGENTS=1" >> .env
uvicorn app:app --reload
```

The setup script is idempotent — re-running it reuses existing IDs unless you
pass `--force`. With `MANAGED_AGENTS=0` (or `MOCK_MODE=1`), the Red Team
falls back to a legacy single-prompt auditor so the demo stays reliable.

---

## Pipeline architecture (9 agents, 3 of them concurrent)

```
User  ─WS─►  Qualifier  ──►  Interviewer  ──►  Analyzer (🧠)
                                                   │
                                                   ▼
                              Red Team Auditor (👤 Managed Agent)
                                                   │
                                                   ▼
                                           Board Presenter
                                                   │
                                   ┌───────────────┼───────────────┐
                                   ▼               ▼               ▼
                               Drafter     Threat Actor (🧠)   Closure Planner
                                   └───────────────┼───────────────┘
                                                   ▼
                                   Remediation Agent (🔧 tool_use)
                                                   │
                                                   ▼
                                 [ report.pdf · policy · incident · checklist · closure plan ]

           plus: Regulatory Monitor (👤 Managed Agent, 🌐 web_search)
                 · fires immediately on /api/subscribe
                 · re-runs on the asyncio scheduler (default: weekly)
                 · on-demand via /api/monitor/run

🧠 Extended Thinking   👤 Managed Agent   🔧 tool_use   🌐 web_search   ∥ asyncio.gather
```

### The 9 agents

| # | Agent | File | What it does | Opus features |
|---|---|---|---|---|
| 1 | **Qualifier** | `agents/qualifier.py` | 3 structured questions → decides if NIS2 applies directly (Annex I/II), indirectly (supply-chain per Art. 21(2)(d)), or not at all | prompt caching |
| 2 | **Interviewer** | `agents/interviewer.py` | Runs a compliance interview (min. 8, typically 10–14 questions), one at a time, plain business language, covering all 10 Art. 21(2) sub-paragraphs before wrapping | prompt caching, streaming |
| 3 | **Analyzer** | `agents/analyzer.py` | Extended-Thinking gap analysis — cross-references interview findings against the 10 requirements, outputs gap list with risk levels, business impact, article refs | Extended Thinking (🧠), prompt caching |
| 4 | **Red Team Auditor** | `agents/redteam_managed.py` | **Managed Agent.** Self-drives through 4 custom tools, investigates 4–6 sub-paragraphs in depth, issues PASS / CONDITIONAL / FAIL verdict. Typical run: ~13 tool invocations. | Managed Agent (👤), streaming |
| 5 | **Threat Actor** | `agents/threat_actor.py` | Extended Thinking — generates personalized attack scenarios based on YOUR specific gaps, not a generic threat catalogue | Extended Thinking (🧠), prompt caching |
| 6 | **Board Presenter** | `agents/board_presenter.py` | 5-slide executive deck with compliance-score gauge (0–100), key metrics, recommended budget | prompt caching |
| 7 | **Policy Drafter** | `agents/drafter.py` | Plain-language policy outlines for the top critical/high gaps, written in the user's language | prompt caching |
| 8 | **Closure Planner** | `agents/closure_planner.py` | For each top gap, generates a **7–14-day operational runbook**: day-by-day steps, verification checks, pre-drafted board email, team announcement, Definition of Done | prompt caching |
| 9 | **Remediation Agent** | `app.py:run_remediation_agent` | Orchestrates PDF generation for 4 documents + ENISA resource search. After the 2026-04-24 refactor this is **deterministic** (no `tool_choice: any`) and runs concurrently via `asyncio.gather` + `asyncio.to_thread` | tool use (🔧) |

### Key design decisions

**Why a pipeline, not one mega-prompt.**
Each agent has a focused system prompt, a narrow output contract (JSON schema
or marked JSON block), and its own failure mode. A parse error in the Drafter
doesn't blow up the whole run — the pipeline continues with an empty
`drafter_result` and the final PDF just omits the policies section. This is
cheaper (tight context per call), faster (prompt caching hits on every agent's
static system block), and more demo-reliable.

**Why concurrent post-audit.**
Drafter, Threat Actor, and Closure Planner all read the same inputs (gap
analysis + red-team verdict) and write to independent fields. Running them
sequentially wasted ~2 minutes. `asyncio.gather(..., return_exceptions=True)`
cuts that in ~3×, and any individual failure is caught and logged without
taking down the others.

**Why deterministic remediation, not tool_choice.**
An earlier version let Claude pick which PDF tools to call via
`tool_choice={"type": "any"}`. It would sometimes silently skip a document
("raz generuje, raz nie"). Replaced with a direct loop over
`_TOOL_GENERATORS`, each wrapped in `asyncio.to_thread` — WeasyPrint is sync
and CPU-bound, so running it inline would block the event loop and freeze
*every other active session* on the server for seconds.

**Why grounded in EUR-Lex verbatim.**
`scripts/fetch_nis2.py` parses the official EUR-Lex PDF with `pypdf` and
writes `data/frameworks/nis2_directive.json`. The auditor's
`lookup_requirement("b")` returns the exact Art. 21(2)(b) sentence — no
paraphrase, no hallucination. `nis2.json` is a summarised index that links
each requirement to its `article_ref`, `eurlex_url`, and verbatim
`directive_text`.

---

## The two Managed Agents

Built on Claude's Managed Agents beta (`managed-agents-2026-04-01`). Anthropic
runs the agent loop; we define the tools and starter prompt; Opus 4.7 decides
what to call and when.

### 1. Iterative Red Team Auditor

Replaces the legacy one-shot "here is a transcript, output a verdict JSON"
pattern. The auditor now has four custom tools:

- `lookup_requirement(article_ref)` — returns Art. 21(2) sub-paragraph text
  from EUR-Lex (e.g. `"b"` → full text of Art. 21(2)(b)).
- `lookup_gap(requirement_name)` — cross-references what the Analyzer flagged
  on that requirement.
- `lookup_interview_answer(topic)` — pulls the relevant company answers from
  the interview transcript.
- `finalize_verdict(verdict, summary, critical_failures, passed_checks, preparation)`
  — terminal tool. The only way to end the session.

A typical run looks like: pick a requirement → look up its text → pull the
company's answer → look up what the Analyzer said → decide if it's a real
gap → move to the next requirement → after 4–6 rounds, call `finalize_verdict`.
About **13 tool invocations per audit**, streamed live to the UI so the user
watches the auditor "work."

Timeouts & fallback: 300 s hard stream timeout. On timeout or any exception
the pipeline automatically falls back to `_run_legacy_redteam_oneshot` (the
old single-prompt auditor in `agents/redteam.py`). The user sees a brief
notice ("⚠ Managed Agents auditor did not respond — falling back to local
one-shot auditor") and the run continues.

### 2. Regulatory Monitor

A second Managed Agent that runs both **on-demand** (user clicks "Run now"
from the mailbox) **and on a schedule** (in-process asyncio loop —
`utils/monitor_scheduler.py`). On `/api/subscribe` the first run is fired
immediately in the background so a user sees alerts within minutes of
subscribing, not a week.

Per run:
- `lookup_user_profile()` — sector, language, open gaps
- 2–4 targeted `web_search` queries (NIS2 / CSIRT / ENISA / sector-specific news)
- `queue_alert(...)` — **only** when a finding touches one of this user's
  specific open gaps. Zero alerts is a valid run.
- `finalize_run(...)` — terminal tool

Alerts include source URLs, a severity (informational / important / urgent),
and which of the user's gaps they relate to, rendered in the user's language.

**Scheduler** (env-tunable):

| Var | Default | Purpose |
|---|---|---|
| `MONITOR_INTERVAL_HOURS` | `168` | how often the tick fires (weekly) |
| `MONITOR_STAGGER_SECONDS` | `30` | gap between per-user runs (avoid bursts) |
| `MONITOR_MIN_INTERVAL_HOURS` | `24` | skip profiles checked more recently |

Scheduler health is exposed at `GET /api/monitor/status`. SMTP delivery is
out of scope — alerts live in the in-app mailbox at `GET /api/alerts?user_id=…`.

### API endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Landing + chat SPA |
| `WS` | `/ws/{session_id}` | Full pipeline over a single WebSocket |
| `GET` | `/report/{session_id}` | Main PDF report (WeasyPrint, 45 s timeout) |
| `GET` | `/download/{session_id}/{tool_name}` | Tool PDFs (policy / incident / checklist / closure_plan) |
| `POST` | `/api/subscribe` | Save email + gaps as monitoring profile; fires first run in background |
| `POST` | `/api/monitor/run` | Trigger one monitor pass on-demand |
| `GET` | `/api/monitor/status` | Scheduler health: running, interval, last tick |
| `GET` | `/api/alerts?user_id=...` | List queued alerts |
| `GET` | `/api/benchmark?sector=...&size_bucket=...&user_score=...` | Anonymised percentile ranking against peers |
| `GET` | `/api/session/{session_id}/status` | Restore / resume a past session |
| `GET` | `/metrics` | Runtime counters: token usage, cache-hit ratio, managed-agents tool-call distribution |

---

## Tech stack

- **Runtime:** Python 3.11+, FastAPI, asyncio
- **Transport:** single WebSocket per session + HTTP for PDFs
- **AI:** `anthropic` SDK. `claude-opus-4-7` for all 9 agents;
  `claude-sonnet-4-6` for the Marek-demo persona and `TEST_MODE=1`.
- **Managed Agents:** `client.beta.agents.create_session()` +
  `client.beta.sessions.messages.create()` with custom tools and built-in `web_search`.
- **Extended Thinking:** `thinking={"type": "adaptive", "display": "summarized"}`,
  `output_config={"effort": "high"}`; thinking text surfaced in the UI
  behind a "Show reasoning" toggle.
- **Prompt caching:** `cache_control={"type": "ephemeral"}` on every agent's
  static system block. Each call logs `input_tokens`, `output_tokens`,
  `cache_read_input_tokens`, `cache_creation_input_tokens` (`_log_usage` in
  `app.py`) so cache effectiveness is measurable, not a claim.
- **Tool use:** 4 PDF generators (`utils/tools.py`) + 1 ENISA search.
  Called deterministically, wrapped in `asyncio.to_thread` to keep the event
  loop free for concurrent sessions.
- **PDF:** WeasyPrint + Jinja2; Archivo + IBM Plex Mono TTFs embedded.
  Main report: `templates/report.html`. Tool PDFs: `templates/tools/*.html`.
- **Frontend:** Vanilla JS + Tailwind CSS + `marked.js` (markdown rendering
  for agent messages). No build step.
- **NIS2 grounding:** `scripts/fetch_nis2.py` parses the EUR-Lex directive
  PDF into `data/frameworks/nis2_directive.json`; `nis2.json` is a
  summarised index.
- **Persistence:** SQLite (`data/regula.db`, gitignored) for assessment
  sessions, user profiles, and alerts — survives server restarts.

---

## Performance & cost

Numbers from real Opus 4.7 runs (logged to stdout as you demo):

| Stage | Typical wall-clock | Notes |
|---|---|---|
| Qualifier | ~3 s | 3 short turns |
| Interviewer | 3–5 min | user-paced; 10–14 questions |
| Analyzer | 30–60 s | Extended Thinking with 6k budget |
| Red Team (managed) | 60–120 s | ~13 tool calls |
| Threat Actor | 30–60 s | Extended Thinking with 8k budget |
| Board + Drafter + Closure (∥) | 60–120 s | concurrent via `asyncio.gather` |
| Remediation (4 PDFs + ENISA) | 5–10 s | concurrent via `asyncio.gather` + `asyncio.to_thread` |
| Report PDF | 1–3 s | WeasyPrint, offloaded to threadpool |
| **Total** | **~8–12 min** | user interview dominates |

`MOCK_MODE=1`: full pipeline in **~5 s**, no API calls, no keys required.

**Prompt caching is real.** After the first run, system-prompt cache hits
typically cover 80–95% of input tokens on every in-process agent. Grep
server logs for `cache_read=` to see it per call.

**Demo-safe hardening:**
- 180 s API timeout + `max_retries=1` (default was 10 × 60 s = "demo killer")
- 300 s hard timeout on the Managed-Agents auditor stream; automatic
  fallback to the legacy one-shot auditor on timeout
- 45 s PDF generation timeout
- WebSocket auto-reconnect on the client with session restore
- Input sanitation: 1500-char message cap, 80-message session cap, control/
  zero-width char stripping
- Fail-soft on every JSON parse: the pipeline continues with an empty result
  for the failing agent rather than dying

---

## Project layout

```
regula/
├── app.py                           # FastAPI + WebSocket + all /api endpoints
├── agents/
│   ├── qualifier.py
│   ├── interviewer.py
│   ├── analyzer.py                  # Extended Thinking
│   ├── redteam.py                   # legacy one-shot auditor (fallback)
│   ├── redteam_managed.py           # Managed-Agents iterative auditor
│   ├── monitor_managed.py           # Managed-Agents regulatory monitor
│   ├── threat_actor.py              # Extended Thinking
│   ├── board_presenter.py
│   ├── drafter.py
│   └── closure_planner.py           # day-by-day gap closure runbooks
├── scripts/
│   ├── fetch_nis2.py                # EUR-Lex PDF → JSON grounding
│   └── setup_managed_agents.py      # one-time agent + environment creation
├── data/frameworks/
│   ├── nis2.json                    # requirements index (summarised)
│   └── nis2_directive.json          # verbatim Art. 21(2) text + Annex I/II
├── utils/
│   ├── pdf.py                       # main WeasyPrint report generator
│   ├── tools.py                     # generate_{policy,incident,checklist,closure_plan}
│   ├── benchmark.py                 # anonymised percentile ranking
│   ├── session_store.py             # SQLite session persistence
│   ├── profile_store.py             # SQLite profiles + alerts
│   ├── monitor_scheduler.py         # asyncio loop that ticks the monitor agent
│   └── metrics.py                   # in-memory counters feeding GET /metrics
├── templates/
│   ├── report.html                  # main PDF report
│   └── tools/
│       ├── policy.html
│       ├── incident.html
│       ├── checklist.html
│       └── closure_plan.html
├── static/
│   ├── fonts/                       # Archivo + IBM Plex Mono TTFs
│   └── index.html                   # landing + chat + mailbox SPA
├── tests/
│   ├── mock_pipeline.py             # end-to-end smoke test
│   ├── test_parsing.py
│   └── test_pdf.py
├── CLAUDE.md                        # project rules (loaded by Claude Code)
├── requirements.txt
└── .env.example
```

---

## Configuration reference

All config via `.env`:

```dotenv
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Modes (pick zero or one)
TEST_MODE=1            # Sonnet 4.6, no Extended Thinking — cheap dev loop
MOCK_MODE=1            # no API calls, instant — offline demos

# Managed Agents (optional; leave empty to use legacy Red Team)
MANAGED_AGENTS=1
MANAGED_ENV_ID=env_...
REDTEAM_AGENT_ID=agent_...
MONITOR_AGENT_ID=agent_...
```

Populate the Managed-Agents IDs with `python scripts/setup_managed_agents.py`.

---

## Testing

```bash
# Unit tests — JSON parsing, PDF rendering (no server, no API)
python -m pytest tests/ -v

# End-to-end smoke in mock mode: start server in MOCK_MODE then run
MOCK_MODE=1 uvicorn app:app --reload &
python tests/mock_pipeline.py
```

---

## Known limitations

- **Not a legal document.** Regula's output is a draft starting point for
  legal review. It does not substitute for a qualified lawyer or a certified
  auditor. This is stated in every PDF footer and on the landing page.
- **Monitor delivery is in-app, not SMTP.** Alerts queue into
  `GET /api/alerts?user_id=…` and render in the mailbox UI. Email delivery
  would require SMTP credentials and deliverability work — out of scope.
- **Interview language is plain on purpose.** If the user already speaks
  fluent compliance jargon, some questions will feel basic — by design.
- **Marek demo is Sonnet 4.6, not Opus.** The persona doesn't need the top
  model and it cuts cost/latency on demos. Everything *about* Marek (the
  real pipeline agents) still runs on Opus 4.7.
- **Prompt caching TTL is 5 minutes.** Back-to-back runs hit cache; a run
  after a coffee break pays the cache-creation tokens again.
- **Metrics reset on restart.** `/metrics` is in-memory; Prometheus-style
  persistent scraping would need an external collector.

---

## Roadmap

- SMTP alert delivery (today alerts live in the in-app mailbox)
- Multi-user / multi-tenant (today each SQLite row is a user; no auth yet)
- Per-sector deep dives (healthcare, finance, digital infrastructure) beyond
  the current generic Art. 21(2) coverage
- Prometheus-compatible `/metrics` exporter for persistent scraping
- Additional frameworks: DORA (EU financial services), ISO 27001 mapping

---

## License & disclaimer

MIT — open source, self-hostable. Assessment data lives in a local SQLite
file; the only external call is to the Anthropic API (and, when enabled,
web searches from the Regulatory Monitor).

> **Disclaimer.** Regula's output is a draft starting point for legal review —
> not a final compliance document. Always consult a qualified legal or
> cybersecurity professional before implementing.

---

Built with **Claude Opus 4.7** · Cerebral Valley "Built with Opus 4.7" Hackathon 2026
