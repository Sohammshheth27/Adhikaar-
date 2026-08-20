# Adhikaar — DPDP Compliance Assessment Engine

**A complete technical reference.**
Automated assessment of a website against India's **Digital Personal Data Protection Act 2023** and the **DPDP Rules 2025 (G.S.R. 846(E))**, producing grounded, citation-guarded compliance and recommendation reports.

- **Codebase:** `D:\Adhikaar\backend`
- **Authorship:** Developed by Sohamm Manish Shheth (sohamm.shheth24@sakec.ac.in) & Dr. Nilakshi Jain (nilakshi.jain@sakec.ac.in)
- **Last updated:** 2026-08-20

---

## 1. What Adhikaar does

Given a website URL, Adhikaar:
1. **Crawls** the site (JS-rendered), locating the privacy policy, cookie policy, terms, grievance/legal pages, and the pages that collect personal data.
2. **Probes** (signal-only) for exposed files and published-records/PII exposure — never storing the data itself.
3. **Judges** the disclosures against **47 DPDP requirements** across **14 categories**, using a best-available judging cascade.
4. **Scores** an adequacy value and a letter **Grade (A–E)**, with per-requirement verdicts, DPDP anchors, penalty exposure, and remediation.
5. **Renders** four artefacts: a detailed **Compliance report** and a **Recommendation report**, each as **Markdown + PDF**, plus a machine-readable **JSON**.

**Design principle (non-negotiable): citation integrity.** No fabricated citations, numbers, or quotes. Every evidence quote must be verbatim from the source; any quote that is not a literal substring is blanked, and an unquoted "Compliant" is downgraded.

---

## 2. The 47-requirement framework

| Property | Value |
|---|---|
| Total checks | **47** |
| Categories | **14** |
| Mandatory duties | **18** |
| Disclosure-only (internal controls, judged as disclosure) | **15** |
| Framework | DPDP Act 2023 + DPDP Rules 2025 |

**Penalty bands** (per the Act's schedule), with the count of checks mapped to each:

| Band | Cap | Checks |
|---|---|---|
| `security` | ₹250 cr | 7 |
| `breach_notify` | ₹200 cr | 2 |
| `children` | ₹200 cr | 1 |
| `sdf` (Significant Data Fiduciary) | ₹150 cr | 5 |
| `other_provision` | ₹50 cr | 29 |
| `good_practice` | none | 3 |

**Verdict vocabulary:** `Compliant` · `Partial` · `Gap` · `Not disclosed` · `Not externally verifiable` (NEV, for internal controls that can't be observed from outside).

**Adequacy & grade:** weighted sum ÷ 47 (Compliant = 1.0, NEV = 0.75, Partial = 0.5).
Grade bands: **A ≥ 0.85 · B ≥ 0.70 · C ≥ 0.55 · D ≥ 0.40 · E < 0.40**.

Each requirement in `catalog.json` carries: `id`, `category`, `requirement`, `finding` (negative phrasing), `dpdp_anchor` (act section + rule), `priority`, `penalty_band`, `mandatory`, `disclosure_only`, `signals` (keyword fallback), `remediation`, `impact`.

---

## 3. Architecture

```
backend/
├── adhikaar_scan.py                 CLI: crawl → probe → score → render (md+pdf+json)
├── adhikaar_build_corpus.py        Build a fine-tuning corpus from REAL policies (LLM-labelled)
├── adhikaar_finetune.py            Fine-tune the local semantic model on the real-policy corpus
├── adhikaar_calibrate.py           Sweep thresholds on the GOLD set; report precision/recall/F1
├── adhikaar_iterate.py             Convergence harness (crawl-cache + diff vs a reference report)
├── adhikaar_batch.py               Portfolio mode (assess many sites)
├── adhikaar_diff.py                Re-assessment diff (what changed since last scan)
├── requirements.txt
└── app/
    ├── main.py            FastAPI entrypoint
    ├── compliance/
    │   ├── catalog.json / catalog.py / build_catalog.py   47-check framework + loader
    │   ├── crawler.py     Playwright crawler (JS render, consent, scroll, 404-recovery)
    │   ├── engine.py      Core: builds policy text, runs the judging cascade, scores
    │   ├── models.py      Pydantic v2 models (Finding, Evidence, Overall, Report)
    │   ├── exposure.py    Signal-only file-exposure probe (soft-404 guarded)
    │   ├── records.py     Published-records / PII exposure detector (counts only)
    │   ├── subdomains.py  Passive subdomain discovery (subfinder / crt.sh — no wordlist)
    │   ├── report_render.py   Markdown renderer
    │   └── pdf_render.py      reportlab PDF renderer (Calibri, watermark, Page X of Y)
    └── rag/
        ├── semantic.py    Fine-tuned bi-encoder disclosure judge (offline)
        ├── llm_judge.py   LLM disclosure judge (provider-agnostic) + corpus labeller
        ├── retriever.py   Guardrailed DPDP provision lookup (verbatim, by anchor)
        ├── dpdp_corpus.json   DPDP provision text
        └── models/
            ├── adhikaar-minilm/       ← DEPLOYED fine-tuned model (F1 0.73)
            └── adhikaar-minilm_073/   ← backup of the winner
```

---

## 4. The judging cascade (best available wins)

For each of the 47 duties, Adhikaar decides the verdict using the strongest judge available, all under the same citation guard:

1. **LLM judge** (`llm_judge.py`) — reads the real policy text, returns a verdict + the **verbatim** evidence sentence per duty. Used when `ADHIKAAR_LLM_JUDGE=1` and a key/endpoint is set. Highest accuracy.
2. **Fine-tuned semantic model** (`semantic.py`) — an offline bi-encoder scoring each policy sentence against a per-duty exemplar of "what a compliant disclosure says." Catches paraphrases a keyword list misses. **This is the deployed default — fully offline, free.**
3. **Keyword signals** — the original deterministic fallback in `engine.py`.

**Thresholds** (semantic): `T_HIGH = 0.55` → Compliant, `T_PARTIAL = 0.47` → Partial. GOLD-calibrated.

**Citation guard (all tiers):** evidence must be a verbatim (case-insensitive) substring of the policy or it is blanked; a Compliant verdict with no valid quote is downgraded to Partial. Hallucinated quotes can never reach a report.

---

## 5. Online vs. offline — how a scan actually runs

| Stage | Online / Offline | Why |
|---|---|---|
| **Crawl** the target | **Online (always)** | Must reach the live site to read its policy |
| **Judge / score** | **Offline** | The fine-tuned model runs locally — no API, free |
| **LLM judge** (optional top tier) | **Online (only if enabled)** | Calls the configured LLM |

With the LLM judge **off**, a scan makes network calls **only to the site being assessed**; the scoring brain is 100% local.

---

## 6. The crawler (hardened for JS / top-org sites)

`crawler.py` renders publicly-served pages the way an ordinary visitor's browser would — **no auth bypass, no WAF/rate-limit evasion, no fingerprint spoofing beyond a normal browser config.** (VAPT boundary: "we read only what any user can read.")

| Capability | Purpose |
|---|---|
| `_dismiss_consent` | Clicks the site's own cookie-consent "Accept" (OneTrust/Cookiebot/Quantcast/TrustArc + generic) to reveal gated content |
| `_auto_scroll` | Triggers lazy-loaded sections |
| `_wait_stable_text` | Waits until body text stops growing (SPA render settled) — not a blind timer |
| `_extract_text` | Returns full body text (superset that always contains the policy); main-content extractor only as a thin-page fallback |
| thin-retry | Reloads once with longer waits if a page is < 600 chars |
| anchor-text discovery | Finds "Privacy"/"Grievance"/"Nodal" links even with opaque URLs |
| **404-recovery** | If the entry URL is dead, falls back to the site root and discovers the policy |
| HTTP/1.1 | `--disable-http2` works around servers that reject Chromium's HTTP/2 |

**Validated:** ICICI recovered a real policy page; cyberpeace correctly determined to publish **no** policy (all `/privacy*` paths 404 — a genuine Gap finding, not a crawl bug).

**Known limitation:** single-page-app policies behind **client-side routes** (e.g. Tata Neu's `/login/privacypolicy`) can't be loaded by direct navigation and may render incompletely, causing false "Not disclosed" on duties that are actually disclosed deeper in the app. Durable fix = policy-page-specific render-wait (planned).

---

## 7. Exposure & PII detection (signal-only, safe by design)

- **`exposure.py`** — probes for exposed files with a **soft-404 catch-all guard** (a site that returns 200 for everything is detected and suppressed; "3+ control hits = catch-all"), eliminating false positives on SPAs.
- **`records.py`** — detects published personal data (emails/phones/gov-IDs) by **count only, never storing the data**. Role mailboxes excluded; gov-IDs keyword-gated and require ≥2 to fire. Emits Critical findings with counts alone.
- **`subdomains.py`** — passive discovery via **subfinder** (if on PATH) or **Certificate Transparency (crt.sh)** — no brute-force wordlist.

---

## 8. Reports produced

Per scan, in the output directory:

- `<Org>-Compliance.md` / `.pdf` — the detailed 40+-section assessment (scope, grade, per-requirement findings with DPDP anchors, evidence, penalty exposure, remediation, data-exposure observations, tracker/cookie inventory, appendices, draft privacy notice).
- `<Org>-Recommendation.md` / `.pdf` — the executive recommendation report.
- `<Org>-report.json` — full machine-readable result.

**PDF template:** Calibri, monochrome, Adhikaar wordmark, faint behind-content watermark, "Page X of Y" footer, authorship line.

---

## 9. The fine-tuning pipeline (train on REAL policies, never synthetic)

The offline semantic model was fine-tuned on **actual published privacy policies**, with an LLM as the expert labeller:

1. **`adhikaar_build_corpus.py`** — crawls a list of real strong policies; an LLM labels each of the 47 duties with the **verbatim** evidence sentence; emits `(sentence, duty, label)` training pairs (positive = evidence; negatives = that sentence vs other duties, and other sentences vs the duty).
2. **`adhikaar_finetune.py`** — self-contained PyTorch loop (cosine + MSE), fine-tunes `all-MiniLM-L6-v2` so real disclosure sentences sit close to their duty exemplar. Saves to `app/rag/models/adhikaar-minilm/` (auto-loaded by `semantic.py`).
3. **`adhikaar_calibrate.py`** — sweeps thresholds on an independent hand-written GOLD set; reports precision/recall/F1.

**Provider-agnostic labeller** (`llm_judge.py`): Anthropic, OpenAI, **Gemini**, **Groq**, or a **local** model (Ollama/llama.cpp) via `ADHIKAAR_LLM_BASE_URL`. Rate-limit-aware retry (honors `Retry-After` / "retry in Xs"); reasoning-model token handling (`ADHIKAAR_LLM_MAXTOK`, `ADHIKAAR_LLM_REASONING`).

### Results (GOLD-set F1 — data never seen in training)

| Model | Corpus | GOLD F1 |
|---|---|---|
| Semantic baseline (pre-tune) | — | 0.58 |
| Fine-tuned, 14 sites, old crawler (Gemini) | 2,272 pairs | 0.69 |
| **Fine-tuned, 8 strong sites, hardened crawler (Gemini)** | **1,281 pairs** | **0.73 ← deployed** |
| Fine-tuned, 15 sites (+7 conservative Groq labels) | 1,449 pairs | 0.69 (rejected) |

**Lesson, proven twice: label quality beats corpus size.** Better crawling (0.69→0.73) and rejecting weaker labels (kept 0.73 over 0.69) both won on quality, not quantity. Every candidate was A/B-tested on GOLD with model backups, so the deployed model never regressed. The grievance false-negative is fixed on text that contains the disclosure (duty 19 scores 0.83 Compliant on "nodal officer" phrasing).

---

## 10. Running it

**Generate a report (offline judging, no key needed):**
```powershell
cd D:\Adhikaar\backend
python adhikaar_scan.py https://example.com --org "Example" --out reports\example --budget 12
```

**Maximum accuracy (add the LLM judge on top):**
```powershell
$env:ADHIKAAR_LLM_JUDGE="1"; $env:ADHIKAAR_LLM_PROVIDER="openai"
$env:ADHIKAAR_LLM_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai"
$env:ADHIKAAR_LLM_API_KEY="<key>"; $env:ADHIKAAR_LLM_MODEL="gemini-3.6-flash"
python adhikaar_scan.py https://example.com --org "Example" --out reports\example
```

**Improve the model further** (crawl real policies → label → fine-tune → calibrate):
```powershell
python adhikaar_build_corpus.py adhikaar_policies.txt --out adhikaar_corpus.jsonl   # run SOLO (free tiers rate-limit)
python adhikaar_finetune.py adhikaar_corpus.jsonl
python adhikaar_calibrate.py
```

**`adhikaar_scan.py` flags:** `--org`, `--out`, `--budget` (default 12), `--static` (httpx fallback), `--fuzz`, `--no-exposure`.

---

## 11. Operational notes

- **Gemini free tier:** ~20 req/min, quota is **per Google account** (a new project on the same account shares it). Run `adhikaar_build_corpus.py` **solo** — concurrent calls starve its retries.
- **Groq free tier:** fast, but tight tokens-per-minute; `gpt-oss` are *reasoning* models — set `ADHIKAAR_LLM_MAXTOK=8000` and `ADHIKAAR_LLM_REASONING=low` or they emit zero answer tokens.
- **Offline training:** set `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` to skip HuggingFace network stalls (the base model is cached).
- **Dependencies:** `pydantic`, `httpx`, `playwright`, `fastapi`, `uvicorn`, `reportlab`, `sentence-transformers`, `torch` (all installed). `subfinder` optional.

---

## 12. Current state (2026-08-20)

- ✅ Deployed model: **F1 0.73**, offline, optimally tuned (T_HIGH 0.55 / T_PARTIAL 0.47)
- ✅ 3-tier citation-guarded judge; provider-agnostic labeller
- ✅ Hardened crawler (consent/scroll/stable-wait/404-recovery/anchor-discovery) within a strict VAPT boundary
- ✅ Signal-only exposure + PII detection; passive subdomain discovery
- ✅ Full PDF/MD/JSON report suite
- ⚠️ Open item: client-side-routed SPA policies (e.g. Tata Neu) can render incompletely → policy-page render-wait is the next crawler improvement
