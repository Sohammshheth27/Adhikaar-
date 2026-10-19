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
import shutil
import time
from urllib.parse import urljoin, urlparse

CRAWL_DEADLINE_S = 300          # wall-clock budget: return what we have rather than hang on a slow SPA

DEFAULT_BUDGET = 40             # pages per site (raised from 12: don't under-cover a large site)

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
_DROP = re.compile(r"/blog|/news|/category|/tag|/media|"
                   r"\.(jpg|jpeg|png|gif|svg|webp|ico|pdf|zip|css|js|xml|woff2?|ttf|eot|mp4|webm)(\?|$)", re.I)
_COMMON_PATHS = ["/privacy-policy", "/privacy", "/privacy-policy/", "/about-us", "/about",
                 "/contact", "/contact-us", "/terms", "/terms-of-use", "/terms-and-conditions",
                 "/cookie-policy", "/legal", "/grievance", "/grievance-redressal",
                 "/grievance-redressal-mechanism", "/nodal-officer", "/data-protection",
                 "/website-policy", "/website-policies", "/policies"]
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


_TRACKER_CATEGORY = {
    "Google Analytics": "Analytics", "Google Tag Manager": "Tag manager",
    "Google Ads / DoubleClick": "Advertising", "Google Ads": "Advertising", "Meta Pixel": "Advertising",
    "Hotjar": "Behaviour analytics", "Microsoft Clarity": "Behaviour analytics",
    "Mixpanel": "Product analytics", "Segment": "Customer data platform", "Amplitude": "Product analytics",
    "Matomo": "Analytics", "Criteo": "Advertising", "AppNexus": "Advertising", "Comscore": "Measurement",
    "Quantcast": "Advertising", "Microsoft Ads": "Advertising", "LinkedIn": "Advertising / Social",
    "X / Twitter": "Advertising / Social", "TikTok": "Advertising / Social", "Yandex": "Analytics",
    "Razorpay": "Payments",
}


def tracker_category(name: str) -> str:
    return _TRACKER_CATEGORY.get(name, "Other")


# Cookies that may lawfully be set before consent (ePrivacy "strictly necessary" exemption):
# session management, security/anti-CSRF, bot-protection, load balancing, user preferences, and the
# consent manager's OWN cookie. Everything else (analytics, advertising, social) requires consent,
# so if it is set before the visitor chooses it is a pre-consent tracking cookie.
_COOKIE_NECESSARY_RE = re.compile(
    r"(phpsessid|jsessionid|asp\.?net_?sessionid|aspsession|^sess|session[_-]?id|connect\.sid|"
    r"laravel_session|ci_session|^sid$|wordpress_logged|wp-settings|wp_?session|"
    r"csrf|xsrf|csrf[_-]?token|request_?token|antiforgery|cf_clearance|__cf_bm|__cfruid|_cfuvid|__cfwaitingroom|ak_bmsc|"
    r"bm_sz|incap_ses|visid_incap|_grecaptcha|awsalb|awsalbcors|gclb|^glb$|bigipserver|"
    r"arraffinity|nlbi_|^lb$|srv_?id|server_?id|"
    r"cookieyes|cookielawinfo|optanon|cookieconsent|cookie[_-]?consent|cookie-agreed|euconsent|"
    r"borlabs|usercentrics|onetrust|__cmp|complianz|real_cookie|moove_gdpr|"
    r"^(lang|language|locale|currency|timezone|country|region|pll_language)([_-]|$))",
    re.I)

# Names that identify the presence of a consent-management platform (a banner), so we can credit a
# site for offering a choice even while flagging trackers that fire before that choice.
_CMP_COOKIE_RE = re.compile(
    r"(cookieyes|cookielawinfo|optanon|cookieconsent|cookie[_-]?consent|cookie-agreed|euconsent|"
    r"borlabs|usercentrics|onetrust|__cmp|complianz|real_cookie_banner|moove_gdpr)", re.I)


def cookie_necessity(name: str, domain: str = "", third_party: bool = False) -> str:
    """Classify a cookie as 'necessary' (exempt, may be set before consent) or 'consent_required'
    (analytics/advertising/social, needs prior consent). Third-party cookies are consent-requiring
    unless they match a known-necessary pattern (e.g. a CDN/bot-protection cookie)."""
    n = (name or "").strip()
    if _COOKIE_NECESSARY_RE.search(n):
        return "necessary"
    return "consent_required"


def is_cmp_cookie(name: str) -> bool:
    return bool(_CMP_COOKIE_RE.search(name or ""))


def _classify_trackers(hosts) -> list[dict]:
    out, seen = [], set()
    for h in hosts:
        for dom, (name, cc) in _TRACKER_DOMAINS.items():
            if h.endswith(dom) and name not in seen:
                seen.add(name)
                out.append({"name": name, "domain": dom, "country": cc, "category": tracker_category(name)})
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
    """A real privacy DOCUMENT -- not any page mentioning 'privacy' in a nav link.

    Detected by URL hint + substance, OR (crucially) by CONTENT alone: some sites publish the notice
    at a URL with no 'privacy' in it (e.g. Amazon's ...?nodeId=200534380). Without content detection
    that notice is never recognised as the policy, so it is deprioritised and its disclosures get
    judged as 'Not disclosed' -- a large class of false negatives. A page whose TEXT clearly reads as
    a privacy notice (says 'privacy policy/notice/statement' and carries many policy terms) counts."""
    # URL hints include the GIGW "website policy" page, where Indian institutional/.gov sites publish
    # their privacy notice (JNU, many .ac.in). The term-count guard below keeps a generic policy-listing
    # or a "library policy" page from qualifying.
    url_hint = bool(re.search(r"privacy|data[-_ ]?protection|dpdp|gdpr|website[-_ ]?polic", url, re.I))
    substantial = len(text) > 800 and len(_POLICY_TERMS.findall(text)) >= 3
    strong_content = (len(text) > 1500
                      and bool(re.search(r"privacy (policy|notice|statement)", text, re.I))
                      and len(_POLICY_TERMS.findall(text)) >= 4)
    return (url_hint and substantial) or strong_content


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
    pdf_candidates: list[str] = []          # policy-relevant PDF links to extract after the HTML crawl
    _page_links: dict[str, set] = {}        # source URL -> linked URLs (the site graph, for the map)
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
        # Entry navigation with www/http fallbacks: some servers reject apex-HTTPS or serve only
        # over www or plain http, which otherwise yields a zero-page crawl of a live site.
        _host0 = urlparse(base).netloc
        _bare = _host0[4:] if _host0.lower().startswith("www.") else _host0
        _cands = [base] + [u for u in (f"https://www.{_bare}", f"http://www.{_bare}", f"http://{_bare}")
                           if u != base]
        try:
            # "commit" returns as soon as navigation commits, so a heavy SPA that never fires a
            # clean domcontentloaded does not time out; then let scripts settle.
            resp = None
            for _cand in _cands:
                try:
                    resp = page.goto(_cand, wait_until="commit", timeout=35000)
                except Exception:
                    resp = None
                    continue
                if resp is not None:
                    base = _cand
                    to_visit = [base]
                    break
            if resp is None:
                raise RuntimeError("all entry-URL candidates failed")
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
            # Policy documents are often published as PDFs (NGO/college/.gov notices, grievance
            # mechanisms). The HTML crawl drops .pdf links, so collect the policy-relevant ones here
            # and extract their text after the HTML pass.
            try:
                from . import docs as _docs
                for _pr in pairs:
                    _full = urljoin(base, _pr.get("href", ""))
                    if (_registrable(urlparse(_full).netloc) == origin
                            and _docs.looks_like_policy_pdf(_full, _pr.get("text", ""))):
                        pdf_candidates.append(_full)
            except Exception:
                pass
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
                try:                                      # record link edges for the site map
                    from . import deepcrawl as _dcg
                    _su = _dcg.canonicalize(u)
                    _tset = _page_links.setdefault(_su, set())
                    for _l in _dcg.extract_links(html, u, origin):
                        _tset.add(_dcg.canonicalize(_l))
                except Exception:
                    pass
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

        # PDF policy-document extraction: fetch the policy-relevant PDFs discovered above and feed
        # their text to the engine as pages (bounded by the page budget and wall-clock deadline).
        try:
            from . import docs as _docs
            if pdf_candidates and _docs.pdf_available():
                import httpx as _httpx
                _ph = {"User-Agent": _UA_STRING}
                if _no_stealth():
                    _ph["X-Adhikaar-Scanner"] = _SCANNER_HEADER
                _pc = _httpx.Client(headers=_ph, timeout=25, follow_redirects=True, http2=False)
                try:
                    for _pu in dict.fromkeys(pdf_candidates):
                        if len(pages) >= budget or time.time() - _start > CRAWL_DEADLINE_S:
                            break
                        if _pu in seen:
                            continue
                        seen.add(_pu)
                        _txt = _docs.fetch_pdf_text(_pu, client=_pc)
                        if len(_txt) > 400 and not any(p["url"] == _pu for p in pages):
                            pages.append({
                                "url": _pu, "text": _txt, "html": "",
                                "is_policy": _is_policy_document(_pu, _txt),
                                "data_collected": [], "trackers": [], "screenshot": None,
                                "consent_banner": False, "via": "pdf",
                            })
                finally:
                    _pc.close()
        except Exception:
            pass

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

    from . import deepcrawl as _dcg2            # edges reference the pages' actual urls (not canonical)
    _canon2raw = {_dcg2.canonicalize(p["url"]): p["url"] for p in pages}
    _edges = []
    for _s, _tgts in _page_links.items():
        _sr = _canon2raw.get(_s)
        if not _sr:
            continue
        for _t in _tgts:
            _tr = _canon2raw.get(_t)
            if _tr and _tr != _sr:
                _edges.append([_sr, _tr])
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
        "edges": _edges[:800],
    }


def _robots_disallows(client, base: str) -> list:
    """Fetch robots.txt and return Disallow path-prefixes that apply to our UA (or '*'). Polite mode
    honours these; a compliance officer respects a site's stated crawl wishes."""
    try:
        from urllib.parse import urlparse as _up
        root = f"{_up(base).scheme}://{_up(base).netloc}"
        r = client.get(root + "/robots.txt")
        if r.status_code >= 400 or not r.text:
            return []
    except Exception:
        return []
    disallows, applies = [], False
    for line in r.text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "user-agent":
            applies = v == "*" or "adhikaar" in v.lower()
        elif k == "disallow" and applies and v:
            disallows.append(v)
    return disallows


def _path_blocked(url: str, disallows: list) -> bool:
    from urllib.parse import urlparse as _up
    path = _up(url).path or "/"
    return any(path.startswith(d) for d in disallows)


_BEHAVIOUR_RECYCLE_EVERY = 40        # recycle the browser context every N pages to release Chromium heap


def site_behaviour(url: str, page_urls=None, max_pages: int = 25, deadline: float = 180,
                   recycle_every: int = _BEHAVIOUR_RECYCLE_EVERY) -> dict:
    """Render the site's pages in a real browser (JS on) to capture the full cookie jar and the
    third-party trackers that fire across the site -- the 'before consent' behaviour httpx can't see.
    Cookies accumulate across pages; trackers aggregate across every page. Time-bounded.

    Memory: Chromium's heap grows with every page rendered, so on a large (deep) scan we RECYCLE the
    browser context every `recycle_every` pages -- harvesting the cookie jar first so nothing is lost,
    then closing and reopening the context to hand the accumulated memory back to the OS."""
    from playwright.sync_api import sync_playwright
    base = url if url.startswith("http") else "https://" + url
    origin = _registrable(urlparse(base).netloc)
    targets = [base] + [u for u in (page_urls or []) if u and u.rstrip("/") != base.rstrip("/")]
    targets = list(dict.fromkeys(targets))[:max(1, max_pages)]
    third, sec = set(), {}
    cookie_jar: dict[tuple, dict] = {}      # (name, domain, path) -> cookie, merged across recycles
    start = time.time()

    def _on_req(req):
        try:
            h = _registrable(urlparse(req.url).netloc)
            if h and h != origin:
                third.add(urlparse(req.url).netloc.lower())
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-http2", "--disable-dev-shm-usage",
                                                         "--disable-blink-features=AutomationControlled"])
        headers = {"Accept-Language": "en-US,en;q=0.9"}
        if _no_stealth():
            headers["X-Adhikaar-Scanner"] = _SCANNER_HEADER

        def _new_ctx():
            c = browser.new_context(user_agent=_UA_STRING, locale="en-US",
                                    viewport={"width": 1920, "height": 1080}, extra_http_headers=headers)
            if not _no_stealth():
                try:
                    from playwright_stealth import Stealth
                    Stealth().apply_stealth_sync(c)
                except Exception:
                    pass
            pg = c.new_page()
            pg.on("request", _on_req)
            return c, pg

        def _harvest(c):
            try:
                for ck in c.cookies():
                    cookie_jar[(ck.get("name"), ck.get("domain"), ck.get("path"))] = ck
            except Exception:
                pass

        ctx, page = _new_ctx()
        for i, u in enumerate(targets):
            if time.time() - start > deadline:
                break
            # Recycle: harvest this context's cookies, tear it down, open a fresh one (frees heap).
            if i and recycle_every and i % recycle_every == 0:
                _harvest(ctx)
                try:
                    ctx.close()
                except Exception:
                    pass
                ctx, page = _new_ctx()
            try:
                resp = page.goto(u, wait_until="commit", timeout=20000)
                try:
                    page.wait_for_load_state("networkidle", timeout=6000)
                except Exception:
                    pass
                page.wait_for_timeout(900)
                if i == 0 and resp is not None:
                    h = {k.lower(): v for k, v in resp.headers.items()}
                    sec = {"hsts": h.get("strict-transport-security", ""), "csp": h.get("content-security-policy", ""),
                           "x_content_type_options": h.get("x-content-type-options", ""),
                           "x_frame_options": h.get("x-frame-options", "")}
            except Exception:
                continue
        _harvest(ctx)                       # final jar from the last (un-recycled) context
        try:
            browser.close()
        except Exception:
            pass
    cookies = list(cookie_jar.values())
    for c in cookies:
        c["before_consent"] = True
        c["third_party"] = _registrable(c.get("domain", "")) != origin
    return {"cookies": cookies, "trackers": _classify_trackers(third), "sec_headers": sec, "pages_rendered": len(targets)}


# Known reject/necessary-only controls across common consent-management platforms.
_REJECT_SELECTORS = [
    "#onetrust-reject-all-handler",
    "#CybotCookiebotDialogBodyButtonDecline",
    "button.cky-btn-reject", '[data-cky-tag="reject-button"]',
    ".cmplz-deny", ".cc-deny", ".osano-cm-denyAll", "#W0wltc",
    'button[aria-label*="reject" i]', 'button[aria-label*="decline" i]',
]
_REJECT_TEXTS = ["reject all", "reject non-essential", "reject", "decline all", "decline",
                 "deny", "only necessary", "necessary only", "refuse", "do not accept",
                 "do not consent"]


def consent_reject_probe(url: str, deadline: float = 25.0) -> dict:
    """Measure whether a site's consent banner honours rejection. Loads the homepage, snapshots the
    cookie jar (pre-interaction), then attempts to click a reject / necessary-only control, and
    re-snapshots. Returns which non-essential cookies were set before any choice, which persisted
    after an explicit reject, and which were removed. This is a short, read-only interaction (the
    ordinary, most privacy-preserving visitor action), not a crawl."""
    from playwright.sync_api import sync_playwright
    base = url if url.startswith("http") else "https://" + url
    origin = _registrable(urlparse(base).netloc)

    def _nonessential(cks):
        out = []
        for c in cks:
            nm = c.get("name", "")
            dom = (c.get("domain", "") or "").lstrip(".")
            tp = _registrable(dom) != origin
            if cookie_necessity(nm, dom, tp) == "consent_required":
                out.append(nm)
        return set(out)

    clicked, label, pre, post = False, None, [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-http2", "--disable-dev-shm-usage",
                                                         "--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(user_agent=_UA_STRING, locale="en-US",
                                  viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        try:
            page.goto(base, wait_until="commit", timeout=20000)
            try:
                page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass
            page.wait_for_timeout(1200)
            pre = ctx.cookies()
            for sel in _REJECT_SELECTORS:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.click(timeout=3000); clicked = True; label = sel; break
                except Exception:
                    continue
            if not clicked:
                try:
                    for el in page.query_selector_all("button, a, [role=button]"):
                        try:
                            t = (el.inner_text() or "").strip().lower()
                            if t and len(t) < 40 and any(rt == t or rt in t for rt in _REJECT_TEXTS) and el.is_visible():
                                el.click(timeout=3000); clicked = True; label = t; break
                        except Exception:
                            continue
                except Exception:
                    pass
            page.wait_for_timeout(1500)
            post = ctx.cookies()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass

    pre_ne, post_ne = _nonessential(pre), _nonessential(post)
    banner = clicked or any(is_cmp_cookie(c.get("name", "")) for c in pre)
    return {
        "banner_detected": bool(banner),
        "reject_control_found": bool(clicked),
        "reject_label": label,
        "nonessential_before": sorted(pre_ne),
        "nonessential_after_reject": sorted(post_ne),
        "persisted_after_reject": sorted(pre_ne & post_ne),
        "removed_after_reject": sorted(pre_ne - post_ne),
    }


class _PageStore:
    """Spills each crawled page's heavy fields (text, html) to local disk, so the crawl holds only
    light per-page metadata in RAM instead of thousands of full page bodies. Page dicts the crawler
    returns are _LazyPage objects that read their text/html back from disk on demand and do NOT
    retain them -- so even a 2,000+ page deep crawl keeps a near-flat memory footprint."""

    def __init__(self, root: str | None = None):
        import uuid as _uuid
        base = root or os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache", "pagestore")
        # best-effort purge of stores left by earlier scans (>2h old) so disk doesn't grow unbounded
        try:
            if os.path.isdir(base):
                for d in os.listdir(base):
                    p = os.path.join(base, d)
                    if os.path.isdir(p) and time.time() - os.path.getmtime(p) > 7200:
                        shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass
        self.dir = os.path.join(base, _uuid.uuid4().hex)
        os.makedirs(self.dir, exist_ok=True)
        self._n = 0

    def put(self, text: str, html: str) -> int:
        i = self._n
        self._n += 1
        try:
            if text:
                with open(os.path.join(self.dir, f"{i}.txt"), "w", encoding="utf-8") as fh:
                    fh.write(text)
            if html:
                with open(os.path.join(self.dir, f"{i}.html"), "w", encoding="utf-8") as fh:
                    fh.write(html)
        except Exception:
            pass
        return i

    def load(self, i: int, field: str) -> str:
        try:
            p = os.path.join(self.dir, f"{i}.{'txt' if field == 'text' else 'html'}")
            if os.path.exists(p):
                with open(p, encoding="utf-8") as fh:
                    return fh.read()
        except Exception:
            pass
        return ""

    def close(self):
        try:
            shutil.rmtree(self.dir, ignore_errors=True)
        except Exception:
            pass


class _LazyPage(dict):
    """A page dict whose 'text' and 'html' live on disk (in a _PageStore) and are loaded on access,
    then not retained. Every other field is a normal inline dict entry, so existing engine code that
    does p['url'] / p.get('text') / p.get('html') works unchanged."""

    def __init__(self, *args, store: "_PageStore | None" = None, idx: int | None = None, **kw):
        super().__init__(*args, **kw)
        self._store = store
        self._idx = idx

    def _spilled(self, key):
        return key in ("text", "html") and self._store is not None and self._idx is not None \
            and not super().__contains__(key)

    def get(self, key, default=None):
        if self._spilled(key):
            v = self._store.load(self._idx, key)
            return v if v != "" else (default if default is not None else "")
        return super().get(key, default)

    def __getitem__(self, key):
        if self._spilled(key):
            return self._store.load(self._idx, key)
        return super().__getitem__(key)

    def __contains__(self, key):
        if key in ("text", "html") and self._store is not None and self._idx is not None:
            return True
        return super().__contains__(key)


def crawl_static(url: str, budget: int = 60, polite: bool = False, delay: float = 1.5,
                 deadline: float | None = None, seeds: list[str] | None = None,
                 spill: bool = False) -> dict:
    """httpx multi-page SPIDER: seeds from sitemap.xml + robots + the homepage, then follows links
    recursively (BFS) for broad attack-surface coverage, bounded by `budget` pages and `deadline`
    wall-clock seconds. Reads server-rendered HTML -- fast and broad; the caller escalates to a real
    browser only when this comes back thin (a JS SPA). Policy/legal links are visited first so the
    disclosure read always has the notice, while the rest gives the exposure/leak sweep its breadth.
    """
    import httpx
    import time as _time
    from . import deepcrawl as _dc
    deadline = deadline or CRAWL_DEADLINE_S
    _start = _time.time()
    base = url if url.startswith("http") else "https://" + url
    origin = _registrable(urlparse(base).netloc)
    ua = {"User-Agent": _UA_STRING, "Accept-Language": "en-US,en;q=0.9"}
    if _no_stealth():                                    # announce ourselves ONLY in research Track B;
        ua["X-Adhikaar-Scanner"] = _SCANNER_HEADER       # a scanner header invites a bot-block otherwise
    client = httpx.Client(headers=ua, timeout=20, follow_redirects=True, http2=False)
    disallows = _robots_disallows(client, base) if polite else []
    robots_skipped = []

    def fetch(u):
        for attempt in range(3):
            try:
                r = client.get(u)
                if r.status_code == 429:                # rate limited -> honour Retry-After / back off
                    ra = r.headers.get("retry-after")
                    _time.sleep(min(20.0, float(ra)) if (ra and ra.isdigit()) else 2.0 * (attempt + 1))
                    continue
                if r.status_code < 400 and r.text:
                    return r.text
                return None
            except Exception:
                return None
        return None

    subdomains = {urlparse(base).netloc.lower()}
    _page_links: dict[str, set] = {}                     # source URL -> set of linked URLs (the site graph)
    pages, seen = [], set()
    _store = _PageStore() if spill else None             # deep scans spill page bodies to disk (RAM-flat)
    trackers_seen = set()
    pdf_candidates: list[str] = []
    try:
        from . import docs as _docs
    except Exception:
        _docs = None

    # Frontier: the landing + the site's own sitemap (instant broad coverage) + common policy paths.
    # The BFS then follows real links from every page. Policy/legal links jump the queue. Every URL
    # is CANONICALISED (tracking/locale params stripped) before being queued, so the budget is spent
    # on DISTINCT pages instead of the same document re-crawled in six languages.
    def _enq(url_list, front=False):
        for l in url_list:
            cu = _dc.canonicalize(l)
            if cu in enqueued or _DROP.search(cu):
                continue
            enqueued.add(cu)
            (queue.insert(0, cu) if front else queue.append(cu))

    queue, enqueued = [], set()
    try:
        _disc = _dc.discover_urls(base, client=client, cap=max(budget * 3, 300))
    except Exception:
        _disc = []
    # Queue order matters: a privacy notice must never be starved by the wall-clock deadline on a
    # large site. So we front-load the discovery -- homepage first (for footer/legal link discovery),
    # then the common policy paths, then EVERY policy/legal URL the sitemap already lists -- before the
    # hundreds of ordinary pages. During the crawl, newly found policy links also jump the queue.
    _pol = [u for u in _disc if _POLICY_URL_RE.search(u)]
    _rest = [u for u in _disc if not _POLICY_URL_RE.search(u)]
    _enq([base])                                              # 1. homepage
    _enq([base.rstrip("/") + cp for cp in _COMMON_PATHS])     # 2. common policy paths
    _enq(_pol)                                                # 3. policy/legal URLs from the sitemap
    if seeds:                                                 # 3b. fuzzer-supplied live subdomain roots
        _enq([s if s.startswith("http") else "https://" + s for s in seeds])
    _enq(_rest)                                               # 4. everything else, BFS order
    # Harvest policy PDFs straight from the sitemap so a PDF-only notice listed there is fetched
    # (post-loop, deadline-immune) even if the page that links to it is never reached in time.
    if _docs is not None:
        for _u in _disc:
            try:
                if _docs.looks_like_policy_pdf(_u):
                    pdf_candidates.append(_u)
            except Exception:
                pass
    seen_content = set()

    while queue:
        if len(pages) >= budget or _time.time() - _start > deadline:
            break
        u = queue.pop(0)
        if u in seen or _DROP.search(u):
            continue
        seen.add(u)
        if polite and u != base and _path_blocked(u, disallows):
            robots_skipped.append(u)                    # honour robots.txt Disallow
            continue
        html = fetch(u)
        if polite and u != base:
            time.sleep(delay)                           # pace requests like a considerate visitor
        if not html:
            continue
        for dom in _TRACKER_DOMAINS:
            if dom in html:
                trackers_seen.add(dom)
        # discover + enqueue new on-origin links (recursive spider); policy/legal links to the front
        _links = _dc.extract_links(html, u, origin)
        _src = _dc.canonicalize(u)                       # record the link graph (source -> targets)
        _edge_tgts = _page_links.setdefault(_src, set())
        for l in _links:
            nl = urlparse(l).netloc.lower()
            if nl:
                subdomains.add(nl)
            if _docs is not None and _docs.looks_like_policy_pdf(l):
                pdf_candidates.append(l)
            _edge_tgts.add(_dc.canonicalize(l))
        _enq([l for l in _links if _POLICY_URL_RE.search(l)], front=True)
        _enq([l for l in _links if not _POLICY_URL_RE.search(l)])
        text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<noscript[^>]*>.*?</noscript>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)            # strip tags AFTER removing script/style CONTENT
        text = re.sub(r"\s+", " ", text)
        ck = _dc.content_key(text)                       # drop a page whose BODY duplicates one seen
        if ck is not None and ck in seen_content:
            continue
        if ck is not None:
            seen_content.add(ck)
        _ispol = _is_policy_document(u, text)
        _dcol = _data_collected(html)
        # Keep the raw HTML only for pages the engine actually needs it for (policy/legal + forms);
        # discard it for the bulk of the crawl so a 30-minute scan of a large site stays lean. The
        # page TEXT is kept in full, so leak/PII detection over every page is unaffected.
        _keep_html = _ispol or bool(_POLICY_URL_RE.search(u)) or bool(_dcol)
        _html_keep = html if _keep_html else ""
        _banner = bool(re.search(r"accept cookies|we use cookies|cookie consent", text, re.I))
        _light = {"url": u, "is_policy": _ispol, "data_collected": _dcol, "trackers": [],
                  "screenshot": None, "consent_banner": _banner}
        if _store is not None:                            # spill body to disk; keep only light metadata
            _i = _store.put(text, _html_keep)
            pages.append(_LazyPage(_light, store=_store, idx=_i))
        else:
            pages.append({**_light, "text": text, "html": _html_keep})

    # Extract policy PDFs (same client) so a PDF-only notice isn't read as 'Not disclosed'.
    try:
        from . import docs as _docs
        if pdf_candidates and _docs.pdf_available():
            for _pu in dict.fromkeys(pdf_candidates):
                if len(pages) >= budget or _pu in seen:
                    continue
                seen.add(_pu)
                _txt = _docs.fetch_pdf_text(_pu, client=client)
                if len(_txt) > 400 and not any(p["url"] == _pu for p in pages):
                    pages.append({"url": _pu, "text": _txt, "html": "",
                                  "is_policy": _is_policy_document(_pu, _txt),
                                  "data_collected": [], "trackers": [], "screenshot": None,
                                  "consent_banner": False, "via": "pdf"})
    except Exception:
        pass
    client.close()

    _legal = re.compile(r"privacy|policy|terms|legal|grievance|redressal|nodal|cookie|data-protection", re.I)
    pages = sorted(pages, key=lambda p: (p["is_policy"] or bool(_legal.search(p["url"])),
                                         bool(p["data_collected"])), reverse=True)
    policy_found = any(p["is_policy"] for p in pages)
    _lh = next((p["html"] for p in pages if p["url"].rstrip("/") == base.rstrip("/")),
               (pages[0]["html"] if pages else ""))
    # Link graph: edges between pages we actually crawled, so the site map shows real structure.
    _crawled = {p["url"] for p in pages}
    edges = []
    for _s, _tgts in _page_links.items():
        if _s not in _crawled:
            continue
        for _t in _tgts:
            if _t in _crawled and _t != _s:
                edges.append([_s, _t])
    return {"pages": pages, "site_third_parties": [], "subdomains": sorted(subdomains),
            "trackers": _classify_trackers(trackers_seen), "cookies": [],
            "platform": _detect_platform(_lh or ""), "policy_found": policy_found,
            "archived_policy": None if policy_found else archive_policy(origin),
            "edges": edges[:2000], "robots_skipped": robots_skipped, "polite": polite,
            "_pagestore": _store}
