"""
auth.py -- authorized AUTHENTICATED scanning.

Many DPDP duties live ONLY behind a sign-in: the rights portal (access / correction / erasure,
ss.11-12), consent management and withdrawal (s.6), data download / portability, nomination
(s.14), and the actual profile data held about the user. A public-only scan reads these as
"Not disclosed" even when they exist, a false negative. This module assesses the logged-in area
using an operator-supplied, authorized session, and feeds the pages to the same engine.

Design:
  * Egress-agnostic. The crawl runs wherever this process runs (a residential line locally, or a
    proxy when hosted -- pass `proxy`). The acquisition of the session is pluggable: a local headed
    login (operator drives a real browser, see session.py), or a supplied storage_state ("bring
    your own session"). A hosted CDP-screencast front-end can feed the same storage_state later.

NON-NEGOTIABLE guardrails (this is an auditor tool, not an agent that acts on an account):
  * READ-ONLY. We only navigate and read. We NEVER submit a form, and we never navigate to a URL
    whose path looks destructive or state-changing (logout, delete, remove, cancel, pay, checkout,
    order, transfer, unsubscribe, deactivate). No clicks at all in the authenticated area.
  * The operator clears every interactive challenge (CAPTCHA, OTP, 2FA) themselves (see session.py).
    This module never solves or bypasses anti-bot.
  * The session (storage_state) is held only for the scan and never written to disk or logged.
    An authorization attestation is required to start the flow (enforced at the API layer).
"""
from __future__ import annotations
import re
import time
from urllib.parse import urljoin, urlparse

from .crawler import (_UA_STRING, _registrable, _extract_text, _auto_scroll, _wait_stable_text,
                      _data_collected, _is_policy_document, _classify_trackers, rank_urls,
                      _detect_platform, CRAWL_DEADLINE_S)

# URLs we must NOT navigate to in an authenticated session: destructive or state-changing routes.
# A compliance crawl of a logged-in area reads pages; it never triggers an account action.
BLOCKED_URL_RX = re.compile(
    r"/(logout|log-out|signout|sign-out|delete|remove|deactivate|close[-_]?account|"
    r"cancel|unsubscribe|pay|payment|checkout|buy|order|purchase|transfer|withdraw|"
    r"send|confirm|approve|reset|revoke)\b", re.I)

# Post-login pages that carry the high-value DPDP duties -- seed and prioritise these.
_AUTH_SEED_PATHS = [
    "/account", "/my-account", "/profile", "/settings", "/account/settings",
    "/privacy", "/privacy-settings", "/account/privacy", "/data", "/my-data",
    "/account/data", "/download-data", "/data-download", "/export",
    "/security", "/account/security", "/consent", "/preferences", "/communication-preferences",
    "/rights", "/data-request", "/dsr", "/nominee", "/nomination", "/manage",
]
_AUTH_VALUE = re.compile(
    r"account|profile|setting|privacy|consent|preference|data|download|export|"
    r"right|request|nominee|nomination|security|personal", re.I)
_SKIP_EXT = re.compile(r"\.(jpg|jpeg|png|gif|svg|pdf|zip|css|js|ico|woff2?)(\?|$)", re.I)


def _safe_to_visit(url: str, origin: str) -> bool:
    """On-origin, not a static asset, and not a destructive/state-changing route."""
    try:
        if _registrable(urlparse(url).netloc) != origin:
            return False
    except Exception:
        return False
    if _SKIP_EXT.search(url) or BLOCKED_URL_RX.search(url):
        return False
    return True


def _rank_auth(urls: list[str], origin: str) -> list[str]:
    """Rank discovered on-origin links by DPDP-in-account value, dropping unsafe ones."""
    scored, seen = [], set()
    for u in urls:
        if u in seen or not _safe_to_visit(u, origin):
            continue
        seen.add(u)
        score = 20 if _AUTH_VALUE.search(u) else 5
        scored.append((score, u))
    scored.sort(key=lambda x: -x[0])
    return [u for _, u in scored]


def _read_only_render(page) -> str:
    """Settle and read a page WITHOUT clicking anything (no consent-accept, no buttons).
    Logged-in areas are read as-is; we never change account state."""
    _auto_scroll(page)
    _wait_stable_text(page, max_ms=9000, quiet_ms=1200)
    return _extract_text(page)


def crawl_authenticated(url: str, storage_state: dict, budget: int = 25,
                        deadline: float | None = None, proxy: str | None = None) -> dict:
    """Read-only crawl of the authenticated area, seeded with the operator's session.

    `storage_state` is a Playwright storage_state dict (cookies + origins). `proxy` (e.g.
    "http://user:pass@host:port") routes egress through a residential/mobile line when hosted;
    None uses this process's own egress (residential, for the local demo). Returns the same shape
    crawler.crawl returns, plus authenticated=True."""
    from playwright.sync_api import sync_playwright
    deadline = deadline or CRAWL_DEADLINE_S
    base = url if url.startswith("http") else "https://" + url
    origin = _registrable(urlparse(base).netloc)
    _start = time.time()
    pages, third_parties, subdomains = [], set(), set()
    subdomains.add(urlparse(base).netloc.lower())
    landing_html, sec_headers = "", {}

    with sync_playwright() as p:
        _args = ["--disable-http2", "--disable-dev-shm-usage",
                 "--disable-blink-features=AutomationControlled"]
        launch_kwargs = {"headless": True, "args": _args}
        if proxy:
            launch_kwargs["proxy"] = {"server": proxy}
        browser = p.chromium.launch(**launch_kwargs)
        ctx = browser.new_context(user_agent=_UA_STRING, locale="en-US",
                                  timezone_id="Asia/Kolkata",
                                  viewport={"width": 1920, "height": 1080},
                                  storage_state=storage_state or None)
        page = ctx.new_page()
        page.on("request", lambda r: third_parties.add(urlparse(r.url).netloc)
                if _registrable(urlparse(r.url).netloc) != origin else None)

        # Frontier: the landing, the site's own sitemap (broad coverage for the leak sweep), and the
        # known account paths. The BFS below then follows REAL links from every page, so the whole
        # logged-in site is spidered instead of only 22 guessed URLs.
        from . import deepcrawl as _dc
        queue = [base]
        try:
            queue += _dc.discover_urls(base, cap=400)
        except Exception:
            pass
        queue += [base.rstrip("/") + sp for sp in _AUTH_SEED_PATHS]

        try:
            resp = page.goto(base, wait_until="commit", timeout=30000)
            try:
                h = {k.lower(): v for k, v in (resp.headers if resp else {}).items()}
                sec_headers = {"hsts": h.get("strict-transport-security", ""),
                               "csp": h.get("content-security-policy", ""),
                               "x_content_type_options": h.get("x-content-type-options", ""),
                               "x_frame_options": h.get("x-frame-options", "")}
            except Exception:
                pass
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            page.wait_for_timeout(1500)
            landing_html = page.content()
            for l in _dc.extract_links(landing_html, base, origin):
                queue.append(l)
                nl = urlparse(l).netloc.lower()
                if nl and _registrable(nl) == origin:
                    subdomains.add(nl)
        except Exception:
            pass

        # BFS: high-value (account/privacy/data/rights) links are visited first, then the rest for
        # broad leak coverage. Each URL is enqueued once; destructive routes are never visited.
        def _order(urls):
            hi = [u for u in urls if _AUTH_VALUE.search(u)]
            lo = [u for u in urls if not _AUTH_VALUE.search(u)]
            return hi + lo
        # Canonicalise (strip tracking/locale params) so the budget is spent on DISTINCT account
        # pages, not the same page re-crawled in several languages.
        queue = _order([_dc.canonicalize(u) for u in dict.fromkeys(queue) if _safe_to_visit(u, origin)])
        enqueued = set(queue)
        seen, seen_content = set(), set()
        while queue:
            if time.time() - _start > deadline or len(pages) >= budget:
                break
            u = queue.pop(0)
            if u in seen or not _safe_to_visit(u, origin):
                continue
            seen.add(u)
            per_before = set(third_parties)
            try:
                resp = page.goto(u, wait_until="commit", timeout=20000)
                if resp is not None and resp.status >= 400:
                    continue
                try:
                    page.wait_for_load_state("networkidle", timeout=7000)
                except Exception:
                    pass
                page.wait_for_timeout(800)
                text = _read_only_render(page)
                html = page.content()
                # enqueue NEW links discovered on this page (recursive spider), high-value first
                try:
                    fresh = []
                    for l in _dc.extract_links(html, page.url, origin):
                        cl = _dc.canonicalize(l)
                        if cl not in enqueued and _safe_to_visit(cl, origin):
                            enqueued.add(cl); fresh.append(cl)
                    hi = [l for l in fresh if _AUTH_VALUE.search(l)]
                    lo = [l for l in fresh if not _AUTH_VALUE.search(l)]
                    queue = hi + queue + lo         # high-value to the front, rest to the back
                except Exception:
                    pass
                if len(text) < 120:
                    continue
                ck = _dc.content_key(text)           # drop a page whose body duplicates one seen
                if ck is not None and ck in seen_content:
                    continue
                if ck is not None:
                    seen_content.add(ck)
                _ispol = _is_policy_document(page.url, text)
                _dcol = _data_collected(html)
                _keep_html = _ispol or bool(_AUTH_VALUE.search(page.url)) or bool(_dcol)
                pages.append({
                    "url": page.url, "text": text, "html": html if _keep_html else "",
                    "is_policy": _ispol, "data_collected": _dcol,
                    "trackers": _classify_trackers(third_parties - per_before),
                    "screenshot": None, "consent_banner": False, "authenticated": True,
                })
            except Exception:
                continue

        try:
            browser.close()
        except Exception:
            pass

    policy_found = any(p["is_policy"] for p in pages)
    return {
        "pages": pages,
        "site_third_parties": sorted(third_parties),
        "subdomains": sorted(subdomains),
        "trackers": _classify_trackers(third_parties),
        "cookies": [],
        "sec_headers": sec_headers,
        "platform": _detect_platform(landing_html or (pages[0]["html"] if pages else "")),
        "policy_found": policy_found,
        "archived_policy": None,
        "authenticated": True,
    }
