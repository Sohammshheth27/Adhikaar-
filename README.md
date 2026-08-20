# Adhikaar — DPDP Compliance Assessment Engine

Automated assessment of a website against India's **Digital Personal Data Protection Act 2023** and the
**DPDP Rules 2025 (G.S.R. 846(E))** — 47 requirements across 14 categories, producing grounded,
citation-guarded compliance and recommendation reports (Markdown + PDF + JSON).

> Built by **Sohamm Manish Shheth** (sohamm.shheth24@sakec.ac.in) & **Dr. Nilakshi Jain**
> (nilakshi.jain@sakec.ac.in). For a full technical reference see [`ADHIKAAR.md`](ADHIKAAR.md).

## Highlights

- **Multi-source evidence, not just the policy page.** Every duty is judged against the whole site —
  the privacy policy, the footer, `/contact`, cookie banners, FAQ pages — plus **observable technical
  controls** (HTTPS, HSTS/CSP security headers). Grades real behaviour, not prose alone.
- **Three-tier judging**, all citation-guarded: an optional **LLM judge** → a **fine-tuned semantic
  model** (offline, ships in the repo, GOLD-set F1 0.73) → keyword signals.
- **Trained on real policies, never synthetic.** A distillation pipeline crawls actual published
  privacy notices, an LLM labels them with verbatim evidence, and a local bi-encoder is fine-tuned on
  those labels.
- **Hardened crawler** for JS/SPA sites: consent-banner dismissal, scroll, wait-until-stable,
  404-recovery, in-app click navigation — within a strict boundary (renders only what an ordinary
  visitor sees; no auth bypass or evasion).
- **Citation integrity is non-negotiable:** any evidence quote that is not verbatim in the source is
  blanked; unquoted "Compliant" is downgraded. No fabricated citations, numbers, or quotes.

## Quick start

```bash
cd backend
pip install -r requirements.txt
python -m playwright install chromium

# CLI: assess a site (offline judging, no API key needed)
python adhikaar_scan.py https://example.com --org "Example" --out reports/example

# API: serve the engine
uvicorn app.main:app --host 0.0.0.0 --port 8000
#   POST /assess {"url": "..."}       -> full report + markdown
#   POST /scan   {"url": "..."}       -> UI-shaped result (12 checks + risk + coverage)
#   GET  /catalog                     -> the 47-requirement framework
```

For maximum accuracy, enable the LLM judge (any OpenAI-compatible endpoint — OpenAI, Gemini, Groq, or a
local model) via env vars: `ADHIKAAR_LLM_JUDGE=1`, `ADHIKAAR_LLM_API_KEY`, `ADHIKAAR_LLM_BASE_URL`,
`ADHIKAAR_LLM_MODEL`. Keys are read from the environment only — never commit them.

## Layout

```
backend/
  adhikaar_scan.py                CLI (crawl → probe → score → render)
  app/compliance/       catalog, crawler, engine, exposure, records, subdomains, renderers
  app/rag/              semantic.py (fine-tuned model), llm_judge.py, retriever.py
  app/rag/models/adhikaar-minilm/   the deployed fine-tuned model (F1 0.73)
  adhikaar_build_corpus.py / adhikaar_finetune.py / adhikaar_calibrate.py   the real-policy fine-tuning pipeline
```

## Responsible use

Adhikaar assesses **publicly published** pages for **compliance** purposes and behaves like an ordinary
visitor. Use it only on sites you are authorized to assess. It never bypasses authentication, evades
security controls, or stores personal data it observes (exposure detection is signal/count-only).

## Licence

© 2026 Sohamm Manish Shheth & Dr. Nilakshi Jain. All rights reserved. (Add an explicit licence file if
you intend to open-source.)
