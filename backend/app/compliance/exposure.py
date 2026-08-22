"""
exposure.py -- signal-only probe for sensitive files reachable without authentication.

Reconstructed from the original probe list. Ethics discipline (unchanged): request a fixed,
short list of paths that should never be public; count a path as exposed ONLY on an HTTP 200/206
that returns content; never on 404/403; NEVER retrieve or store the file's contents -- only that
it is reachable and its path. A study of leaked data must never itself become one.
"""
from __future__ import annotations

try:
    import httpx
except Exception:  # httpx optional at import time; probe() will raise if used without it
    httpx = None

# Files that must never be publicly served. Reachability alone is the finding.
CRITICAL_PATHS = [
    "/.env", "/.git/config", "/backup.sql", "/db.sql", "/database.sql", "/dump.sql",
    "/wp-config.php.bak", "/config.php.bak", "/.htpasswd", "/phpinfo.php",
    "/adminer.php", "/.DS_Store",
]
# WordPress route that enumerates user accounts (staff/member names + login ids).
USER_ENUM_PATH = "/wp-json/wp/v2/users"

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
       "X-Adhikaar-Scanner": "https://sohammshheth27.github.io/Adhikaar-scan"}


def _get(base: str, path: str, timeout: float = 8.0):
    if httpx is None:
        raise RuntimeError("httpx is required for exposure probing (pip install httpx)")
    for _ in range(2):                                  # one retry for transient network errors
        try:
            return httpx.get(base.rstrip("/") + path, headers=_UA, timeout=timeout,
                             follow_redirects=False)
        except Exception:
            continue
    return None


def _reachable(base: str, path: str, timeout: float = 8.0) -> bool:
    r = _get(base, path, timeout)
    return bool(r is not None and r.status_code in (200, 206) and r.content)


def _heuristic_probe(base_url: str) -> list[dict]:
    """Built-in signal-only fallback (used when the nuclei binary is not installed).
    Return exposure findings (paths only, never content).

    Catch-all / soft-404 guard: many sites (SPAs behind a CDN, wildcard routers) answer HTTP 200
    with their index page for ANY path. On such a site a file-existence probe is meaningless and
    would raise a false 'exposed .git / database dump' finding. So we first request a random,
    certainly-nonexistent path; if THAT returns content, the server answers 200 for everything and
    we suppress all exposure findings rather than report a false positive.
    """
    base = base_url if base_url.startswith("http") else "https://" + base_url
    # Establish the server's soft-404 baseline from two random, certainly-nonexistent paths.
    ctrls = [_get(base, "/adhikaar-nonexistent-control-9z8y7x1w2v.txt"),
             _get(base, "/__adhikaar_404_probe__/qwerty-zxcvb99.php")]
    ctrl_lens = [len(c.content) for c in ctrls if c is not None and c.status_code in (200, 206) and c.content]
    catch_all = len(ctrl_lens) >= 1        # server answers 200 with content for nonexistent paths

    def _differs_from_baseline(path: str) -> bool:
        """A genuine file's body clearly differs from the soft-404 index page."""
        r = _get(base, path)
        if r is None or r.status_code not in (200, 206) or not r.content:
            return False
        if catch_all and any(abs(len(r.content) - cl) < 512 for cl in ctrl_lens):
            return False
        return True

    findings: list[dict] = []
    raw_hits = [p for p in CRITICAL_PATHS if _reachable(base, p)]
    # Definitive catch-all signal (network-independent): no real site simultaneously exposes 3+ of
    # {.env, .git, backup.sql, db.sql, dump.sql, ...}. If 3+ "match", or a random path also returns
    # content, the server answers 200 for everything and file-existence probing is meaningless.
    if len(raw_hits) >= 3 or catch_all:
        # keep only paths whose body clearly differs from the soft-404 baseline (rarely any)
        hits = [p for p in raw_hits if _differs_from_baseline(p)] if ctrl_lens else []
        user_enum = False
    else:
        hits = raw_hits                                 # 0-2 hits on a non-catch-all site = real
        user_enum = _reachable(base, USER_ENUM_PATH)
    if hits:
        findings.append({
            "id": "exposed_files", "severity": "Critical", "found": hits,
            "detail": (f"{len(hits)} sensitive file(s) are readable in the web root: "
                       f"{', '.join(hits)}. Files of this kind hold credentials, database "
                       "contents or source history and must never be publicly served."),
            "recommendation": ("Remove these files from the web root immediately and rotate any "
                               "credential they may contain."),
            "provision": "Act S.8(5); Rule 6",
        })
    if user_enum:
        findings.append({
            "id": "wp_user_enumeration", "severity": "High", "found": [USER_ENUM_PATH],
            "detail": ("The WordPress users endpoint lists account names and login identifiers "
                       "without authentication."),
            "recommendation": "Disable the REST users endpoint or restrict it to authenticated roles.",
            "provision": "Act S.8(5); Rule 6",
        })
    return findings


# ─────────────────────────────────────────────────────────────────────────────
# Nuclei-powered exposure + security-posture engine (primary path).
# Runs SAFE, detection-only templates over the crawl's discovered URL + subdomain
# surface. No active exploitation / fuzzing / brute-force / DoS. Falls back to the
# built-in _heuristic_probe when the `nuclei` binary is not installed.
# ─────────────────────────────────────────────────────────────────────────────
import os
import json
import re as _re
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse

# detection-only template tags; intrusive/active classes are explicitly excluded
_NUCLEI_TAGS = "exposure,exposures,misconfig,misconfiguration,ssl,tech"
_NUCLEI_EXCLUDE = "intrusive,dos,fuzz,fuzzing,brute-force,bruteforce,sqli,rce,xss"
_PROVISION = "Act S.8(5); Rule 6"
_SEV = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low", "info": "Info"}

# tech-detect classification: which detected technologies matter for DPDP data-flow duties
_TRACKER_RX = _re.compile(r"hotjar|google-analytics|googletagmanager|google-tag|gtag|facebook-pixel|meta-pixel|"
                          r"mixpanel|hubspot|clarity|segment|amplitude|matomo|scorecardresearch|quantcast|"
                          r"criteo|doubleclick|linkedin-insight|fullstory|mouseflow|yandex-metrika", _re.I)
_COLLECTOR_RX = _re.compile(r"contact-form|cfdb|form-db|formidable|gravityforms|gravity-forms|ninja-form|"
                            r"wpforms|forminator|mailchimp|newsletter", _re.I)

_SCAN_CACHE = {}


def _nuclei_available() -> bool:
    return shutil.which("nuclei") is not None


def _target_list(base_url, pages, subdomains):
    urls = {base_url}
    for p in (pages or []):
        u = p.get("url") if isinstance(p, dict) else p
        if u:
            urls.add(u)
    scheme = urlparse(base_url).scheme or "https"
    for sd in (subdomains or []):
        if sd:
            urls.add(scheme + "://" + sd)
    return sorted(urls)


def _pretty(tid):
    return tid.replace("-detect", "").replace("-rum", "").replace("wordpress-", "").replace("-", " ").title()


def _run_nuclei(base_url, pages=None, subdomains=None):
    """Run Nuclei ONCE over the crawl surface; split into security findings + tech signals. Cached."""
    targets = _target_list(base_url, pages, subdomains)
    key = tuple(targets)
    if key in _SCAN_CACHE:
        return _SCAN_CACHE[key]
    tin = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    tin.write("\n".join(targets)); tin.close()
    tout = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False); tout.close()
    cmd = ["nuclei", "-silent", "-jsonl", "-o", tout.name, "-l", tin.name,
           "-tags", _NUCLEI_TAGS, "-exclude-tags", _NUCLEI_EXCLUDE,
           "-severity", "info,low,medium,high,critical",
           "-timeout", "8", "-retries", "1", "-rate-limit", "40", "-disable-update-check"]
    findings, trackers, collectors = [], set(), set()
    try:
        subprocess.run(cmd, capture_output=True, timeout=300)
        with open(tout.name, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                info = d.get("info", {}) or {}
                sev = _SEV.get((info.get("severity") or "").lower(), "Info")
                tid = d.get("template-id", "")
                murl = d.get("matched-at") or d.get("host") or base_url
                if sev != "Info":                       # real security issue -> exposure finding
                    desc = (". " + info["description"]) if info.get("description") else ""
                    findings.append({
                        "id": tid or "nuclei", "severity": sev, "found": [murl],
                        "detail": (info.get("name", "") + desc).strip(),
                        "recommendation": info.get("remediation")
                            or "Review and remediate the exposure/misconfiguration this check identified.",
                        "provision": _PROVISION, "engine": "nuclei",
                    })
                else:                                   # info -> tech-detect: classify for data-flow duties
                    if _TRACKER_RX.search(tid):
                        trackers.add(_pretty(tid))
                    elif _COLLECTOR_RX.search(tid):
                        collectors.add(_pretty(tid))
    except Exception:
        findings = _heuristic_probe(base_url)           # nuclei errored -> safe fallback
    finally:
        for f in (tin.name, tout.name):
            try:
                os.unlink(f)
            except Exception:
                pass
    result = {"findings": findings, "trackers": sorted(trackers), "collectors": sorted(collectors)}
    _SCAN_CACHE[key] = result
    return result


def probe(base_url, pages=None, subdomains=None):
    """Exposure + security-posture probe (Nuclei-led, heuristic fallback). Returns security findings."""
    if _nuclei_available():
        return _run_nuclei(base_url, pages, subdomains)["findings"]
    return _heuristic_probe(base_url)


def tech_signals(base_url, pages=None, subdomains=None):
    """DPDP data-flow signals from Nuclei tech-detect: {trackers:[], collectors:[]}. Empty without nuclei."""
    if _nuclei_available():
        r = _run_nuclei(base_url, pages, subdomains)
        return {"trackers": r["trackers"], "collectors": r["collectors"]}
    return {"trackers": [], "collectors": []}
