---
description: Improve and iterate on the Regula NIS2 PDF report. Use when the user wants to improve report layout, fix rendering issues, add new sections, preview the PDF, or debug WeasyPrint problems.
argument-hint: What to improve or fix (optional)
---

# PDF Report Improvement Skill

You are helping improve the Regula NIS2 compliance PDF report.

## Key files
- `templates/report.html` — Jinja2 template rendered by WeasyPrint (currently 701 lines, 7 sections)
- `utils/pdf.py` — `generate_report_pdf(session_data, language)` — renders template to bytes
- `agents/` — each agent outputs data consumed by the template

## Report structure (7 sections)
1. **Qualification Summary** — `session.qualifier_result` (applies, scope, confidence, reasoning)
2. **Compliance Score** — `session.gap_analysis` + score from `session.board_slides.slides[1].score`
3. **Gap Analysis Table** — `session.gap_analysis.gaps[]` (requirement, status, risk_level, what_to_do, estimated_effort, estimated_cost)
4. **Top 3 Priority Actions** — `session.gap_analysis.priority_3[]`
5. **Audit Simulation Verdict** — `session.redteam_result` or `redteam_html` (markdown fallback)
6. **Attack Scenarios** — `session.threat_actor_result.scenarios[]`
7. **Policy Drafts** — `session.drafter_result.policies[]`

## Rendering pipeline
```
Jinja2 template → HTML string → WeasyPrint HTML(string=..., base_url=BASE_DIR).write_pdf()
```
Language: `language` variable is `"pl"` or `"en"`, controls all translations via `is_pl` flag.

## WeasyPrint CSS constraints
WeasyPrint uses Pango/Cairo — NOT a browser engine. Limitations to keep in mind:
- No `flexbox` or `grid` — use `display: table` / `table-cell` for multi-column layouts
- No CSS variables (`--var`) — hardcode values
- Limited `@page` support — `@bottom-left`, `@bottom-right` work; `@top-*` is unreliable
- `page-break-before: always` → use this, not `break-before: page`
- No `position: sticky/fixed` — only `static`, `relative`, `absolute`
- `border-radius` works but `box-shadow` may not render
- Fonts: only system fonts or fonts loaded via `@font-face` with file path — Google Fonts won't work
- `content` in `::before`/`::after` pseudo-elements works
- Images: use absolute file paths or base64 inline

## How to preview the PDF
```bash
# Start with mock data (no API calls):
MOCK_MODE=1 uvicorn app:app --reload

# Then trigger PDF download via the UI, or call directly:
python3 -c "
from utils.pdf import generate_report_pdf
import json, pathlib

# Load mock session data (from tests/mock_pipeline.py or build minimal dict)
session = {
    'qualifier_result': {'applies': True, 'scope': 'important', 'confidence': 'high', 'reasoning': 'Test'},
    'gap_analysis': {'overall_risk': 'high', 'headline': 'Test headline', 'good_news': 'Good news', 'gaps': [], 'priority_3': []},
}
pdf_bytes = generate_report_pdf(session, 'pl')
pathlib.Path('/tmp/test_report.pdf').write_bytes(pdf_bytes)
print('Saved to /tmp/test_report.pdf')
"
open /tmp/test_report.pdf
```

## Common improvements to make
- **Visual hierarchy**: add color-coded risk summary bar at top of each gap row
- **Executive summary**: add a page-0 summary before section 1 with key numbers
- **Charts**: WeasyPrint can render SVG inline — use for simple bar/donut charts
- **Table of contents**: add a simple TOC after the header using anchors
- **Typography**: tighten line-height and padding for denser information
- **Cover page**: add a full-page cover before section 1 (use `@page :first` rule)

## Task
$ARGUMENTS

If no specific task is given: read the current template, identify the 3 most impactful improvements for readability and professionalism, then propose them with mockups (describe the HTML/CSS change) before implementing.

Always preview changes by generating a test PDF before declaring the task done.
