"""
main.py -- FastAPI service exposing the Adhikaar DPDP engine.

    uvicorn app.main:app --reload
    POST /assess   {"url": "https://example.org", "org": "Example", "static": false}
    GET  /catalog  -> the 47-requirement framework
    GET  /health
"""
from __future__ import annotations
import re
from fastapi import FastAPI
from pydantic import BaseModel

from app.compliance import crawler, exposure
from app.compliance.catalog import CHECKS
from app.compliance.engine import compliance_report
from app.compliance.report_render import render_compliance, render_recommendation
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Adhikaar — DPDP Compliance Engine", version="1.1")

# Allow the static site (any origin during the demo) to call the API from the browser.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Demo-safe result cache: a URL scanned once is served instantly on repeat (pre-scan your demo targets
# the night before -> on stage the result is deterministic and cannot fail). Does NOT touch the crawler.
_CACHE: dict[str, dict] = {}


class AssessRequest(BaseModel):
    url: str
    org: str | None = None
    budget: int = 12
    static: bool = False
    exposure: bool = True
    force: bool = False          # re-scan even if cached (default: serve cache when present)


@app.get("/health")
def health():
    return {"status": "ok", "checks": len(CHECKS)}


@app.get("/catalog")
def catalog():
    return {"n_checks": len(CHECKS), "checks": CHECKS}


def _smart_crawl(url: str, budget: int, static: bool):
    """Static-first for reliability: the httpx crawler is fast and doesn't hang, and today it out-
    performed the browser on every real site. Force static when asked; otherwise run static and only
    fall back to the browser if static comes back thin (a true JS SPA)."""
    if static:
        return crawler.crawl_static(url, budget)
    cr = crawler.crawl_static(url, budget)
    if len(cr.get("pages", [])) >= 3:
        return cr
    try:
        cb = crawler.crawl(url, budget)
        return cb if len(cb.get("pages", [])) > len(cr.get("pages", [])) else cr
    except Exception:
        return cr


_CRAWL_CACHE: dict[str, dict] = {}


def _cached_crawl(url: str, budget: int, static: bool, force: bool = False):
    """Cache the crawl per URL so /scan and /report.pdf don't crawl the same site twice."""
    key = url.rstrip("/").lower()
    if not force and key in _CRAWL_CACHE:
        return _CRAWL_CACHE[key]
    cr = _smart_crawl(url, budget, static)
    _CRAWL_CACHE[key] = cr
    return cr


def _build_report(req: "AssessRequest"):
    """Crawl (cached) + full engine -> a ComplianceReport, shared by /assess, /scan and /report.pdf."""
    crawl = _cached_crawl(req.url, req.budget, req.static, req.force)
    exp = exposure.probe(req.url, pages=crawl.get("pages"), subdomains=crawl.get("subdomains")) if req.exposure else []
    site = re.sub(r"^https?://(www\.)?", "", req.url).split("/")[0]
    rep = compliance_report(url=req.url, pages=crawl["pages"], exposure_findings=exp,
                            is_https=req.url.startswith("https"), site=site, page_budget=req.budget,
                            platform=crawl.get("platform", "Unknown"),
                            archived_policy=crawl.get("archived_policy"),
                            policy_found=crawl.get("policy_found"),
                            subdomains=crawl.get("subdomains"),
                            sec_headers=crawl.get("sec_headers"))
    rep.tracker_inventory = crawl.get("trackers", [])
    rep.cookie_inventory = crawl.get("cookies", [])
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


@app.post("/report.pdf")
def report_pdf(req: AssessRequest):
    """Generate the detailed Compliance PDF for a URL and return it as a file download."""
    from app.compliance.pdf_render import build_compliance_pdf
    from fastapi.responses import FileResponse
    import tempfile
    rep, _ = _build_report(req)
    site = re.sub(r"^https?://(www\.)?", "", req.url).split("/")[0]
    name = (req.org or site).replace(" ", "-") + "-Compliance.pdf"
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    build_compliance_pdf(rep, org=req.org, out_path=tmp.name)
    return FileResponse(tmp.name, media_type="application/pdf", filename=name)


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
