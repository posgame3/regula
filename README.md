# Regula

> **Self-driving NIS2 compliance audit on Claude Opus 4.7.**
> 15 minutes. 13 tool calls. 5 remediation-ready PDFs. Zero consultants.

🌐 **Live** → [regula.digital](https://regula.digital)
💻 **Repo** → [github.com/posgame3/regula](https://github.com/posgame3/regula)
📁 Built for **Cerebral Valley · Built with Opus 4.7 · 2026 Hackathon**

---

## TL;DR

160,000 European companies are now in scope of the **NIS2 Directive (EU 2022/2555)**. Most don't know it. Fines reach €10M or 2% of global turnover. The cheapest path to clarity today is a **€1,500–€4,000 consultant**. It takes weeks.

**Regula replaces that consultant in 15 minutes.**

A 9-agent Claude Opus 4.7 pipeline that runs a **plain-language interview**, performs **gap analysis with Extended Thinking**, deploys a **fully-autonomous Red Team auditor on Managed Agents beta** (13 tool invocations against verbatim EUR-Lex text), runs three concurrent specialists (Threat Actor, Drafter, Closure Planner), and ships **5 remediation-ready PDFs** including a 14-day day-by-day closure runbook and a pre-drafted board email.

Plus a **second Managed Agent** that runs weekly via in-process asyncio scheduler, web-searches NIS2/CSIRT advisories, and queues alerts matching your specific gaps.

**Five Opus 4.7 capabilities. One product. Not five demos.**

---

## Five Opus 4.7 capabilities, working together

| Capability | How Regula uses it |
|---|---|
| 👤 **Managed Agents** (beta `managed-agents-2026-04-01`) | **Two production agents.** Red Team auditor self-drives 13 tool calls per session through verbatim Article 21(2) text. Regulatory Monitor runs weekly, web-searches news, queues gap-relevant alerts. Anthropic runs the loop; we ship the tools. |
| 🧠 **Extended Thinking** (adaptive, summarized) | Two reasoning agents — Analyzer and Threat Actor. Adaptive 6k–8k budget. Reasoning surfaced live in the UI behind a "Show reasoning" toggle, not hidden. |
| ⚡ **Prompt caching** (`cache_control: ephemeral`) | Every in-process agent's static system block. Logged per call as `cache_read_input_tokens` — measurable at `GET /metrics`. **Typical cache hit ratio: 87%.** Not a claim. |
| 🔧 **Parallel tool use** | 4 PDF generators + ENISA search via `asyncio.gather`. Deterministic, not `tool_choice: any` (which silently dropped documents in earlier builds). WeasyPrint offloaded to threadpool with `asyncio.to_thread` so the event loop stays free for concurrent sessions. |
| 📡 **Streaming** (WebSocket) | Single WebSocket per session. Every agent's tokens stream live to the browser. The full pipeline is a live conversation, not a batch job. |

---

## What the pipeline handles

Regula is **not a template generator.** Every agent personalizes its output to the specific company sitting in front of it — sector, size, gap profile, language, answers. There is no "scripted path." A 12-person logistics shop and a 200-person fintech go through the **same nine agents** and come out with **different gap tables, different threat scenarios, different closure plans, different policies, different board emails.**

**Scope coverage**

| What | How Regula adapts |
|---|---|
| **Direct scope** (Annex I/II) | Energy, transport, banking, financial markets, health, water, digital infrastructure, ICT service management, public administration, space, postal/courier, waste, chemicals, food, manufacturing of critical products, digital providers, research |
| **Indirect scope** (Art. 21(2)(d)) | Supply-chain entities — a small SaaS supplier whose clients are NIS2-covered hospitals or banks inherits indirect compliance pressure. **Most tools miss this. Regula's Qualifier catches it.** |
| **Size** | SME (8 employees) to mid-market (~500). The Closure Planner sizes runbooks to team capacity. |
| **Language** | Full **PL / EN** end-to-end. Every agent — interview, analysis, threat scenarios, policies, closure plans, board emails — runs in the user's language. |
| **Sub-paragraph coverage** | All 10 Art. 21(2) sub-paragraphs (a–j) are surfaced by the Interviewer regardless of what the user volunteers. The Analyzer cross-references each. |

**Personalization in action**

- The **Threat Actor** does not generate a generic threat catalogue. It models how an attacker would specifically exploit YOUR gap profile — e.g., *"no MFA on AWS root + patient records on S3 = ransomware blast radius covers 12 hospital contracts."*
- The **Closure Planner** does not paste a 14-day template. It writes a runbook matched to your specific gaps, ordered by exploit risk, sized to your team. A logistics operator with no IT lead gets a different sequence than a fintech with a CISO.
- The **Policy Drafter** writes outlines tailored to your business model. A hospital SaaS gets a different access-control policy than a chemical manufacturer — same Article 21(2)(i), different operational context.

## What you get in 15 minutes

Regardless of sector or size, every Regula run produces:

- **A scope verdict** with article citation: *direct (Annex I/II)*, *indirect (Art. 21(2)(d) supply-chain)*, or *out of scope*
- **A gap table** — every Article 21 sub-paragraph, status, risk level (critical / high / medium / low), business impact, deadline (1–12 months)
- **A Red Team verdict** — *PASS / CONDITIONAL / FAIL* with article-level citations and ~13 tool invocations from the Managed Agent
- **Personalized attack scenarios** for your specific gap profile (Extended Thinking)
- **Day-by-day closure runbook** — typically 7–14 days, with verification checks and a Definition of Done per step
- **Pre-drafted board email** ready to send
- **5 PDFs** ready for legal review: security policy, incident response plan, remediation checklist, closure plan, full report

## Demo persona — Marek

For jury demos and offline recording we ship a deterministic test persona: **Marek**, a Polish SaaS owner managing patient records for 12 hospitals. He's a **Sonnet 4.6 model** with a hardcoded company profile (`MAREK_PERSONA_SYSTEM` in `app.py`) that answers Regula's questions in real time. Click **"Watch Marek's story"** on `regula.digital` to see all nine agents run end-to-end without typing — useful when jury wants the full pipeline in 3 minutes after cache pre-warm.

Marek is one path through Regula. **Open chat mode and answer as your own company** to see the pipeline adapt — different sector, different gaps, different documents, every time.

---

## Pipeline architecture · 9 agents, 3 concurrent

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
                 · fires on /api/subscribe (immediate first run in background)
                 · re-runs weekly via asyncio scheduler
                 · on-demand via /api/monitor/run

🧠 Extended Thinking   👤 Managed Agent   🔧 tool_use   🌐 web_search   ∥ asyncio.gather
```

| # | Agent | Role | Opus features |
|---|---|---|---|
| 1 | **Qualifier** | 3 questions → decides if NIS2 applies directly (Annex I/II), indirectly (supply-chain per Art. 21(2)(d)), or not at all | prompt caching |
| 2 | **Interviewer** | 10–14 plain-language questions covering all 10 Art. 21(2) sub-paragraphs | streaming, prompt caching |
| 3 | **Analyzer** | Cross-references findings against the 10 requirements; outputs gap list with risk levels, business impact, article refs | 🧠 Extended Thinking, prompt caching |
| 4 | **Red Team Auditor** | **Managed Agent.** Self-drives 4 custom tools against verbatim EUR-Lex text. Issues PASS / CONDITIONAL / FAIL verdict. **~13 tool invocations per audit.** | 👤 Managed Agent, streaming |
| 5 | **Threat Actor** | Generates personalized attack scenarios specific to YOUR gaps — not a generic threat catalogue | 🧠 Extended Thinking, prompt caching |
| 6 | **Board Presenter** | 5-slide executive deck. Compliance-score gauge (0–100), key metrics, recommended budget | prompt caching |
| 7 | **Policy Drafter** | Plain-language policy outlines for top critical/high gaps, in user's language | prompt caching |
| 8 | **Closure Planner** | **7–14-day operational runbook** per top gap: day-by-day steps, verification checks, pre-drafted board email, team announcement, Definition of Done | prompt caching |
| 9 | **Remediation Agent** | Deterministic orchestration of 4 PDF generators + ENISA search via `asyncio.gather` + `asyncio.to_thread` | 🔧 tool use |

---

## The two Managed Agents

Anthropic runs the agent loop. We define the tools. **Opus 4.7 decides what to call and when.**

### 1 · Iterative Red Team Auditor

Replaces the legacy *"here's a transcript, output a verdict JSON"* pattern with an investigative agent that owns 4 custom tools:

```
lookup_requirement(article_ref)        → verbatim Art. 21(2) sub-paragraph from EUR-Lex
lookup_gap(requirement_name)           → what the Analyzer flagged on this requirement
lookup_interview_answer(topic)         → relevant company answers from the interview
finalize_verdict(...)                  → terminal tool. The only way to end the session.
```

Typical run: pick a sub-paragraph → pull its verbatim text → pull the company's actual answer → pull the Analyzer's classification → decide if it's a gap → repeat 4–6 times → call `finalize_verdict`. **Streamed live** to the UI so users watch the auditor *work*.

**Hardening:** 300 s stream timeout. On timeout or any exception, automatic fallback to the legacy one-shot auditor (`agents/redteam.py`). The user sees a brief notice; the run continues.

### 2 · Regulatory Monitor

A second Managed Agent that runs **on-demand** (mailbox button) **and on a schedule** (in-process asyncio loop). On `/api/subscribe` the first run fires immediately in the background — the user sees alerts within minutes, not a week.

```
lookup_user_profile()                  → sector, language, open gaps, last check
[built-in] web_search                  → 2–4 targeted queries (NIS2/CSIRT/sector news)
queue_alert(...)                       → only when finding touches an open gap
finalize_run(...)                      → terminal tool
```

Alerts include source URLs, severity (informational / important / urgent), gap-reference, rendered in user's language. **Zero alerts is a valid run** — we don't manufacture noise.

| Env | Default | Purpose |
|---|---|---|
| `MONITOR_INTERVAL_HOURS` | `168` | how often the tick fires (weekly) |
| `MONITOR_STAGGER_SECONDS` | `30` | gap between per-user runs |
| `MONITOR_MIN_INTERVAL_HOURS` | `24` | skip profiles checked recently |

Health: `GET /api/monitor/status`.

---

## Why NIS2, not "cybersecurity"?

NIS2 Article 21(2) is **not paperwork**. It enumerates **ten mandatory security controls**: incident handling, business continuity and backup discipline, supply-chain security, vulnerability management, cryptography, access management, multifactor authentication, cyber-hygiene training, and incident reporting. **These are the same controls a real attacker probes for and a real auditor checks.** Compliance with Article 21 *is* a real cybersecurity uplift — with legal teeth that "best practice" alone never has.

Regula does **not** replace your SOC, EDR, vulnerability scanner, or penetration tester. It identifies which of those ten controls are missing, models how an attacker would exploit each gap, and ships the documents required to close them. **Compliance is the legal frame; cybersecurity is the actual outcome.**

---

## Performance · measured, not claimed

Every Opus call logs `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` to stdout via `_log_usage`. Aggregated at `GET /metrics`:

```json
{
  "totals": {
    "input_tokens":         52840,
    "output_tokens":         6210,
    "cache_read_tokens":    47280,
    "cache_create_tokens":   5560,
    "cache_hit_ratio":        0.87
  },
  "managed_tool_calls": {
    "redteam.lookup_requirement":       5,
    "redteam.lookup_interview_answer":  4,
    "redteam.lookup_gap":               3,
    "redteam.finalize_verdict":         1,
    "monitor.web_search":               3,
    "monitor.queue_alert":              1,
    "monitor.finalize_run":             1
  },
  "counters": { "assessments_completed": 12, "pdf_generated": 60, "monitor_runs": 7 }
}
```

| Stage | Wall-clock | Notes |
|---|---|---|
| Qualifier | ~3 s | 3 short turns |
| Interviewer | 3–5 min | user-paced; 10–14 questions |
| Analyzer | 30–60 s | Extended Thinking, 6k budget |
| Red Team (managed) | 60–120 s | ~13 tool calls |
| Threat Actor | 30–60 s | Extended Thinking, 8k budget |
| Board + Drafter + Closure (∥) | 60–120 s | concurrent via `asyncio.gather` |
| Remediation (4 PDFs + ENISA) | 5–10 s | concurrent + `asyncio.to_thread` |
| Report PDF | 1–3 s | WeasyPrint, threadpool |
| **Total** | **~8–12 min** | user interview dominates |

`MOCK_MODE=1`: full pipeline in **~5 s**, no API calls, no key required — for offline demos and video recording.

**Demo-safe hardening:** 180 s API timeout with `max_retries=1` (Anthropic SDK default of 10×60s was a demo killer); 300 s Managed-Agents stream timeout with auto-fallback; 45 s PDF timeout; WebSocket auto-reconnect with session restore; fail-soft JSON parsing — a single agent's parse error never takes down the run.

---

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Landing + chat SPA |
| `WS` | `/ws/{session_id}` | Full pipeline over a single WebSocket |
| `GET` | `/report/{session_id}` | Main PDF report |
| `GET` | `/download/{session_id}/{tool_name}` | Tool PDFs (policy / incident / checklist / closure_plan) |
| `POST` | `/api/subscribe` | Save email + gaps; fires first monitor run in background |
| `POST` | `/api/monitor/run` | Trigger one monitor pass on-demand |
| `GET` | `/api/monitor/status` | Scheduler health |
| `GET` | `/api/alerts?user_id=...` | List queued alerts |
| `GET` | `/api/benchmark` | Anonymised percentile ranking against peers |
| `GET` | `/api/session/{session_id}/status` | Restore / resume past session |
| `GET` | `/metrics` | Token usage, cache-hit ratio, managed-agents tool-call distribution |

---

## Live demo · what to click

1. Open **[regula.digital](https://regula.digital)**.
2. Pick language (PL / EN).
3. Either:
   - **Chat mode (recommended)** — answer Regula's questions as your own company. ~10–14 questions, real adaptive flow. **This is the actual product.**
   - **"Watch Marek's story"** — Sonnet 4.6 demo persona auto-answers so jury can watch all nine agents run end-to-end without typing. ~3 minutes (after cache pre-warm). Test fixture, not the product.
4. Watch the stage bar: `qualify → interview → analyze → redteam (👤) → threat (🧠) → board → drafter + closure (∥) → remediation (🔧) → complete`.
5. At "complete", download the PDFs.
6. Optional: subscribe to **Regulatory Monitor** with your email — first run fires immediately in the background.

---

## Quick start

```bash
git clone https://github.com/posgame3/regula
cd regula
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...

# Production mode (Opus 4.7, real API calls)
uvicorn app:app --reload

# OR — fast iteration with Sonnet 4.6
TEST_MODE=1 uvicorn app:app --reload

# OR — instant mock pipeline, no API calls (for video recording)
MOCK_MODE=1 uvicorn app:app --reload
```

For long sessions, add WebSocket keepalive:
```bash
uvicorn app:app --reload --ws-ping-interval 30 --ws-ping-timeout 60
```

### Enabling Managed Agents

```bash
python scripts/setup_managed_agents.py    # one-time: creates agents + environment
echo "MANAGED_AGENTS=1" >> .env
uvicorn app:app --reload
```

The setup script is idempotent. With `MANAGED_AGENTS=0` (or `MOCK_MODE=1`), Red Team falls back to a legacy one-shot auditor — demo never breaks.

---

## Tech stack

Python 3.11+ · FastAPI · asyncio · `anthropic` SDK · WeasyPrint + Jinja2 · SQLite · Vanilla JS + Tailwind + `marked.js` (no build step) · Archivo + IBM Plex Mono fonts embedded.

**NIS2 grounding:** `scripts/fetch_nis2.py` parses the official EUR-Lex PDF with `pypdf` into `data/frameworks/nis2_directive.json`. The auditor's `lookup_requirement("b")` returns the exact Art. 21(2)(b) sentence — **no paraphrase, no hallucination.**

---

## Testing

```bash
python -m pytest tests/ -v                      # unit tests (parsing, PDF rendering)
MOCK_MODE=1 uvicorn app:app --reload &          # full pipeline smoke test
python tests/mock_pipeline.py
```

10 tests, ~2 s. Plus end-to-end mock smoke that exercises the entire 9-agent pipeline.

---

## Honest limits

- **Not a legal document.** Regula's output is a draft starting point for legal review. Not a substitute for a qualified lawyer or certified auditor. Stated in every PDF footer and on the landing page.
- **Monitor delivery is in-app, not SMTP.** Alerts queue at `GET /api/alerts?user_id=…`. Email delivery would need SMTP credentials and deliverability work — out of scope for hackathon.
- **Marek demo runs on Sonnet 4.6.** The persona doesn't need top model and it cuts cost/latency on demos. Everything *about* Marek (the real pipeline agents) still runs on Opus 4.7.

---

<details>
<summary><strong>Project layout</strong></summary>

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
│   ├── monitor_scheduler.py         # asyncio loop ticking the monitor agent
│   └── metrics.py                   # in-memory counters → GET /metrics
├── templates/
│   ├── report.html
│   └── tools/{policy,incident,checklist,closure_plan}.html
├── static/{fonts/, index.html}
├── tests/{mock_pipeline.py, test_parsing.py, test_pdf.py}
├── CLAUDE.md
├── requirements.txt
└── .env.example
```
</details>

<details>
<summary><strong>Configuration reference</strong></summary>

```dotenv
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Modes (zero or one)
TEST_MODE=1            # Sonnet 4.6, no Extended Thinking
MOCK_MODE=1            # no API calls, instant

# Managed Agents (optional)
MANAGED_AGENTS=1
MANAGED_ENV_ID=env_...
REDTEAM_AGENT_ID=agent_...
MONITOR_AGENT_ID=agent_...

# Monitor scheduler (optional, with sane defaults)
MONITOR_INTERVAL_HOURS=168
MONITOR_STAGGER_SECONDS=30
MONITOR_MIN_INTERVAL_HOURS=24
```

Populate Managed-Agents IDs with `python scripts/setup_managed_agents.py`.
</details>

---

## License

MIT — open source, self-hostable. Assessment data lives in local SQLite. Only external call: Anthropic API (and, when enabled, web searches from the Regulatory Monitor).

> **Disclaimer.** Regula's output is a draft starting point for legal review — not a final compliance document. Always consult a qualified legal or cybersecurity professional before implementing.

---

Built with **Claude Opus 4.7** · Cerebral Valley *Built with Opus 4.7* Hackathon · 2026
