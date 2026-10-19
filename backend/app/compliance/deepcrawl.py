"""
deepcrawl.py -- broad attack-surface discovery for the exposure/leak sweep.

A compliance scan has two jobs with opposite coverage needs: DISCLOSURE adequacy is judged on the
policy pages (a handful is enough), but EXPOSURE / data-leak detection must see EVERY page, because
a leaked record or an open file can be anywhere. This module gives the full page inventory of a site
cheaply so the exposure sweep is not limited to the ranked policy pages.

Two sources, cheapest first:
  * robots.txt     -> the Sitemap: directives (and Disallow paths worth probing).
  * sitemap.xml    -> the site's own list of every page (follows <sitemapindex> trees).

Shared by the public crawler and the authenticated crawler (the sitemap is fetched the same way in
both cases; the authenticated crawler then visits those URLs within the logged-in session).
"""
from __future__ import annotations
import re
import hashlib
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit, parse_qsl, urlencode

from .crawler import _UA_STRING, _registrable

# Query parameters that change the URL but NOT the page's substance -- tracking, locale/language,
# session and display params. Stripping them collapses duplicate URLs (e.g. Amazon's language
# switcher ?mons_sel_locale=hi_IN) so the page budget is spent on DISTINCT pages, not re-crawls of
# the same document in six languages. Content-identifying params (nodeId, id, p, page ...) are kept.
_STRIP_PARAMS_EXACT = {
    "mons_sel_locale", "ref_", "ref", "_encoding", "qid", "sr", "th", "psc", "smid", "spm",
    "gclid", "fbclid", "mc_cid", "mc_eid", "igshid", "language", "lang", "hl", "locale",
    "pldnsite", "currency", "cur", "_ga", "_gl", "yclid", "msclkid", "s_kwcid"}
_STRIP_PARAMS_PREFIX = ("utm_", "pf_rd_", "pd_rd_", "pf_", "pd_", "aff_", "_branch_", "mkt_tok")


def canonicalize(url: str) -> str:
    """A stable key for a URL that ignores tracking/locale/session params and the fragment, so two
    URLs that serve the same page collapse to one. Content params are preserved."""
    try:
        s = urlsplit(url)
    except Exception:
        return url
    scheme = (s.scheme or "https").lower()
    netloc = s.netloc.lower()
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    if scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    path = s.path or "/"
    path = re.sub(r"/ref=[^/]*$", "", path)              # strip Amazon-style trailing /ref=... refs
    if len(path) > 1:
        path = path.rstrip("/")
    path = path or "/"
    kept = []
    for k, v in parse_qsl(s.query, keep_blank_values=False):
        kl = k.lower()
        if kl in _STRIP_PARAMS_EXACT or any(kl.startswith(p) for p in _STRIP_PARAMS_PREFIX):
            continue
        kept.append((k, v))
    kept.sort()
    return urlunsplit((scheme, netloc, path, urlencode(kept), ""))


def content_key(text: str) -> str | None:
    """A hash of the page's normalised text, to drop pages whose BODY duplicates one already seen
    (same content served at different URLs, beyond what param-stripping catches)."""
    norm = re.sub(r"\s+", " ", (text or "")).strip().lower()
    if len(norm) < 200:                      # too thin to fingerprint reliably -> never dedup it out
        return None
    return hashlib.md5(norm[:6000].encode("utf-8", "ignore")).hexdigest()

_BROWSER_HEADERS = {"User-Agent": _UA_STRING, "Accept-Language": "en-US,en;q=0.9"}
_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
_SITEMAP_RE = re.compile(r"(?im)^\s*sitemap:\s*(\S+)")
_DISALLOW_RE = re.compile(r"(?im)^\s*disallow:\s*(\S+)")


def _root(base: str) -> str:
    u = urlparse(base if base.startswith("http") else "https://" + base)
    return f"{u.scheme}://{u.netloc}"


def robots_hints(base: str, client=None, timeout: float = 12.0) -> dict:
    """Return {'sitemaps': [...], 'disallows': [...]} from robots.txt (empty on failure)."""
    import httpx
    own = client is None
    if own:
        client = httpx.Client(timeout=timeout, follow_redirects=True, headers=_BROWSER_HEADERS)
    sitemaps, disallows = [], []
    try:
        r = client.get(_root(base) + "/robots.txt")
        if r.status_code < 400 and r.text:
            sitemaps = [s.strip() for s in _SITEMAP_RE.findall(r.text)]
            disallows = [d.strip() for d in _DISALLOW_RE.findall(r.text) if d.strip() not in ("/", "")]
    except Exception:
        pass
    finally:
        if own:
            try: client.close()
            except Exception: pass
    return {"sitemaps": sitemaps, "disallows": disallows}


def discover_urls(base: str, client=None, cap: int = 800, timeout: float = 15.0,
                  max_sitemaps: int = 60) -> list[str]:
    """Return on-origin page URLs discovered from robots.txt + sitemap.xml (follows sitemap indexes).
    Bounded by `cap` URLs and `max_sitemaps` sitemap files so a giant site can't run away."""
    import httpx
    own = client is None
    if own:
        client = httpx.Client(timeout=timeout, follow_redirects=True, headers=_BROWSER_HEADERS)
    origin = _registrable(urlparse(base if base.startswith("http") else "https://" + base).netloc)
    root = _root(base)

    hints = robots_hints(base, client=client)
    queue = list(dict.fromkeys(hints["sitemaps"] or [root + "/sitemap.xml", root + "/sitemap_index.xml",
                                                     root + "/sitemap-index.xml", root + "/wp-sitemap.xml"]))
    found: set[str] = set()
    seen_sm: set[str] = set()
    n_sm = 0
    try:
        while queue and len(found) < cap and n_sm < max_sitemaps:
            sm = queue.pop(0)
            if sm in seen_sm:
                continue
            seen_sm.add(sm); n_sm += 1
            try:
                r = client.get(sm)
            except Exception:
                continue
            if r.status_code >= 400 or not r.text:
                continue
            is_index = "<sitemapindex" in r.text.lower()
            for loc in _LOC_RE.findall(r.text):
                loc = loc.strip()
                if not loc.startswith("http"):
                    loc = urljoin(root + "/", loc)
                if is_index:
                    if loc not in seen_sm:
                        queue.append(loc)
                elif _registrable(urlparse(loc).netloc) == origin:
                    found.add(loc)
                    if len(found) >= cap:
                        break
    finally:
        if own:
            try: client.close()
            except Exception: pass
    return sorted(found)[:cap]


def extract_links(html: str, base: str, origin: str) -> list[str]:
    """On-origin hrefs from a page's HTML (for recursive BFS when there is no/partial sitemap)."""
    out, seen = [], set()
    for href in re.findall(r'href=["\']([^"\'#]+)', html or ""):
        try:
            full = urljoin(base, href)
        except Exception:
            continue
        if full in seen:
            continue
        seen.add(full)
        try:
            if _registrable(urlparse(full).netloc) == origin and full.startswith("http"):
                out.append(full.split("#")[0])
        except Exception:
            continue
    return out
