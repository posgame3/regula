# Regula — NIS2 Compliance Assessment Agent

Regula is an AI-powered compliance advisor that tells EU business owners in 15 minutes whether the NIS2 cybersecurity directive applies to them, where their gaps are, and what to do first — for free, in plain language, without a consultant.

Built with Claude Opus 4.7 for **Cerebral Valley Built with 4.7 Hackathon**.

---

## Quick start

```bash
git clone https://github.com/yourusername/regula.git
cd regula
pip install -r requirements.txt
cp .env.example .env          # add your Anthropic API key
python main.py
```

---

## Architecture

```
User
 │
 ▼
┌─────────────┐
│  Qualifier  │  3 questions → applies? scope? (essential/important/not_in_scope)
└──────┬──────┘
       │ JSON {applies, scope, confidence}
       ▼
┌─────────────┐
│ Interviewer │  10-14 plain-language questions → covers all 10 NIS2 Art.21 requirements
└──────┬──────┘
       │ JSON {findings, key_quotes, biggest_concern}
       ▼
┌─────────────┐
│  Analyzer   │  Automatic — maps findings to gaps with risk levels, costs, actions
└──────┬──────┘
       │ JSON {gaps[], priority_3, board_summary}
       ▼
┌─────────────┐
│  Red Team   │  Simulates NIS2 auditor — 5-7 hard questions targeting real gaps
└──────┬──────┘
       │ JSON {verdict, critical_failures, preparation_steps}
       ▼
┌─────────────┐
│   Drafter   │  Generates plain-language policy outlines for top critical gaps
└─────────────┘
       │ JSON {policies[]}
       ▼
  Full report
```

**Model**: `claude-opus-4-7` for all five agents  
**NIS2 requirements**: hardcoded in `data/frameworks/nis2.json` — the model never invents requirements  
**Languages**: English and Polish (detected automatically from user input)

---

## Project structure

```
regula/
├── main.py                    # CLI pipeline runner
├── agents/
│   ├── qualifier.py           # NIS2 applicability check
│   ├── interviewer.py         # 10-14 question gap discovery interview
│   ├── analyzer.py            # Automatic gap analysis
│   ├── redteam.py             # Simulated auditor inspection
│   └── drafter.py             # Policy outline generator
├── data/frameworks/nis2.json  # 10 NIS2 Art.21 requirements (hardcoded)
├── utils/pdf.py               # PDF export (coming soon)
├── static/index.html          # Web UI (coming soon)
├── requirements.txt
└── .env
```

---

## Output

For each company, Regula produces:

- **Qualifier result** — applies yes/no, entity type, confidence
- **Interview findings** — risk score 0-3 for each of 10 NIS2 requirements
- **Gap analysis** — plain-language gaps with business impact, first action, cost estimate
- **Audit simulation** — verdict (PASS / FAIL / CONDITIONS), fine exposure, critical failures
- **Policy drafts** — 2-4 simple policy outlines for top gaps, ready for legal review

---

## License

MIT — see [LICENSE](LICENSE)

> Disclaimer: Regula output is a draft starting point for legal review — not a final compliance document.
