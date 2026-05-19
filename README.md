# UI Fidelity Checker

Catch design-to-build drift before QA does.

UI Fidelity Checker compares a Figma design against a screenshot of the
implemented UI and produces a precise, actionable report: what is wrong, the
expected vs. actual value, a suggested fix, a PASS/FAIL verdict, an annotated
screenshot, and a Copilot-ready Markdown fix list.

It was built to close the gap developers and testers constantly hit — *"the
build doesn't quite match the design"* — by turning a vague impression into a
concrete, prioritised punch list.

---

## What it does

- **Image vs. image (default, no setup):** drop a screenshot/export of the
  Figma frame and a screenshot of the running build. The tool diffs them.
- **Figma API (optional):** paste a Figma link instead of a design image
  (requires a Figma seat with API/file access).
- **Dynamic section detection:** when you add the design image, the tool reads
  it and offers the actual sections it finds (header, sidebar, cards, charts…)
  so you can scope the comparison to just one part of the screen.
- **PASS / FAIL verdict:** FAIL if any high-severity deviation exists.
- **Severity-ranked, expandable findings:** each issue shows the design value,
  the build value, a plain-English explanation, and a one-line fix.
- **Annotated screenshot:** the build image with numbered boxes drawn on each
  issue, downloadable as a PNG.
- **Markdown fix list:** one click exports a checkbox task list (grouped by
  priority, with expected/actual/fix) — paste straight into Copilot/Cursor.

---

## How it works

A small Flask web app sends the design and build images to a vision model with
a structured-output schema. Findings come back as JSON and are rendered as an
interactive report. Two model backends are supported:

| Backend | Cost | Notes |
| --- | --- | --- |
| Google Gemini | Free tier | Default if `GEMINI_API_KEY` is set. |
| Anthropic Claude | Paid | Used if only `ANTHROPIC_API_KEY` is set. Higher-precision boxes. |

If a free Gemini model is overloaded, the tool retries and falls back across
several Gemini models automatically.

---

## Setup

Requires Python 3.10+.

```bash
# 1. install dependencies
pip install -r requirements.txt

# 2. configure a model key
#    copy the template and fill in ONE key
cp .env.example .env          # Windows: copy .env.example .env
#    then edit .env:
#      GEMINI_API_KEY=...     (free — https://aistudio.google.com/apikey)
#    or ANTHROPIC_API_KEY=... (paid — https://console.anthropic.com)

# 3. run
python app.py
```

Open <http://127.0.0.1:5000> in a browser.

`.env` is git-ignored — keys never leave the machine and are never committed.

---

## Usage

1. Drop a **Figma design** image (Box 1) and a **build screenshot** (Box 2).
2. Optionally pick a **section** to scope the comparison (or keep "Whole
   screen"). The section list auto-populates from the design image.
3. Click **Compare**.
4. Review the PASS/FAIL verdict and the findings. Filter by severity, expand a
   card for detail, download the annotated screenshot, or generate the
   Markdown fix list.

A command-line version is also available:

```bash
python spec_ui_diff.py --figma-url "<figma link>" --screenshot build.png
```

---

## Project structure

```
app.py            Flask web app + UI
core.py           Diff logic, model backends, section detection
figma_client.py   Figma REST API extraction (optional mode)
spec_ui_diff.py   Command-line interface
requirements.txt  Dependencies
.env.example      Configuration template
```

---

## License

Copyright (c) 2026 Sofia Sekar. All rights reserved.

This project and its underlying idea are the author's own work. No permission
is granted to copy, modify, distribute, or use this software without the
author's explicit written consent. See [LICENSE](LICENSE).
