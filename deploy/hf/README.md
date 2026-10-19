---
title: Adhikaar DPDP Scanner
emoji: 🛡️
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: DPDP compliance scanner — engine + web UI
---

# Adhikaar — DPDP Compliance Scanner

This Space runs the full Adhikaar engine (crawler + fine-tuned model + FastAPI) **and** serves the web
scanner UI, in one Docker container on port 7860.

- Web UI: the Space's root URL (redirects to `Scanner.dc.html`)
- API: `POST /scan`, `POST /assess`, `GET /catalog`, `GET /health`

**Optional — top-accuracy LLM judge:** add these as **Space secrets** (Settings → Variables and secrets):
`ADHIKAAR_LLM_JUDGE=1`, `ADHIKAAR_LLM_PROVIDER=openai`,
`ADHIKAAR_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`,
`ADHIKAAR_LLM_API_KEY=<your key>`, `ADHIKAAR_LLM_MODEL=gemini-3.6-flash`.
Without them, the scanner uses the offline fine-tuned model (still accurate, fully free).

> Note: crawling runs from this Space's datacenter IP, so hard anti-bot sites may block it. Normal
> sites (colleges, NGOs, most companies) work fine.
