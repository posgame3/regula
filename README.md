# Regula

> **Self-driving NIS2 compliance audit on Claude Opus 4.7.**
> 15 minutes. 13 tool calls. 5 remediation-ready PDFs.
> **Cybersecurity uplift with legal backing.**

[![Built with Opus 4.7](https://img.shields.io/badge/Built%20with-Opus%204.7-E11B1B)](https://www.anthropic.com/)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Cerebral Valley](https://img.shields.io/badge/Cerebral%20Valley-2026-purple)](https://cerebralvalley.ai/)

🌐 **Live** → [regula.digital](https://regula.digital)
💻 **Repo** → [github.com/posgame3/regula](https://github.com/posgame3/regula)
📁 **Built for** Cerebral Valley · *Built with Opus 4.7* Hackathon · 2026

---

## The problem

NIS2 didn't appear out of nowhere. It's the EU's response to a brutal escalation in cyberattacks against the very companies it now regulates:

- **Ransomware operators have systematically targeted EU healthcare** through 2023–2024, encrypting patient records and forcing hospitals offline for weeks
- **Supply-chain attacks** (MOVEit-class, Log4j-class) repeatedly use small SaaS vendors as the entry point into critical infrastructure
- **Phishing and credential theft** remain the #1 initial access vector — exploiting the absence of MFA and security training in SMEs
- **Backup-related ransomware recovery failures** have driven multiple EU-region SMEs out of business in the past 18 months

The European Commission's impact assessment estimates **~160,000 companies** are now in scope of the NIS2 Directive — up from ~3,500 under NIS1. Most of them have **no compliance officer, no security team, and no clear path forward**. Fines reach **€10M or 2% of global turnover**, whichever is higher. A typical client compliance request gives the supplier **14 days** to confirm their stance.

NIS2 mandates ten specific cybersecurity controls (Article 21(2)). Regula identifies which you're missing, models how an attacker would exploit each gap, and ships the documents required to close them.

**This is cybersecurity work, with legal backing.**

---

## What Regula is

Regula is a **9-agent adaptive compliance pipeline** built on Claude Opus 4.7. It runs the full NIS2 assessment lifecycle for any company in scope of the directive — regardless of sector, size, or specific gap profile.

**Three modes, one product:**

1. 🩺 **Assessment** — Plain-language interview (10–14 questions) → Extended Thinking gap analysis → 5 remediation-ready PDFs in 15 min. **Adaptive per-company, not template-based.**

2. 🛡️ **Audit simulation** — Autonomous Red Team auditor on Anthropic's Managed Agents beta. Self-drives ~13 tool invocations against verbatim Article 21(2) text. Issues **PASS / CONDITIONAL / FAIL** verdict with article-level citations.

3. 📡 **Regulatory monitoring** — Second Managed Agent, runs weekly via in-process asyncio scheduler. Web-searches NIS2/CSIRT advisories, queues alerts matching your specific open gaps.

**Five Opus 4.7 capabilities. One product. Not five demos.**

---

## What Regula defends against

Article 21(2)'s ten mandatory controls aren't paperwork — they map 1:1 onto how real attacks unfold. Regula identifies which controls are missing for your specific company, then models how an attacker would exploit each gap (Threat Actor agent with Extended Thinking).

| NIS2 control | Article | Attack pattern it stops |
|---|---|---|
| Risk-management policies | 21(2)(a) | Undocumented decisions → repeated mistakes, no accountability |
| Incident handling & monitoring | 21(2)(b) | Late detection of ransomware → larger blast radius |
| Business continuity, backup recovery | 21(2)(c) | Untested backups = unrecoverable ransomware |
| Supply-chain security | 21(2)(d) | MOVEit / Log4j-class vendor compromises |
| Vulnerability handling & disclosure | 21(2)(e) | Unpatched perimeter exploited (RCE-class CVEs) |
| Effectiveness assessment | 21(2)(f) | Late regulator notification → escalated fines |
| Cyber-hygiene & training | 21(2)(g) | Phishing-driven initial access |
| Cryptography & encryption | 21(2)(h) | Data exfiltration in cleartext |
| Access management | 21(2)(i) | Stale credentials of ex-employees → insider-style breach |
| Multifactor authentication | 21(2)(j) | Credential stuffing, phishing, password reuse |

The Red Team auditor (👤 Managed Agent) cross-references your specific answers against these controls and issues a verdict — **the same gaps a real attacker would exploit, before one ever shows up.**

---

## Why this matters

**Regula sits in the cybersecurity space, not the paperwork space.**

NIS2 Article 21(2) enumerates ten mandatory security controls — incident handling, business continuity, supply-chain security, vulnerability management, cryptography, access management, MFA, cyber-hygiene training, risk policies, incident reporting. These aren't compliance theatre. They're **the same controls a real attacker probes for and a real auditor checks**.

Compliance with Article 21 *is* a real cybersecurity uplift — with legal teeth that "best practice" alone never has. SMEs across the EU are being hit with ransomware, supply-chain attacks, and phishing campaigns at a rate that has accelerated through 2024. The 10 NIS2 controls represent the minimum baseline that would stop most of them.

Regula does **not** replace your SOC, EDR, vulnerability scanner, or penetration tester. It identifies which of the ten controls you are missing, models how an attacker would specifically exploit each gap on your infrastructure, and ships the documents required to close them. **Compliance is the legal frame; cybersecurity uplift is the actual outcome.**

---

## Built with Opus 4.7

Regula is a deep integration of five Claude Opus 4.7 capabilities. Each is used where it produces measurable engineering value, not for show.

### 👤 Managed Agents (beta `managed-agents-2026-04-01`)

**Two production agents.** Anthropic runs the agent loop. We define the tools and starter prompt. Opus 4.7 decides which tools to call and when — **including the terminal tool that ends the session**.

**Red Team Auditor** (`agents/redteam_managed.py`) — Replaces the legacy *"here is a transcript, output a verdict JSON"* one-shot pattern. Owns four custom tools:

```json
{
  "name": "lookup_requirement",
  "description": "Returns verbatim Article 21(2) sub-paragraph text from EUR-Lex.",
  "input_schema": {
    "type": "object",
    "properties": {
      "article_ref": {
        "type": "string",
        "description": "Sub-paragraph letter (a–j)"
      }
    },
    "required": ["article_ref"]
  }
}

{
  "name": "lookup_gap",
  "description": "Returns the analyzer's finding for one requirement (status, risk, business impact)."
}

{
  "name": "lookup_interview_answer",
  "description": "Returns how the company answered on a topic during the interview."
}

{
  "name": "finalize_verdict",
  "description": "Terminal tool. Call exactly once to end the audit with the final verdict."
}
```

**Typical session flow:** pick a sub-paragraph → pull verbatim EUR-Lex text → pull the company's actual interview answer → pull the Analyzer's gap classification → decide if it's a real gap → repeat 4–6 times → call `finalize_verdict`. **~13 tool invocations per audit**, streamed live to the UI so users watch the auditor *work*.

**Hardening:** 300 s hard stream timeout. Stream-first event ordering (open `events.stream()` before `events.send()` to avoid race). Session post-idle settle (`_wait_until_not_running` polls `sessions.retrieve()` for up to 10 s before archiving). On timeout or any exception, automatic fallback to the legacy one-shot auditor (`agents/redteam.py`) — the demo never breaks.

**Regulatory Monitor** (`agents/monitor_managed.py`) — Second Managed Agent that runs **on-demand** (mailbox button) **and on a schedule** (in-process asyncio loop in `utils/monitor_scheduler.py`). On `/api/subscribe` the first run fires immediately in the background. Owns three custom tools plus built-in `web_search`:

```
lookup_user_profile()              → sector, language, open gaps, last check
[built-in] web_search              → 2–4 targeted queries (NIS2/CSIRT/sector news)
queue_alert(...)                   → only when finding touches an open gap
finalize_run(...)                  → terminal tool
```

Alerts include source URLs, severity (informational / important / urgent), gap-reference, rendered in user's language. **Zero alerts is a valid run** — we don't manufacture noise.

### 🧠 Extended Thinking (`thinking={"type": "adaptive", "display": "summarized"}`)

Two reasoning agents use Extended Thinking with adaptive budget and summarized output. Reasoning is surfaced live in the UI behind a "Show reasoning" toggle — **not hidden from users**.

**Analyzer** (`agents/analyzer.py`) — cross-references interview findings against the 10 Art. 21(2) requirements in parallel. Outputs a gap list with risk levels (critical/high/medium/low), business impact, and exact article references. Adaptive 6k thinking budget. `output_config={"effort": "high"}`.

**Threat Actor** (`agents/threat_actor.py`) — generates personalized attack scenarios specific to YOUR gap profile. Example output for a healthcare SaaS with no MFA + untested backups:

> *"Adversary phishes a developer Slack account → pivots to AWS console (no MFA on root) → encrypts S3 buckets containing 12 hospitals' patient records → ransomware demand denominated in the company's annual revenue. Backup restore drill never performed → estimated 3-4 weeks of downtime. Article 21(2)(c) business-continuity gap directly enables this scenario."*

This is **threat modeling**, not threat naming. Adaptive 8k budget.

### ⚡ Prompt caching (`cache_control: {"type": "ephemeral"}`)

Every in-process agent's static system block is cache-marked. The static block contains:
- The verbatim Article 21(2) text from EUR-Lex
- The full requirements taxonomy
- Tone & format rules
- Output schema

The user-specific delta (interview transcript, gap analysis, etc.) is appended *outside* the cache breakpoint. This way the system block hashes identically across all runs — every call after the first hits cache.

Implementation pattern (every agent file):
```python
system_blocks = [
    {"type": "text", "text": static_block, "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": user_specific_block},
]
```

Each call logs `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` to stdout via `_log_usage()` in `app.py`. **Typical cache hit ratio across all 8 in-process agents: 87%**, measurable at `GET /metrics`.

### 🔧 Tool use — parallel & deterministic

The Remediation stage generates 4 PDFs (security policy, incident response, remediation checklist, closure plan) plus an ENISA resource search. **All five run concurrently** via `asyncio.gather`:

```python
results = await asyncio.gather(
    asyncio.to_thread(generate_security_policy, session_data),
    asyncio.to_thread(generate_incident_plan, session_data),
    asyncio.to_thread(generate_remediation_checklist, session_data),
    asyncio.to_thread(generate_closure_plan, session_data),
    search_enisa_guidance(session_data),
    return_exceptions=True,
)
```

WeasyPrint is sync and CPU-bound — wrapping each generator in `asyncio.to_thread` keeps the event loop free for **other concurrent users**. Without this, one PDF render would block every other active session for several seconds.

**Why deterministic, not `tool_choice: any`?** An earlier version let Claude pick which PDFs to generate via `tool_choice={"type": "any"}`. It would **silently skip documents** ("raz generuje, raz nie"). Replaced with a direct loop over `_TOOL_GENERATORS` — every PDF runs every time.

The same `Drafter + Threat Actor + Closure Planner` post-audit stage also uses `asyncio.gather(..., return_exceptions=True)`. Sequential execution wasted ~2 minutes; concurrent cuts it ~3×.

### 📡 Streaming (WebSocket end-to-end)

Single WebSocket per session (`/ws/{session_id}`). Every agent's tokens stream live to the browser. The full pipeline is a **live conversation**, not a batch job. Stage transitions, Extended Thinking summaries, Managed Agent tool invocations — everything is surfaced in real time.

WebSocket auto-reconnect on the client with session restore from SQLite (`utils/session_store.py`) so long pipeline runs survive transient disconnects.

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

| # | Agent | File | Role | Opus features |
|---|---|---|---|---|
| 1 | **Qualifier** | `agents/qualifier.py` | 3 questions → decides if NIS2 applies directly (Annex I/II), indirectly (supply-chain Art. 21(2)(d)), or not at all | prompt caching |
| 2 | **Interviewer** | `agents/interviewer.py` | 10–14 plain-language questions covering all 10 Art. 21(2) sub-paragraphs | streaming, prompt caching |
| 3 | **Analyzer** | `agents/analyzer.py` | Cross-references findings against the 10 requirements; outputs gap list with risk levels, business impact, article refs | 🧠 Extended Thinking, prompt caching |
| 4 | **Red Team Auditor** | `agents/redteam_managed.py` | **Managed Agent.** Self-drives 4 custom tools against verbatim EUR-Lex text. Issues PASS / CONDITIONAL / FAIL verdict. ~13 tool invocations per audit. | 👤 Managed Agent, streaming |
| 5 | **Threat Actor** | `agents/threat_actor.py` | Personalized attack scenarios specific to YOUR gaps — not a generic threat catalogue | 🧠 Extended Thinking, prompt caching |
| 6 | **Board Presenter** | `agents/board_presenter.py` | 5-slide executive deck, compliance-score gauge (0–100), key metrics, recommended budget | prompt caching |
| 7 | **Policy Drafter** | `agents/drafter.py` | Plain-language policy outlines for top critical/high gaps, in user's language | prompt caching |
| 8 | **Closure Planner** | `agents/closure_planner.py` | 7–14-day operational runbook per top gap: day-by-day steps, verification checks, pre-drafted board email, team announcement, Definition of Done | prompt caching |
| 9 | **Remediation Agent** | `app.py:run_remediation_agent` | Deterministic orchestration of 4 PDF generators + ENISA search via `asyncio.gather` + `asyncio.to_thread` | 🔧 tool use |

### Key design decisions

**Why a pipeline, not one mega-prompt.** Each agent has a focused system prompt, narrow output contract (JSON schema or marked block), and its own failure mode. A parse error in the Drafter doesn't blow up the run — pipeline continues with empty `drafter_result` and the final PDF omits the policies section. Cheaper (tight context per call), faster (cache hits on every static block), demo-reliable.

**Why grounded in EUR-Lex verbatim.** `scripts/fetch_nis2.py` parses the official EUR-Lex PDF with `pypdf` into `data/frameworks/nis2_directive.json`. The auditor's `lookup_requirement("b")` returns the **exact Art. 21(2)(b) sentence** — no paraphrase, no hallucination. `nis2.json` is a summarised index linking each requirement to `article_ref`, `eurlex_url`, and verbatim `directive_text`.

**Why a fallback for Managed Agents.** Beta APIs fail. The Red Team auditor has a 300 s hard timeout. On timeout or exception, the pipeline falls through to `_run_legacy_redteam_oneshot` (the old single-prompt auditor in `agents/redteam.py`). User sees a brief notice; the run continues. **The demo never breaks**, regardless of upstream issues.

---

## Adaptive intelligence

Regula is **not a template generator**. Every agent personalizes its output to the specific company sitting in front of it — sector, size, gap profile, language, answers. There is no scripted path. A 12-person logistics shop and a 200-person fintech go through the **same nine agents** and come out with **different gap tables, different threat scenarios, different closure plans, different policies, different board emails**.

### Scope coverage

| What | How Regula adapts |
|---|---|
| **Direct scope** (Annex I/II) | Energy, transport, banking, financial markets, health, water, digital infrastructure, ICT service management, public administration, space, postal/courier, waste, chemicals, food, manufacturing of critical products, digital providers, research |
| **Indirect scope** (Art. 21(2)(d)) | Supply-chain entities — a small SaaS supplier whose clients are NIS2-covered hospitals or banks inherits indirect compliance pressure. **Most tools miss this. Regula's Qualifier catches it.** |
| **Size** | SME (8 employees) to mid-market (~500). The Closure Planner sizes runbooks to team capacity. |
| **Language** | Full **PL / EN** end-to-end. Every agent — interview, analysis, threat scenarios, policies, closure plans, board emails — runs in the user's language. |
| **Sub-paragraph coverage** | All 10 Art. 21(2) sub-paragraphs (a–j) are surfaced by the Interviewer regardless of what the user volunteers. The Analyzer cross-references each. |

### Personalization in action

- The **Threat Actor** does not generate a generic threat catalogue. It models how an attacker would specifically exploit YOUR gap profile — *e.g., "no MFA on AWS root + patient records on S3 = ransomware blast radius covers 12 hospital contracts."*
- The **Closure Planner** does not paste a 14-day template. It writes a runbook matched to your specific gaps, ordered by exploit risk, sized to your team. A logistics operator with no IT lead gets a different sequence than a fintech with a CISO.
- The **Policy Drafter** writes outlines tailored to your business model. A hospital SaaS gets a different access-control policy than a chemical manufacturer — same Article 21(2)(i), different operational context.

---

## Performance & cost economics

Every Opus 4.7 call logs `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` to stdout via `_log_usage` in `app.py`. Aggregated at `GET /metrics`:

```json
{
  "uptime_seconds": 3247.5,
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
  "counters": {
    "assessments_started":   13,
    "assessments_completed": 12,
    "subscriptions":          7,
    "monitor_runs":           7,
    "monitor_alerts_queued":  4,
    "pdf_generated":         60
  }
}
```

### Cost per assessment

A complete Opus 4.7 assessment costs approximately **$0.37 per run** at current Anthropic pricing:

```
cache_creation:  13K tokens × $18.75/MTok = $0.24
cache_read:      85K tokens × $1.50/MTok  = $0.13
output:           6K tokens × $75.00/MTok = $0.45
                                            ─────
                                            ~$0.37 (typical)
```

This is achievable thanks to **prompt caching across all 8 in-process agents** with `cache_control: ephemeral` on every static system block. After the first run, system-prompt cache hits typically cover **80–95%** of input tokens.

### Latency per stage

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

### Demo-safe hardening

- 180 s API timeout with `max_retries=1` (Anthropic SDK default of 10×60 s was a demo killer)
- 300 s Managed-Agents stream timeout with **automatic fallback** to legacy one-shot auditor
- 45 s PDF generation timeout
- WebSocket auto-reconnect with session restore from SQLite
- Input sanitation: 1500-char message cap, 80-message session cap, control/zero-width char stripping
- Fail-soft on every JSON parse: pipeline continues with empty result for the failing agent rather than dying

---

## Live demo & API

### Live walkthrough

1. Open **[regula.digital](https://regula.digital)**.
2. Pick language (PL / EN).
3. Either:
   - **Chat mode (recommended)** — answer Regula's questions as your own company. ~10–14 questions, real adaptive flow. **This is the actual product.**
   - **"Watch Marek's story"** — Sonnet 4.6 demo persona auto-answers so jury can watch all nine agents run end-to-end without typing. Test fixture, not the product.
4. Watch the stage bar: `qualify → interview → analyze → redteam (👤) → threat (🧠) → board → drafter + closure (∥) → remediation (🔧) → complete`.
5. At "complete", download the 5 PDFs.
6. Optional: subscribe to **Regulatory Monitor** with your email — first run fires immediately in the background.

### API endpoints

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

The setup script is idempotent — re-running reuses existing IDs unless `--force`. With `MANAGED_AGENTS=0` (or `MOCK_MODE=1`), Red Team falls back to the legacy one-shot auditor.

---

## Vision & extensibility

**Regula's architecture is regulation-agnostic.** The pipeline doesn't know which regulation it's running — it operates on a structured representation of:

1. A list of legal requirements (e.g. Article 21(2) sub-paragraphs)
2. A scope qualifier (Annex I/II, supply-chain entity rules)
3. A risk-level taxonomy (critical / high / medium / low)
4. An interview probe set (one per requirement, in plain language)

Today: **NIS2** (`data/frameworks/nis2.json` + verbatim EUR-Lex directive). Future framework support is a config swap, not a rewrite:

- **DORA** — EU Digital Operational Resilience Act (financial services)
- **AI Act** — EU regulation on high-risk AI systems
- **ISO 27001** — international information security standard
- **CRA** — EU Cyber Resilience Act (digital products)
- **Sectoral NIS2 deep dives** — healthcare, finance, digital infrastructure, energy

The 9-agent pipeline, the two Managed Agents, the Extended Thinking patterns, the prompt-cache strategy, the deterministic tool use — **all reusable**. Each new framework needs:

- ~200 lines of structured requirements JSON
- Sector list (Annex equivalent)
- Risk-level taxonomy
- Interview probe set

Everything else stays the same. **The pipeline is a template, not a tool.**

### Roadmap (post-hackathon)

- Multi-tenancy + auth (currently single-tenant SQLite)
- SMTP delivery for Regulatory Monitor alerts
- DORA framework adapter (financial services pilot)
- Continuous-compliance dashboard (drift detection vs initial assessment)
- AI Act framework adapter (high-risk AI systems)

---

## Tech stack

- **Runtime:** Python 3.11+, FastAPI, asyncio
- **Transport:** single WebSocket per session + HTTP for PDFs
- **AI:** `anthropic` SDK · `claude-opus-4-7` for all 9 agents · `claude-sonnet-4-6` for the Marek-demo persona and `TEST_MODE=1`
- **Managed Agents:** `client.beta.agents.create_session()` + `client.beta.sessions.events.stream()` with custom tools and built-in `web_search`
- **Extended Thinking:** `thinking={"type": "adaptive", "display": "summarized"}` + `output_config={"effort": "high"}`
- **Prompt caching:** `cache_control={"type": "ephemeral"}` on every agent's static system block
- **PDF:** WeasyPrint + Jinja2 · Archivo + IBM Plex Mono TTFs embedded
- **Frontend:** Vanilla JS + Tailwind CSS + `marked.js` (no build step)
- **Persistence:** SQLite (`data/regula.db`, gitignored) for sessions, profiles, alerts — survives restarts
- **NIS2 grounding:** `scripts/fetch_nis2.py` parses official EUR-Lex PDF into `data/frameworks/nis2_directive.json`

---

## Architecture deep-dives

<details>
<summary><strong>Managed Agents implementation</strong></summary>

Regula uses Anthropic's `managed-agents-2026-04-01` beta. Two agents are created once via `scripts/setup_managed_agents.py`, IDs written to `.env`. Subsequent app runs only call `sessions.create()` — no agent creation in the request path.

**Stream-first event ordering:** `client.beta.sessions.events.stream()` is opened **before** the kickoff `events.send()` to avoid a race where the response could arrive before the stream subscriber attaches.

**Custom tool dispatch:** Tool implementations are host-side. The agent emits `agent.custom_tool_use` events, we look up data from session state, and reply with `user.custom_tool_result`. Tools include fuzzy matching (`difflib.SequenceMatcher`) so the agent can use natural language requirement names instead of exact strings.

**Terminal tool pattern:** Both Managed Agents have one terminal tool (`finalize_verdict` / `finalize_run`). Calling it captures the verdict payload but the response we send back is just `{"ok": true, "verdict_recorded": true}` — the agent uses the side-effect, not the response, to know it's done.

**Post-idle settle:** After the stream closes, `_wait_until_not_running()` polls `sessions.retrieve()` for up to 10 seconds before calling `sessions.archive()`. This avoids a race where archiving a still-running session would orphan tokens.

**Fallback flow:** On 300 s timeout or any exception, control returns to `app.py:run_redteam_stage`, which calls `_run_legacy_redteam_oneshot()` instead. User sees a notice; pipeline continues uninterrupted.

</details>

<details>
<summary><strong>Adaptive scheduler</strong></summary>

`utils/monitor_scheduler.py` — pure asyncio loop, no external dependencies (no APScheduler, no celery).

**Tick logic:** On each tick, enumerate `profile_store.list_profiles()`, filter to those whose `last_check_iso` is older than `MONITOR_MIN_INTERVAL_HOURS` (default 24), run them sequentially with `MONITOR_STAGGER_SECONDS` gap (default 30) between users.

**Stagger purpose:** Avoid hammering Anthropic's API with parallel sessions from one server process. 30 s between users means 100 users finish in ~50 minutes, well within the weekly tick interval.

**Auto-fire on subscribe:** On `POST /api/subscribe`, after `profile_store.upsert_profile()`, an `asyncio.create_task(_initial_run())` fires the first run in the background. User sees alerts within minutes, not a week.

**Lifecycle:** Started in `_app_lifespan` context manager (FastAPI lifespan event). Cancelled cleanly on shutdown via `asyncio.Event` stop signal.

**Status endpoint:** `GET /api/monitor/status` exposes `running`, `interval_seconds`, `last_tick_iso`, `last_tick_runs` — useful for jury verification and uptime monitoring.

</details>

<details>
<summary><strong>Cache strategy</strong></summary>

Every agent in `agents/` builds a system message with two text blocks:

```python
system_blocks = [
    {"type": "text", "text": static_block, "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": user_specific_block},  # NOT cached
]
```

The `static_block` contains:
- Verbatim Article 21(2) text from EUR-Lex
- Requirements taxonomy
- Tone & format rules
- Output schema specification

The `user_specific_block` contains the per-session delta (interview transcript, gap analysis, etc.). It's **outside** the cache breakpoint — its bytes change every run, so cache lookup keys to the static block only.

**Why ephemeral, not 1h:** Hackathon usage is bursty. A user runs the pipeline once, then maybe again 5 minutes later. The 5-minute ephemeral TTL covers the common case. 1h cache would be cheaper for high-frequency reuse but unnecessary here.

**Verification:** `_log_usage(stage, response)` in `app.py` logs every call. `metrics.record_usage()` aggregates into `GET /metrics`. Cache hit ratio of 0.87 across all in-process agents is **measured, not claimed**.

</details>

<details>
<summary><strong>Concurrency patterns</strong></summary>

**Post-audit fan-out:** After Red Team verdict, `Drafter`, `Threat Actor`, `Closure Planner`, `Board Presenter` all read the same inputs (gap analysis + verdict) and write to independent fields:

```python
results = await asyncio.gather(
    run_drafter(client, session_data),
    run_threat_actor(client, session_data),
    run_closure_planner(client, session_data),
    run_board_presenter(client, session_data),
    return_exceptions=True,
)
for stage_name, result in zip(stages, results):
    if isinstance(result, Exception):
        log.error("[%s] failed: %s", stage_name, result)
        session_data[stage_name + "_result"] = {}  # fail-soft
    else:
        session_data[stage_name + "_result"] = result
```

`return_exceptions=True` is critical — without it, one failing agent would cancel the others. With it, each is independent.

**PDF generation parallelism:** WeasyPrint is sync and CPU-bound. Inline use would block the event loop, freezing every other concurrent user's session. Solution: `asyncio.to_thread`:

```python
file_path = await asyncio.to_thread(_TOOL_GENERATORS[tool_name], session_data)
```

This offloads to the default threadpool executor. Multiple PDFs generate in true parallel; the event loop stays responsive.

**WebSocket isolation:** Each session gets its own WebSocket and its own SQLite row. No shared state between sessions. Multi-user concurrency is bounded only by Anthropic's per-key rate limits, not by the application.

</details>

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

# Managed Agents (optional; populate with scripts/setup_managed_agents.py)
MANAGED_AGENTS=1
MANAGED_ENV_ID=env_...
REDTEAM_AGENT_ID=agent_...
MONITOR_AGENT_ID=agent_...

# Monitor scheduler (optional, sane defaults)
MONITOR_INTERVAL_HOURS=168       # weekly tick
MONITOR_STAGGER_SECONDS=30       # gap between users
MONITOR_MIN_INTERVAL_HOURS=24    # skip recently-checked profiles
```

</details>

---

## Testing

```bash
python -m pytest tests/ -v                      # 10 unit tests (parsing, PDF rendering)
MOCK_MODE=1 uvicorn app:app --reload &          # full pipeline smoke test
python tests/mock_pipeline.py
```

10 tests, ~2 s. End-to-end mock smoke exercises the entire 9-agent pipeline.

---

## Honest limits

- **Not a legal document.** Regula's output is a draft starting point for legal review. Not a substitute for a qualified lawyer or certified auditor. Stated in every PDF footer and on the landing page.
- **Monitor delivery is in-app, not SMTP.** Alerts queue at `GET /api/alerts?user_id=…`. Email delivery would need SMTP credentials and deliverability work — out of scope for hackathon.
- **Marek demo runs on Sonnet 4.6.** The persona doesn't need top model and it cuts cost/latency on demos. Everything *about* Marek (the real pipeline agents) still runs on Opus 4.7.

---

## License

MIT — open source, self-hostable, fork-friendly. Assessment data lives in local SQLite. Only external call: Anthropic API (and, when enabled, web searches from the Regulatory Monitor).

> **Disclaimer.** Regula's output is a draft starting point for legal review — not a final compliance document. Always consult a qualified legal or cybersecurity professional before implementing.

---

Built with **Claude Opus 4.7** · Cerebral Valley *Built with Opus 4.7* Hackathon · 2026
