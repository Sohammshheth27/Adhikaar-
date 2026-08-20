# Adhikaar — Web Scanner (frontend)

The public site + live scanner UI. `Scanner.dc.html` is wired to the backend `/scan` endpoint (in
`../backend`), so the real engine (crawler + fine-tuned 0.73 model) runs the assessment and the results
render here.

## Run locally
```powershell
# 1. Start the backend (from ../backend)
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. Serve this folder (so pages load over http://, not file://)
python -m http.server 5500
```
Open **http://localhost:5500/Scanner.dc.html**, type a URL, hit **Scan**.

## Point at a different backend
The API base defaults to `http://localhost:8000`. To use a hosted backend (e.g. a Cloudflare tunnel),
set it before the app loads:
```html
<script>window.ADHIKAAR_API = "https://your-backend.example";</script>
```

## Files
- `Scanner.dc.html` — the live scanner (calls `/scan`)
- `Adhikar Landing.dc.html`, `Managing Permissions.dc.html`, `The DPDP Act.dc.html` — site pages
- `support.js`, `i18n.js`, `image-slot.js` — the DC runtime + multilingual layer
