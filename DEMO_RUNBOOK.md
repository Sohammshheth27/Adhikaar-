# Adhikaar — Saturday Demo Runbook

The scanner now runs against the **real backend** (full crawler + fine-tuned 0.73 engine). Your
`Scanner.dc.html` calls the backend `/scan`; results render in your existing UI.

## Architecture (what's wired)
- **Backend** (`D:\Adhikaar\backend`): FastAPI `/scan` → crawl + 47-duty engine → returns the exact
  12-check / risk / coverage shape the UI renders. CORS open. Results **cached** for instant replay.
- **Frontend** (`E:\Markdown file implementation\Scanner.dc.html`): `_runUrlScan` now `fetch()`es
  `/scan`. API base = `window.ADHIKAAR_API` (defaults to `http://localhost:8000`).

## Run it (demo laptop — residential IP = not blocked)

**Terminal 1 — backend:**
```powershell
cd D:\Adhikaar\backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The backend now **serves the site too** (same origin), so there is no second server:
Open **http://localhost:8000/Scanner.dc.html** — type a URL, hit Scan, the real engine runs and the UI fills in.

## The night before — pre-cache your demo targets (do this!)
With the backend running:
```powershell
cd D:\Adhikaar\backend
python adhikaar_precache.py http://localhost:8000 https://siteA.com https://siteB.org
```
Cached sites return **instantly** on stage and cannot hang.

## Demo-day rules (learned the hard way)
1. **Use the demo laptop's own internet** (home/venue Wi-Fi = residential IP). Don't route through a
   datacenter/cloud — those get bot-blocked.
2. **Pick sites that crawl cleanly.** Great picks: a college/NGO site (DPDP-relevant, no bot-walls),
   or Infosys / Zoho / TCS / Razorpay. **Avoid Tata Neu and aggressive consumer SPAs live** — they
   block automation and will hang. If you must show one, pre-cache it the night before.
3. **Don't hammer a site repeatedly before the demo** — sites throttle an IP that scans them 10×.
   Scan each target once to cache it, then leave it alone.
4. **Fallback:** keep the pre-generated PDF reports open in a tab.

## Hosting it (optional, after the demo)
Point the frontend at a public backend by setting, before the app loads:
```html
<script>window.ADHIKAAR_API = "https://your-tunnel.trycloudflare.com";</script>
```
For same accuracy + your home IP: run the backend at home + `cloudflared tunnel --url http://localhost:8000`.

## If the scan shows all-GAP / grade E / "reached 0 pages"
That means the **crawl returned no pages** (site blocked this IP, or is a hostile SPA) — not an engine
fault. Switch to a cleanly-crawlable target, or use a fresh network. The engine only scores what it can
actually read (by design — it never invents findings).
