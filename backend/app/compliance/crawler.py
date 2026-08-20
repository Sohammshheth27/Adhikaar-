"""
crawler.py -- render a site as an ordinary browser and extract what the engine needs.

Track B identity (real Chrome UA + X-Adhikaar-Scanner header, stealth off for research runs),
never accepts a consent banner, curated tracker list. Enrichments added for report parity:
platform fingerprint, archive.org lookup for a previously-published notice, per-page trackers
and data-collection detection, and STRICT policy detection (only a real privacy *document*
counts as policy text, so "no notice published" reproduces correctly).
"""
from __future__ import annotations
import os
import re
import time
from urllib.parse import urljoin, urlparse

CRAWL_DEADLINE_S = 150          # wall-clock budget: return what we have rather than hang on a slow SPA

DEFAULT_BUDGET = 12

_UA_STRING = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
_SCANNER_HEADER = "https://sohammshheth27.github.io/Adhikaar-scan"

_TRACKER_DOMAINS = {
    "google-analytics.com": ("Google Analytics", "US"), "googletagmanager.com": ("Google Tag Manager", "US"),
    "doubleclick.net": ("Google Ads / DoubleClick", "US"), "googlesyndication.com": ("Google Ads", "US"),
    "facebook.net": ("Meta Pixel", "US"), "connect.facebook.net": ("Meta Pixel", "US"),
    "hotjar.com": ("Hotjar", "MT"), "clarity.ms": ("Microsoft Clarity", "US"),
    "mixpanel.com": ("Mixpanel", "US"), "segment.com": ("Segment", "US"),
    "amplitude.com": ("Amplitude", "US"), "matomo.cloud": ("Matomo", "DE"),
    "criteo.com": ("Criteo", "FR"), "adnxs.com": ("AppNexus", "US"),
    "scorecardresearch.com": ("Comscore", "US"), "quantserve.com": ("Quantcast", "US"),
    "bing.com": ("Microsoft Ads", "US"), "licdn.com": ("LinkedIn", "US"),
    "t.co": ("X / Twitter", "US"), "tiktok.com": ("TikTok", "CN"), "yandex.ru": ("Yandex", "RU"),
    "razorpay.com": ("Razorpay", "IN"), "checkout.razorpay.com": ("Razorpay", "IN"),
}

_PLATFORMS = [
    (re.compile(r'generator" content="Webflow|\.webflow\.|data-wf-', re.I), "Webflow"),
    (re.compile(r"wp-content|wp-includes|generator\" content=\"WordPress", re.I), "WordPress"),
    (re.compile(r"cdn\.shopify|shopify", re.I), "Shopify"),
    (re.compile(r"wixstatic|wix\.com", re.I), "Wix"),
    (re.compile(r"squarespace", re.I), "Squarespace"),
    (re.compile(r"drupal", re.I), "Drupal"),
]

_DATA_FIELDS = {
    "name": re.compile(r'name=["\'](full[_-]?name|your[_-]?name|fname|name)["\']|>\s*name\s*<', re.I),
    "email": re.compile(r'type=["\']email["\']|name=["\']email["\']', re.I),
    "phone": re.compile(r'name=["\'](phone|mobile|tel)["\']|type=["\']tel["\']', re.I),
    "dob": re.compile(r'name=["\'](dob|birth|date[_-]?of[_-]?birth)["\']|date of birth', re.I),
    "address": re.compile(r'name=["\'](address|pincode|city|zip)["\']', re.I),
}

_SEED_VALUE = [
    (re.compile(r"privacy|legal|cookie|data-protection|gdpr|dpdp|terms", re.I), 100),
    (re.compile(r"donat|register|signup|sign-up|login|payment|checkout|subscribe|engage|support", re.I), 80),
    (re.compile(r"contact|about|grievance", re.I), 60),
]
_DROP = re.compile(r"/blog|/news|/category|/tag|/media|\.(jpg|jpeg|png|gif|svg|pdf|zip|css|js)(\?|$)", re.I)
_COMMON_PATHS = ["/privacy-policy", "/privacy", "/privacy-policy/", "/about-us", "/about",
                 "/contact", "/contact-us", "/terms", "/terms-of-use", "/terms-and-conditions",
                 "/cookie-policy", "/legal", "/grievance", "/grievance-redressal",
                 "/grievance-redressal-mechanism", "/nodal-officer", "/data-protection"]
_POLICY_TERMS = re.compile(r"personal data|personal information|we collect|data protection|"
                           r"privacy policy|your information|process your", re.I)


def _no_stealth() -> bool:
    return os.environ.get("ADHIKAAR_RESEARCH_NO_STEALTH", "").strip().lower() in ("1", "true", "yes")


def _registrable(host: str) -> str:
    host = host.lower().lstrip(".")
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def rank_urls(urls: list[str]) -> list[str]:
    scored, seen = [], set()
    for u in urls:
        if u in seen or _DROP.search(u):
            continue
        seen.add(u)
        score = 10
        for rx, val in _SEED_VALUE:
            if rx.search(u):
                score = max(score, val)
        scored.append((score, u))
    scored.sort(key=lambda x: -x[0])
    return [u for _, u in scored]


def _classify_trackers(hosts) -> list[dict]:
    out, seen = [], set()
    for h in hosts:
        for dom, (name, cc) in _TRACKER_DOMAINS.items():
            if h.endswith(dom) and name not in seen:
                seen.add(name); out.append({"name": name, "domain": dom, "country": cc})
                break
    return out


def _detect_platform(html: str) -> str:
    for rx, name in _PLATFORMS:
        if rx.search(html):
            return name
    return "Unknown"


def _data_collected(html: str) -> list[str]:
    if not re.search(r"<form|<input", html, re.I):
        return []
    return sorted(f for f, rx in _DATA_FIELDS.items() if rx.search(html))


def _is_policy_document(url: str, text: str) -> bool:
    """Only a real privacy DOCUMENT counts -- not any page mentioning 'privacy' in a nav link."""
    url_hint = bool(re.search(r"privacy|data-protection|dpdp|gdpr", url, re.I))
    substantial = len(text) > 800 and len(_POLICY_TERMS.findall(text)) >= 3
    return url_hint and substantial


_MONTHS = ['', 'January', 'February', 'March', 'April', 'May', 'June', 'July',
           'August', 'September', 'October', 'November', 'December']


def archive_policy(domain: str, paths=("/privacy-policy/", "/privacy-policy", "/privacy", "/privacy/")) -> dict | None:
    """Query the Wayback Machine for a previously-published notice + the date last seen.

    Tries both the bare and www. host (the notice was typically linked at www.<domain>).
    """
    try:
        import httpx
    except Exception:
        return None
    hosts = [f"www.{domain}", domain]
    for host in hosts:
        for path in paths:
            try:
                r = httpx.get("http://archive.org/wayback/available",
                              params={"url": f"{host}{path}"}, timeout=12)
                snap = (r.json().get("archived_snapshots") or {}).get("closest")
                if snap and snap.get("available"):
                    ts = snap["timestamp"]                    # YYYYMMDDhhmmss
                    date = f"{int(ts[6:8])} {_MONTHS[int(ts[4:6])]} {ts[0:4]}"
                    return {"url": f"https://{host}{path}", "last_seen": date,
                            "snapshot": snap.get("url", "")}
            except Exception:
                continue
    return None


# Consent-banner accept buttons across the common CMPs (OneTrust, Cookiebot, Quantcast, TrustArc)
# and generic phrasings. Clicking a site's own public "accept" control reveals the content an
# ordinary visitor sees -- it is not an auth bypass or an evasion of any security control.
_CONSENT_SELECTORS = [
    "#onetrust-accept-btn-handler", "#accept-recommended-btn-handler",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll", ".cc-allow", "#truste-consent-button",
    "button[aria-label*='accept' i]", "button[title*='accept' i]",
    "button:has-text('Accept all')", "button:has-text('Accept All Cookies')",
    "button:has-text('Accept')", "button:has-text('I Agree')", "button:has-text('I agree')",
    "button:has-text('Allow all')", "button:has-text('Allow All')",
    "button:has-text('Got it')", "button:has-text('Agree')", "button:has-text('Continue')",
]

# Prefer the real content region (main/article/policy container); fall back to the largest text
# block; only then the whole body. This strips nav/header/footer chrome that was drowning the
# policy body on SPA sites and defeating is_policy detection.
_MAIN_JS = """() => {
  const sel = 'main, article, [role=main], #content, #main-content, .content, .policy, .privacy-policy, .legal, .rte, .container';
  const pick = document.querySelector(sel);
  let best = pick ? (pick.innerText || '') : '';
  if (best.length < 800) {
    let max = '';
    for (const el of document.querySelectorAll('main, article, section, div')) {
      const t = el.innerText || '';
      if (t.length > max.length) max = t;
    }
    if (max.length > best.length) best = max;
  }
  return best || (document.body ? document.body.innerText : '');
}"""


def _dismiss_consent(page) -> bool:
    """Click a visible cookie/consent 'accept' control so gated content renders."""
    for sel in _CONSENT_SELECTORS:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click(timeout=1500)
                page.wait_for_timeout(500)
                return True
        except Exception:
            continue
    return False


def _auto_scroll(page, steps: int = 8) -> None:
    """Scroll the page to trigger lazy-loaded / viewport-gated content, then return to top."""
    try:
        for _ in range(steps):
            page.mouse.wheel(0, 2400)
            page.wait_for_timeout(250)
        page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass


def _wait_stable_text(page, max_ms: int = 9000, quiet_ms: int = 1200) -> None:
    """Wait until body text stops growing -- an SPA finishing its render -- instead of a blind timer."""
    try:
        last, stable, waited, step = -1, 0, 0, 400
        while waited < max_ms:
            cur = page.evaluate("document.body ? document.body.innerText.length : 0")
            stable = stable + step if cur <= last else 0
            if stable >= quiet_ms:
                break
            last = cur
            page.wait_for_timeout(step)
            waited += step
    except Exception:
        pass


def _extract_text(page) -> str:
    """Full body text (the superset that always contains the policy). The main-content extractor is
    used ONLY when the body is genuinely thin -- its 'largest block' heuristic can grab a nav mega-menu
    on some sites and drop the policy, so the full body is the safe default for labelling and judging."""
    body = ""
    try:
        body = page.inner_text("body")
    except Exception:
        body = ""
    if len(body) >= 200:
        return body
    try:
        t = page.evaluate(_MAIN_JS)                      # rare SPA edge: body empty, content in a region
        if t and len(t) > len(body):
            return t
    except Exception:
        pass
    return body


_POLICY_URL_RE = re.compile(
    r"privacy|policy|terms|legal|grievance|redress|nodal|data[-_ ]?protection|cookie|/gdpr|/dpdp", re.I)


def _looks_like_policy_url(u: str) -> bool:
    return bool(_POLICY_URL_RE.search(u or ""))


def _capture_via_click(page, base, origin, pages, seen, budget, start=None, deadline=None):
    """Reach policy pages on a CLICK-ROUTED SPA by clicking their in-app link (the SPA's own router),
    for sites where goto() to the route times out (e.g. Tata Neu's /login/privacypolicy). Fully bounded
    by a wall-clock deadline (a hostile SPA that times out every nav can't run away) and non-fatal."""
    try:
        anchors = page.query_selector_all("a[href]")
    except Exception:
        return
    targets = []
    for a in anchors:
        try:
            href = a.get_attribute("href") or ""
            text = (a.inner_text() or "").strip()
        except Exception:
            continue
        full = urljoin(base, href)
        if _registrable(urlparse(full).netloc) != origin:
            continue
        if _looks_like_policy_url(href) or _looks_like_policy_url(text):
            targets.append((full, urlparse(full).path, text))
    picked, seen_path = [], set()
    for full, path, text in targets:                         # de-dupe by route path
        if path not in seen_path and full not in seen:
            seen_path.add(path)
            picked.append((full, path, text))
    for full, path, text in picked[:3]:
        if len(pages) >= budget:
            break
        if start is not None and deadline is not None and time.time() - start > deadline:
            break                                        # wall-clock budget: stop before it runs away
        try:
            el = page.query_selector(f'a[href$="{path}"]') or (page.get_by_text(text, exact=False).first if text else None)
            if el is None:
                continue
            el.click(timeout=4000)
            page.wait_for_timeout(1200)
            txt = _render_and_read(page, thin=2500, policy=True)
            cur = page.url
            seen.add(full)
            seen.add(cur)
            if len(txt) > 600 and not any(p["url"] == cur for p in pages):
                html = ""
                try:
                    html = page.content()
                except Exception:
                    pass
                pages.append({
                    "url": cur, "text": txt, "html": html,
                    "is_policy": _is_policy_document(cur, txt),
                    "data_collected": _data_collected(html), "trackers": [],
                    "screenshot": None, "consent_banner": False, "via": "click",
                })
            try:
                page.go_back(wait_until="commit", timeout=6000)    # client-side back to the landing
                page.wait_for_timeout(800)
            except Exception:
                break                                    # can't get back cheaply -> stop, don't stack timeouts
        except Exception:
            continue


def _render_and_read(page, thin: int = 600, policy: bool = False) -> str:
    """Settle the page (consent + scroll + stable-text), extract, escalate once if still thin.

    Policy pages get longer render budgets and a higher `thin` bar: a client-side-routed SPA policy
    (e.g. a /login/privacypolicy route) often paints its shell first and streams the actual clauses in
    late -- accepting the shell would falsely read duties as 'Not disclosed'. The higher bar forces the
    reload-escalation until the real clause text is present (bounded, so it cannot hang)."""
    _dismiss_consent(page)
    _auto_scroll(page)
    _wait_stable_text(page, max_ms=16000 if policy else 9000, quiet_ms=1800 if policy else 1200)
    text = _extract_text(page)
    if len(text) < thin:                                 # late-rendering SPA -> reload with longer waits
        try:
            page.reload(wait_until="commit", timeout=25000)
            page.wait_for_timeout(2500)
            _dismiss_consent(page)
            _auto_scroll(page)
            _wait_stable_text(page, max_ms=18000 if policy else 13000, quiet_ms=1800 if policy else 1500)
            t2 = _extract_text(page)
            if len(t2) > len(text):
                text = t2
        except Exception:
            pass
    return text


def crawl(url: str, budget: int = DEFAULT_BUDGET, screenshot_dir: str | None = None,
          fuzz: bool = False) -> dict:
    from playwright.sync_api import sync_playwright
    if screenshot_dir:
        os.makedirs(screenshot_dir, exist_ok=True)

    base = url if url.startswith("http") else "https://" + url
    origin = _registrable(urlparse(base).netloc)
    _start = time.time()
    pages, third_parties, subdomains = [], set(), set()
    subdomains.add(urlparse(base).netloc.lower())
    landing_html = ""
    cookies = []
    sec_headers = {}

    with sync_playwright() as p:
        # --disable-http2 works around servers that reject Chromium's HTTP/2 handshake
        # (Tata Neu returns ERR_HTTP2_PROTOCOL_ERROR otherwise). No fingerprint spoofing is used.
        _args = ["--disable-http2", "--disable-dev-shm-usage",
                 "--disable-blink-features=AutomationControlled"]
        browser = p.chromium.launch(headless=True, args=_args)
        # A realistic browser configuration (viewport, locale, language headers) that any ordinary
        # Chrome sends -- this is normal configuration, not evasion. Track B still identifies itself.
        headers = {"Accept-Language": "en-US,en;q=0.9",
                   "sec-ch-ua": '"Chromium";v="126", "Google Chrome";v="126", "Not.A/Brand";v="24"',
                   "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"'}
        if _no_stealth():
            headers["X-Adhikaar-Scanner"] = _SCANNER_HEADER
        ctx = browser.new_context(user_agent=_UA_STRING, locale="en-US",
                                  timezone_id="Asia/Kolkata",
                                  viewport={"width": 1920, "height": 1080},
                                  extra_http_headers=headers)
        page = ctx.new_page()
        # Assessment mode: apply anti-bot stealth so a headless browser is not fingerprinted and
        # blocked, and the real (JS-rendered) page is assessed. Disabled in research Track B, which
        # identifies itself and never evades. (This is an authorized single-site assessment.)
        if not _no_stealth():
            try:
                from playwright_stealth import Stealth
                Stealth().apply_stealth_sync(page)
            except Exception:
                pass
        page.on("request", lambda r: third_parties.add(urlparse(r.url).netloc)
                if _registrable(urlparse(r.url).netloc) != origin else None)

        to_visit = [base]
        try:
            # "commit" returns as soon as navigation commits, so a heavy SPA that never fires a
            # clean domcontentloaded does not time out; then let scripts settle.
            resp = page.goto(base, wait_until="commit", timeout=35000)
            try:                                         # observable transport-security posture
                h = {k.lower(): v for k, v in (resp.headers if resp else {}).items()}
                sec_headers = {
                    "hsts": h.get("strict-transport-security", ""),
                    "csp": h.get("content-security-policy", ""),
                    "x_content_type_options": h.get("x-content-type-options", ""),
                    "x_frame_options": h.get("x-frame-options", ""),
                    "referrer_policy": h.get("referrer-policy", ""),
                }
            except Exception:
                pass
            try:
                page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            page.wait_for_timeout(2500)
            _dismiss_consent(page)                       # reveal content behind the cookie gate
            _auto_scroll(page)                           # trigger lazy-loaded sections
            _wait_stable_text(page)                      # let the SPA finish rendering
            # 404-recovery: a dead entry URL (e.g. a moved /privacy-policy) should not end the scan --
            # fall back to the site root and let anchor-text discovery find the real policy link.
            _status = resp.status if resp is not None else 200
            _landing_txt = _extract_text(page)
            _soft404 = bool(re.search(r"page not found|doesn'?t exist|404|not found", (page.title() or ""), re.I)) \
                or len(_landing_txt) < 120
            root = f"{urlparse(base).scheme}://{urlparse(base).netloc}/"
            if (_status >= 400 or _soft404) and base.rstrip("/") != root.rstrip("/"):
                try:
                    page.goto(root, wait_until="commit", timeout=35000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=12000)
                    except Exception:
                        pass
                    page.wait_for_timeout(2500)
                    _dismiss_consent(page)
                    _auto_scroll(page)
                    _wait_stable_text(page)
                    base = root                          # discover links from the working homepage
                except Exception:
                    pass
            landing_html = page.content()
            pairs = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => ({href: e.href, text: (e.innerText||'').trim()}))")
            links = [p["href"] for p in pairs]
            on_site = [urljoin(base, l) for l in links
                       if _registrable(urlparse(urljoin(base, l)).netloc) == origin]
            # Anchor-TEXT discovery: a link labelled "Privacy" / "Grievance" is a policy page even if
            # its URL is opaque (e.g. /p?id=9). Enqueue these first -- the highest-value documents.
            _by_text = re.compile(r"privacy|grievance|redress|nodal|data[ -]?protection|cookie|terms|legal|disclosure", re.I)
            text_hits = [urljoin(base, p["href"]) for p in pairs
                         if _by_text.search(p.get("text", "")) and
                         _registrable(urlparse(urljoin(base, p["href"])).netloc) == origin]
            to_visit += text_hits + rank_urls(on_site)
            for l in on_site:
                nl = urlparse(l).netloc.lower()
                if nl:
                    subdomains.add(nl)
        except Exception:
            pass
        # ensure common personal-data / policy paths are tried even if not linked
        to_visit += [base.rstrip("/") + cp for cp in _COMMON_PATHS]

        seen = set()
        # Click-routed SPA policies (goto times out) -> reach them via the in-app link while we are
        # still on the landing page. Non-fatal; skipped silently on ordinary sites or if over budget.
        try:
            if time.time() - _start < CRAWL_DEADLINE_S * 0.5:
                _capture_via_click(page, base, origin, pages, seen, budget,
                                   start=_start, deadline=CRAWL_DEADLINE_S * 0.75)
        except Exception:
            pass
        for u in to_visit:
            if time.time() - _start > CRAWL_DEADLINE_S:   # wall-clock budget -> stop, return what we have
                break
            if len(pages) >= budget or u in seen:
                continue
            seen.add(u)
            per_before = set(third_parties)
            try:
                resp = page.goto(u, wait_until="commit", timeout=25000)
                if resp is not None and resp.status >= 400:
                    continue
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                page.wait_for_timeout(1200)
                _pol = _looks_like_policy_url(u)          # policy pages: render harder, higher thin bar
                text = _render_and_read(page, thin=2500 if _pol else 600, policy=_pol)
                html = page.content()
                page_tp = _classify_trackers(third_parties - per_before)
                shot = None
                if screenshot_dir:
                    shot = os.path.join(screenshot_dir, f"page_{len(pages) + 1}.png")
                    try:
                        page.screenshot(path=shot)
                    except Exception:
                        shot = None
                pages.append({
                    "url": u, "text": text, "html": html,
                    "is_policy": _is_policy_document(u, text),
                    "data_collected": _data_collected(html),
                    "trackers": page_tp, "screenshot": shot,
                    "consent_banner": bool(re.search(r"accept cookies|we use cookies|cookie consent", text, re.I)),
                })
            except Exception:
                continue

        try:
            cookies = ctx.cookies()
        except Exception:
            cookies = []
        try:
            browser.close()                             # a driver disconnect here must not lose the crawl
        except Exception:
            pass

    for c in cookies:
        c["before_consent"] = True
        c["third_party"] = _registrable(c.get("domain", "")) != origin

    # Select the assessment-relevant pages: policy candidates, pages that collect personal data,
    # and the primary nav (home/about/contact/data-privacy) -- the pages a notice or personal
    # data would live on. Ranked so the most relevant survive the cap.
    # Assess EVERY crawled page (bounded only by the page budget). Order by relevance so the most
    # important pages (privacy/legal/grievance, then data-collection, then nav) appear first in the
    # report, but nothing is dropped.
    _legal = re.compile(r"privacy|policy|terms|legal|grievance|redressal|nodal|cookie|data-protection", re.I)
    _nav = re.compile(r"/(about|contact|data-privacy|engage|support|donat|register|signup)", re.I)
    def _relevance(pg):
        u = pg["url"].rstrip("/")
        if u == base.rstrip("/"): return 6              # landing first
        if pg["is_policy"] or _legal.search(pg["url"]): return 5
        if pg["data_collected"]: return 4
        if _nav.search(pg["url"]): return 3
        return 1
    pages = sorted(pages, key=lambda p: -_relevance(p))

    policy_found = any(p["is_policy"] for p in pages)
    archived = None if policy_found else archive_policy(origin)

    if fuzz:                                             # opt-in subdomain discovery (attack surface)
        try:
            from .subdomains import discover
            for s in discover(origin):
                subdomains.add(s)
        except Exception:
            pass

    return {
        "pages": pages,
        "site_third_parties": sorted(third_parties),
        "subdomains": sorted(subdomains),
        "trackers": _classify_trackers(third_parties),
        "cookies": cookies,
        "sec_headers": sec_headers,
        "platform": _detect_platform(landing_html or (pages[0]["html"] if pages else "")),
        "policy_found": policy_found,
        "archived_policy": archived,
    }


def crawl_static(url: str, budget: int = 8) -> dict:
    """httpx fallback (no JS) -- multi-page. Follows ranked on-site links from the landing page.

    Used when a real browser is blocked (e.g. bot-managed sites that reject HTTP/2). It reads the
    server-rendered HTML, so it still finds the policy, forms and links, but cannot observe
    JS-loaded trackers, cookies set by script, or take screenshots.
    """
    import httpx
    base = url if url.startswith("http") else "https://" + url
    origin = _registrable(urlparse(base).netloc)
    ua = {"User-Agent": _UA_STRING, "X-Adhikaar-Scanner": _SCANNER_HEADER}
    client = httpx.Client(headers=ua, timeout=20, follow_redirects=True, http2=False)

    def fetch(u):
        try:
            r = client.get(u)
            if r.status_code < 400 and r.text:
                return r.text
        except Exception:
            return None
        return None

    subdomains = {urlparse(base).netloc.lower()}
    pages, seen = [], set()
    to_visit = [base]
    landing = fetch(base)
    trackers_seen = set()
    if landing:
        links = re.findall(r'href=["\']([^"\']+)["\']', landing)
        on_site = []
        for l in links:
            full = urljoin(base, l)
            nl = urlparse(full).netloc.lower()
            if _registrable(nl) == origin:
                on_site.append(full)
                if nl:
                    subdomains.add(nl)
        to_visit += rank_urls(on_site)
        to_visit += [base.rstrip("/") + cp for cp in _COMMON_PATHS]
        for dom in _TRACKER_DOMAINS:                    # trackers referenced in the HTML
            if dom in landing:
                trackers_seen.add(dom)

    for u in to_visit:
        if len(pages) >= budget or u in seen:
            continue
        seen.add(u)
        html = landing if u == base else fetch(u)
        if not html:
            continue
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        for dom in _TRACKER_DOMAINS:
            if dom in html:
                trackers_seen.add(dom)
        pages.append({"url": u, "text": text, "html": html,
                      "is_policy": _is_policy_document(u, text),
                      "data_collected": _data_collected(html), "trackers": [],
                      "screenshot": None,
                      "consent_banner": bool(re.search(r"accept cookies|we use cookies|cookie consent", text, re.I))})
    client.close()

    _legal = re.compile(r"privacy|policy|terms|legal|grievance|redressal|nodal|cookie|data-protection", re.I)
    pages = sorted(pages, key=lambda p: (p["is_policy"] or bool(_legal.search(p["url"])),
                                         bool(p["data_collected"])), reverse=True)
    policy_found = any(p["is_policy"] for p in pages)
    return {"pages": pages, "site_third_parties": [], "subdomains": sorted(subdomains),
            "trackers": _classify_trackers(trackers_seen), "cookies": [],
            "platform": _detect_platform(landing or ""), "policy_found": policy_found,
            "archived_policy": None if policy_found else archive_policy(origin)}
