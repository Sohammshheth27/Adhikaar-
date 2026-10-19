"""
main.py -- FastAPI service exposing the Adhikaar DPDP engine.

    uvicorn app.main:app --reload
    POST /assess   {"url": "https://example.org", "org": "Example", "static": false}
    GET  /catalog  -> the 47-requirement framework
    GET  /health
"""
from __future__ import annotations
import re
from urllib.parse import urlparse as _urlparse_main
from fastapi import FastAPI, WebSocket
from pydantic import BaseModel

from app.compliance import crawler, exposure
from app.compliance.catalog import CHECKS
from app.compliance.engine import compliance_report
from app.compliance.report_render import render_compliance, render_recommendation
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Adhikaar — DPDP Compliance Engine", version="1.1")

# Allow the static site (any origin during the demo) to call the API from the browser.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def _no_cache_pages(request, call_next):
    """The frontend (.dc.html / i18n.js) changes during development; tell the browser never to cache
    them so an edit shows on a plain reload instead of needing a hard-refresh."""
    resp = await call_next(request)
    p = request.url.path.lower()
    if p.endswith(".dc.html") or p.endswith(".js") or p.endswith(".html") or p == "/":
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp

# Demo-safe result cache: a URL scanned once is served instantly on repeat (pre-scan your demo targets
# the night before -> on stage the result is deterministic and cannot fail). Does NOT touch the crawler.
_CACHE: dict[str, dict] = {}


class AssessRequest(BaseModel):
    url: str
    org: str | None = None
    budget: int = 60             # default page cap (fuller sitemap, still snappy); scan_minutes = deep mode
    static: bool = False
    exposure: bool = True
    force: bool = False          # re-scan even if cached (default: serve cache when present)
    scan_minutes: int | None = None   # wall-clock budget for a deep scan (e.g. 30); overrides the page cap
    fuzz: bool = False           # passive subdomain discovery (CT logs / subfinder) + seed live subdomains into the crawl


class AuthStartRequest(BaseModel):
    url: str                      # the site to scan after login
    login_url: str | None = None  # where to open the headed browser (defaults to url)
    authorized: bool = False      # operator attests they are authorized to test this site
    headed: bool = True
    # Optional assisted auto-login credentials (operator-supplied, in-memory only, never stored/logged).
    username: str | None = None
    password: str | None = None
    totp_secret: str | None = None


class AuthScanRequest(BaseModel):
    token: str                    # from /auth/start
    url: str                      # the authenticated area to scan
    org: str | None = None
    budget: int = 60
    proxy: str | None = None      # residential/mobile egress for a hosted deployment; None = local
    scan_minutes: int | None = None   # wall-clock budget for the deep authenticated crawl


@app.get("/health")
def health():
    return {"status": "ok", "checks": len(CHECKS)}


@app.get("/catalog")
def catalog():
    return {"n_checks": len(CHECKS), "checks": CHECKS}


def _live_subdomain_roots(subs: list[str], cap: int = 25, timeout: float = 4.0) -> list[str]:
    """Probe passively-discovered subdomains for liveness and return the live ones as crawl roots.
    A quick GET (follow redirects); keep hosts that answer < 400. Bounded by `cap` so the deep crawl
    spreads across real subdomains without unbounded scope."""
    import httpx
    roots: list[str] = []
    try:
        client = httpx.Client(timeout=timeout, follow_redirects=True,
                              headers={"User-Agent": crawler._UA_STRING})
    except Exception:
        return roots
    for h in subs:
        if len(roots) >= cap:
            break
        for scheme in ("https://", "http://"):
            try:
                r = client.get(scheme + h)
                if r.status_code < 400 and r.text:
                    roots.append(scheme + h.rstrip("/") + "/")
                    break
            except Exception:
                continue
    try:
        client.close()
    except Exception:
        pass
    return roots


def _smart_crawl(url: str, budget: int, static: bool, deadline: float | None = None, fuzz: bool = False):
    """Fast httpx spider for breadth, policy and the link graph; then (unless static is forced) a
    browser render of the site's pages to capture the real cookie jar and JS-loaded trackers -- the
    'before consent' behaviour httpx can't see. Best of both: fast + broad + real behaviour.

    Deep mode (deadline > 10 min) renders JS on far more pages; `fuzz` adds PASSIVE subdomain discovery
    (CT logs / subfinder) and seeds the live subdomains into the spider so the map spans the real site."""
    deep = bool(deadline and deadline > 600)

    # ---- Fuzzer: passive subdomain discovery, then seed the live ones as crawl roots ----
    seeds: list[str] = []
    discovered: list[str] = []
    if fuzz:
        try:
            from app.compliance.subdomains import discover as _discover
            origin = crawler._registrable(_urlparse_main(url if url.startswith("http") else "https://" + url).netloc)
            discovered = _discover(origin)                       # real names from CT logs / subfinder
            # Seed only PUBLIC-facing web properties into the crawl (where privacy/cookie duties live);
            # internal / infra / machine hosts are reported in the count but not probed or crawled.
            _skip = re.compile(r"(^|\.)(corp|internal|intranet|vpn|staging|dev|test|qa|uat)\.|"
                               r"-mtls|\.prod\.|mx\d|smtp|mail\.|ns\d|"
                               r"^[0-9a-f]{8}-[0-9a-f]{4}", re.I)
            _public = [s for s in discovered if not _skip.search(s)]
            seeds = _live_subdomain_roots(_public, cap=25)       # crawl the live public ones too
        except Exception:
            pass

    # Split the wall-clock budget: breadth spider gets the smaller share, JS rendering the larger.
    # Deep scans spill page bodies to disk (RAM-flat) since they crawl thousands of pages.
    _static_dl = (deadline * 0.45) if deep else deadline
    cr = crawler.crawl_static(url, budget, deadline=_static_dl, seeds=seeds, spill=deep)

    if discovered:                                               # report every real subdomain found
        cr["subdomains"] = sorted(set(cr.get("subdomains", [])) | set(discovered))

    if not static:
        try:
            _pg = [p.get("url") for p in cr.get("pages", []) if p.get("url")]
            # Deep scan renders JS on as many crawled pages as the time budget allows (not a fixed 25/40).
            _maxp = min(len(_pg), 250) if deep else 25
            _bdl = min(deadline * 0.5, 1500) if deep else (min(deadline or 180, 600) if deadline else 180)
            beh = crawler.site_behaviour(url, page_urls=_pg, max_pages=_maxp, deadline=_bdl)
            if beh.get("cookies"):
                cr["cookies"] = beh["cookies"]
            if beh.get("trackers"):
                cr["trackers"] = beh["trackers"]
            if beh.get("sec_headers") and not cr.get("sec_headers"):
                cr["sec_headers"] = beh["sec_headers"]
        except Exception:
            pass
        # Reject-verification: a short homepage probe that clicks the banner's reject/necessary-only
        # control and checks which non-essential cookies survive, so a consent finding is measured.
        try:
            cr["consent_probe"] = crawler.consent_reject_probe(url)
        except Exception:
            cr["consent_probe"] = None
    return cr


_CRAWL_CACHE: dict[str, dict] = {}


_CRAWL_CACHE_MAX = 8                 # keep only the most recent crawls; evict (and free disk) beyond this


def _cached_crawl(url: str, budget: int, static: bool, force: bool = False,
                  deadline: float | None = None, fuzz: bool = False):
    """Cache the crawl per URL so /scan and /report.pdf don't crawl the same site twice."""
    key = url.rstrip("/").lower()
    if not force and key in _CRAWL_CACHE:
        _CRAWL_CACHE[key] = _CRAWL_CACHE.pop(key)        # mark most-recently used
        return _CRAWL_CACHE[key]
    cr = _smart_crawl(url, budget, static, deadline=deadline, fuzz=fuzz)
    _CRAWL_CACHE.pop(key, None)
    _CRAWL_CACHE[key] = cr
    while len(_CRAWL_CACHE) > _CRAWL_CACHE_MAX:           # evict oldest; close its disk page-store
        _old_k, _old = next(iter(_CRAWL_CACHE.items()))
        _CRAWL_CACHE.pop(_old_k, None)
        try:
            st = _old.get("_pagestore")
            if st is not None:
                st.close()
        except Exception:
            pass
    return cr


_REPORT_CACHE: dict[str, tuple] = {}


def _build_report(req: "AssessRequest"):
    """Crawl (cached) + full engine -> a ComplianceReport, shared by /assess, /scan and /report.pdf.
    The finished report is cached per URL so /report.pdf reuses /scan's work instead of re-running
    the (crawl + engine) a second time -- the PDF is then near-instant after a scan."""
    _rkey = req.url.rstrip("/").lower()
    if not req.force and _rkey in _REPORT_CACHE:
        return _REPORT_CACHE[_rkey]
    # A deep scan is bounded by its wall-clock budget (scan_minutes); the page cap then scales with
    # the time (so TIME is the real limit, not a fixed page count) up to a memory-safety ceiling.
    _deadline = (req.scan_minutes * 60) if req.scan_minutes else None
    _budget = req.budget
    if req.scan_minutes:
        _budget = max(_budget, min(req.scan_minutes * 100, 3000))   # ~100 pages/min, cap 3000
    crawl = _cached_crawl(req.url, _budget, req.static, req.force, deadline=_deadline, fuzz=req.fuzz)
    exp, tech = [], {}
    if req.exposure:
        exp = exposure.probe(req.url, pages=crawl.get("pages"), subdomains=crawl.get("subdomains"))
        tech = exposure.tech_signals(req.url, pages=crawl.get("pages"), subdomains=crawl.get("subdomains"))
    site = re.sub(r"^https?://(www\.)?", "", req.url).split("/")[0]
    rep = compliance_report(url=req.url, pages=crawl["pages"], exposure_findings=exp,
                            is_https=(True if req.url.startswith("https://") else
                                      False if req.url.startswith("http://") else None),
                            site=site, page_budget=req.budget,
                            platform=crawl.get("platform", "Unknown"),
                            archived_policy=crawl.get("archived_policy"),
                            policy_found=crawl.get("policy_found"),
                            subdomains=crawl.get("subdomains"),
                            sec_headers=crawl.get("sec_headers"),
                            observed_tech=tech)
    # merge Nuclei-detected trackers into the inventory (feeds duty 24/34 evidence)
    trk = list(crawl.get("trackers", []))
    known = {t.get("name") for t in trk if isinstance(t, dict)}
    for t in (tech.get("trackers") or []):
        if t not in known:
            trk.append({"name": t, "domain": "", "country": "", "source": "nuclei"})
    rep.tracker_inventory = trk
    rep.cookie_inventory = crawl.get("cookies", [])
    _REPORT_CACHE[_rkey] = (rep, crawl)
    return rep, crawl


@app.post("/assess")
def assess(req: AssessRequest):
    key = req.url.rstrip("/").lower()
    if not req.force and key in _CACHE:                  # instant, deterministic replay for the demo
        return {**_CACHE[key], "cached": True}
    rep, crawl = _build_report(req)
    result = {
        "grade": rep.overall.grade, "adequacy": rep.overall.adequacy,
        "counts": rep.overall.counts,
        "pages_crawled": len(crawl.get("pages", [])),
        "findings": [f.model_dump() for f in rep.findings],
        "exposure": rep.exposure, "trackers": rep.tracker_inventory,
        "compliance_markdown": render_compliance(rep, org=req.org),
        "recommendation_markdown": render_recommendation(rep, org=req.org),
        "cached": False,
    }
    _CACHE[key] = result
    return result


_UI_CACHE: dict[str, dict] = {}


@app.post("/scan")
def scan(req: AssessRequest):
    """Return the result in the exact shape the Scanner web UI renders (12 grouped checks + risk +
    coverage). Same engine and crawler as /assess; demo-cached for instant, deterministic replay."""
    from app.compliance.ui_map import ui_report
    key = req.url.rstrip("/").lower()
    if not req.force and key in _UI_CACHE:
        return {**_UI_CACHE[key], "cached": True}
    rep, crawl = _build_report(req)
    out = ui_report(rep, crawl, org=req.org)
    out["cached"] = False
    _UI_CACHE[key] = out
    return out


# ---- Asynchronous scan: start a background job + poll for the result, so a long (deep) scan is never
# blocked by a proxy's request timeout (Cloudflare drops any request held longer than ~100s). Each HTTP
# call below returns in well under a second; the scan runs in a daemon thread and the UI polls for it.
import uuid as _uuid
import threading as _threading
import time as _time
_JOBS: dict[str, dict] = {}


def _run_scan_job(job_id: str, req: "AssessRequest"):
    try:
        from app.compliance.ui_map import ui_report
        key = req.url.rstrip("/").lower()
        if not req.force and key in _UI_CACHE:
            _JOBS[job_id].update(status="done", result={**_UI_CACHE[key], "cached": True})
            return
        rep, crawl = _build_report(req)
        out = ui_report(rep, crawl, org=req.org)
        out["cached"] = False
        _UI_CACHE[key] = out
        _JOBS[job_id].update(status="done", result=out)
    except Exception as e:  # noqa: BLE001
        _JOBS[job_id].update(status="error", error=str(e)[:300])


@app.post("/scan/start")
def scan_start(req: AssessRequest):
    """Start a scan in the background; return a job id immediately (no long-held connection)."""
    key = req.url.rstrip("/").lower()
    if not req.force and key in _UI_CACHE:                 # instant path for a pre-cached target
        jid = _uuid.uuid4().hex
        _JOBS[jid] = {"status": "done", "result": {**_UI_CACHE[key], "cached": True}, "started": _time.time()}
        return {"job_id": jid, "cached": True}
    jid = _uuid.uuid4().hex
    _JOBS[jid] = {"status": "running", "result": None, "error": None, "started": _time.time()}
    _threading.Thread(target=_run_scan_job, args=(jid, req), daemon=True).start()
    _cut = _time.time() - 3600                             # drop jobs older than an hour
    for k in [k for k, v in list(_JOBS.items()) if v.get("started", 0) < _cut]:
        _JOBS.pop(k, None)
    return {"job_id": jid, "cached": False}


@app.get("/scan/status/{job_id}")
def scan_status(job_id: str):
    """Poll a scan job. Returns {status: running|done|error|unknown}; the result is included when done."""
    j = _JOBS.get(job_id)
    if not j:
        return {"status": "unknown"}
    out = {"status": j["status"], "elapsed": int(_time.time() - j.get("started", _time.time()))}
    if j["status"] == "done":
        out["result"] = j["result"]
    elif j["status"] == "error":
        out["error"] = j["error"]
    return out


@app.post("/auth/start")
def auth_start(req: AuthStartRequest):
    """Open a headed browser at the login page so the operator can sign in (they clear any CAPTCHA /
    OTP / 2FA themselves). Returns a session token. Requires an explicit authorization attestation:
    authenticated scanning is only for a site the operator is authorized to test (their own site, a
    sanctioned audit, or the owner's consent). The attestation is recorded with the request."""
    if not req.authorized:
        return {"error": "authorization_required",
                "detail": ("Authenticated scanning requires you to confirm you are authorized to "
                           "test this site. Set authorized=true to attest and proceed.")}
    from app.compliance import session as _sess
    import datetime as _dt
    login_url = req.login_url or req.url
    print(f"[auth] AUTHORIZED authenticated-login started for {req.url} "
          f"(login at {login_url}) at {_dt.datetime.now().isoformat()}")  # audit trail, no credentials
    try:
        return _sess.start_login(login_url, headed=req.headed)
    except Exception as e:
        return {"error": "login_start_failed", "detail": str(e)}


@app.post("/auth/scan")
def auth_scan(req: AuthScanRequest):
    """Capture the operator's authenticated session and run a READ-ONLY scan of the logged-in area.
    Returns the same UI payload as /scan, with authenticated=true. The session is discarded after."""
    from app.compliance import session as _sess, auth as _auth
    from app.compliance.ui_map import ui_report
    try:
        storage_state = _sess.capture(req.token)
    except Exception as e:
        return {"error": "capture_failed", "detail": str(e)}
    try:
        _dl = (req.scan_minutes * 60) if req.scan_minutes else None
        _bud = max(req.budget, min(req.scan_minutes * 100, 3000)) if req.scan_minutes else req.budget
        crawl = _auth.crawl_authenticated(req.url, storage_state, budget=_bud, deadline=_dl, proxy=req.proxy)
    except Exception as e:
        return {"error": "authenticated_crawl_failed", "detail": str(e)}
    exp, tech = [], {}
    try:
        exp = exposure.probe(req.url, pages=crawl.get("pages"), subdomains=crawl.get("subdomains"))
        tech = exposure.tech_signals(req.url, pages=crawl.get("pages"), subdomains=crawl.get("subdomains"))
    except Exception:
        exp, tech = [], {}
    site = re.sub(r"^https?://(www\.)?", "", req.url).split("/")[0]
    rep = compliance_report(url=req.url, pages=crawl["pages"], exposure_findings=exp,
                            is_https=(True if req.url.startswith("https://") else
                                      False if req.url.startswith("http://") else None),
                            site=site, page_budget=req.budget,
                            platform=crawl.get("platform", "Unknown"),
                            policy_found=crawl.get("policy_found"),
                            subdomains=crawl.get("subdomains"),
                            sec_headers=crawl.get("sec_headers"), observed_tech=tech)
    rep.tracker_inventory = crawl.get("trackers", [])
    rep.cookie_inventory = crawl.get("cookies", [])
    _REPORT_CACHE[req.url.rstrip("/").lower()] = (rep, crawl)   # so /report.pdf renders this scan
    out = ui_report(rep, crawl, org=req.org)
    out["authenticated"] = True
    out["pages_scanned"] = len(crawl.get("pages", []))
    return out


@app.post("/auth/cancel")
def auth_cancel(req: AuthScanRequest):
    """Abort a pending login flow (operator closed it) and tear the headed browser down."""
    from app.compliance import session as _sess
    return {"cancelled": _sess.cancel(req.token)}


# ---- Hosted authenticated login via a CDP-screencast remote browser -------------------------------
@app.post("/auth/stream_start")
def auth_stream_start(req: AuthStartRequest):
    """Register a streamed remote-browser login (hosted path). The operator then connects the
    WebSocket /auth/stream/{token}, which opens the browser and streams it to their page. Requires
    the same authorization attestation as the local flow."""
    if not req.authorized:
        return {"error": "authorization_required",
                "detail": "Set authorized=true to attest you are authorized to test this site."}
    from app.compliance import stream as _stream
    import datetime as _dt
    login_url = req.login_url or req.url
    assisted = bool(req.username or req.password)
    print(f"[auth] AUTHORIZED streamed login started for {req.url} (login at {login_url}; "
          f"assisted={assisted}) at {_dt.datetime.now().isoformat()}")   # audit trail, NO credentials
    creds = {"username": req.username, "password": req.password, "totp_secret": req.totp_secret}
    return {"token": _stream.start(login_url, creds=creds), "login_url": login_url}


@app.websocket("/auth/stream/{token}")
async def auth_stream_ws(ws: WebSocket, token: str):
    """Stream the remote login browser to the operator and forward their input (see stream.py)."""
    from app.compliance import stream as _stream
    await ws.accept()
    try:
        await _stream.run_stream(ws, token)
    except Exception:
        pass
    try:
        await ws.close()
    except Exception:
        pass


@app.post("/auth/stream_scan")
def auth_stream_scan(req: AuthScanRequest):
    """After the operator captured a streamed session, run the read-only authenticated scan."""
    from app.compliance import stream as _stream, auth as _auth
    from app.compliance.ui_map import ui_report
    storage_state = _stream.pop_captured(req.token)
    if storage_state is None:
        return {"error": "no_session", "detail": "No captured session for this token. Finish the "
                "login and click Capture before scanning."}
    try:
        _dl = (req.scan_minutes * 60) if req.scan_minutes else None
        _bud = max(req.budget, min(req.scan_minutes * 100, 3000)) if req.scan_minutes else req.budget
        crawl = _auth.crawl_authenticated(req.url, storage_state, budget=_bud, deadline=_dl, proxy=req.proxy)
    except Exception as e:
        return {"error": "authenticated_crawl_failed", "detail": str(e)}
    exp, tech = [], {}
    try:
        exp = exposure.probe(req.url, pages=crawl.get("pages"), subdomains=crawl.get("subdomains"))
        tech = exposure.tech_signals(req.url, pages=crawl.get("pages"), subdomains=crawl.get("subdomains"))
    except Exception:
        exp, tech = [], {}
    site = re.sub(r"^https?://(www\.)?", "", req.url).split("/")[0]
    rep = compliance_report(url=req.url, pages=crawl["pages"], exposure_findings=exp,
                            is_https=(True if req.url.startswith("https://") else
                                      False if req.url.startswith("http://") else None),
                            site=site, page_budget=req.budget,
                            platform=crawl.get("platform", "Unknown"),
                            policy_found=crawl.get("policy_found"),
                            subdomains=crawl.get("subdomains"),
                            sec_headers=crawl.get("sec_headers"), observed_tech=tech)
    rep.tracker_inventory = crawl.get("trackers", [])
    rep.cookie_inventory = crawl.get("cookies", [])
    _REPORT_CACHE[req.url.rstrip("/").lower()] = (rep, crawl)   # so /report.pdf renders this scan
    out = ui_report(rep, crawl, org=req.org)
    out["authenticated"] = True
    out["pages_scanned"] = len(crawl.get("pages", []))
    return out


def _render_pdf(req: "AssessRequest", builder, suffix: str):
    from fastapi.responses import FileResponse
    import tempfile
    rep, _ = _build_report(req)
    site = re.sub(r"^https?://(www\.)?", "", req.url).split("/")[0]
    name = (req.org or site).replace(" ", "-") + suffix
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    builder(rep, org=req.org, out_path=tmp.name)
    return FileResponse(tmp.name, media_type="application/pdf", filename=name)


@app.post("/report.pdf")
def report_pdf(req: AssessRequest):
    """Report 1 of 3 -- the detailed Compliance PDF (full 47-duty assessment)."""
    from app.compliance.pdf_render import build_compliance_pdf
    return _render_pdf(req, build_compliance_pdf, "-Compliance.pdf")


@app.post("/report/exposure.pdf")
def report_exposure_pdf(req: AssessRequest):
    """Report 2 of 3 -- Exposure, PII and Data-Leak report (for the CISO / security team)."""
    from app.compliance.pdf_render import build_exposure_pdf
    return _render_pdf(req, build_exposure_pdf, "-Exposure-PII-Leaks.pdf")


@app.post("/report/executive.pdf")
def report_executive_pdf(req: AssessRequest):
    """Report 3 of 3 -- short Executive Summary & Recommendations with the purpose of each duty
    (for the DPO / CISO)."""
    from app.compliance.pdf_render import build_executive_pdf
    return _render_pdf(req, build_executive_pdf, "-Executive-Summary.pdf")


# --- Serve the static site from the same origin (one container hosts site + engine) ---
import os as _os
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

_FRONTEND = _os.path.join(_os.path.dirname(__file__), "..", "..", "frontend")


@app.get("/")
def _root():
    return RedirectResponse(url="/Scanner.dc.html")


if _os.path.isdir(_FRONTEND):
    # Mounted last so the API routes (/assess, /scan, /catalog, /health) take precedence.
    app.mount("/", StaticFiles(directory=_FRONTEND, html=True), name="site")
