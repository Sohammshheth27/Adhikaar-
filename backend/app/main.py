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


@app.post("/assess")
def assess(req: AssessRequest):
    key = req.url.rstrip("/").lower()
    if not req.force and key in _CACHE:                  # instant, deterministic replay for the demo
        return {**_CACHE[key], "cached": True}
    crawl = (crawler.crawl_static(req.url, req.budget) if req.static
             else crawler.crawl(req.url, req.budget))
    exp = exposure.probe(req.url) if req.exposure else []
    site = re.sub(r"^https?://(www\.)?", "", req.url).split("/")[0]
    # Full upgraded engine (same call the CLI uses): multi-source governance + observable-technical.
    rep = compliance_report(url=req.url, pages=crawl["pages"], exposure_findings=exp,
                            is_https=req.url.startswith("https"), site=site, page_budget=req.budget,
                            platform=crawl.get("platform", "Unknown"),
                            archived_policy=crawl.get("archived_policy"),
                            policy_found=crawl.get("policy_found"),
                            subdomains=crawl.get("subdomains"),
                            sec_headers=crawl.get("sec_headers"))
    rep.tracker_inventory = crawl.get("trackers", [])
    rep.cookie_inventory = crawl.get("cookies", [])
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
    crawl = (crawler.crawl_static(req.url, req.budget) if req.static
             else crawler.crawl(req.url, req.budget))
    exp = exposure.probe(req.url) if req.exposure else []
    site = re.sub(r"^https?://(www\.)?", "", req.url).split("/")[0]
    rep = compliance_report(url=req.url, pages=crawl["pages"], exposure_findings=exp,
                            is_https=req.url.startswith("https"), site=site, page_budget=req.budget,
                            platform=crawl.get("platform", "Unknown"),
                            archived_policy=crawl.get("archived_policy"),
                            policy_found=crawl.get("policy_found"),
                            subdomains=crawl.get("subdomains"),
                            sec_headers=crawl.get("sec_headers"))
    out = ui_report(rep, crawl, org=req.org)
    out["cached"] = False
    _UI_CACHE[key] = out
    return out
