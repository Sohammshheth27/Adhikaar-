"""
subdomains.py -- PASSIVE subdomain discovery (no wordlist brute-forcing).

A compliance officer maps the attack surface without hammering the target: we read what the
Internet already publishes. Passive sources, best first:

  1. subfinder (ProjectDiscovery) -- if the binary is on PATH, use it (aggregates dozens of
     passive sources: CT logs, DNS datasets, search engines).
  2. Certificate Transparency via crt.sh -- every TLS certificate a site issues names its
     subdomains, publicly logged. No requests to the target itself.
  3. Certificate Transparency via certSpotter -- a second CT aggregator, used when crt.sh is
     rate-limited or slow (it frequently is), so discovery never silently returns nothing.

Results are cached on disk per domain (7 days) so a repeated scan -- or a scan run minutes after
a manual check -- reuses the already-published data instead of re-hitting a rate-limited CT log.

Returns real subdomains that actually exist -- never guessed names. Opt-in; off for research
Track-B minimal-footprint mode.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import time

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache", "subdomains")
_CACHE_TTL = 7 * 24 * 3600          # 7 days -- CT logs change slowly


def _cache_path(domain: str) -> str:
    safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in domain.lower())
    return os.path.join(_CACHE_DIR, safe + ".json")


def _cache_read(domain: str) -> list[str] | None:
    try:
        p = _cache_path(domain)
        if not os.path.exists(p):
            return None
        obj = json.load(open(p, encoding="utf-8"))
        if time.time() - obj.get("ts", 0) > _CACHE_TTL:
            return None
        subs = obj.get("subdomains") or []
        return sorted(set(subs)) if subs else None
    except Exception:
        return None


def _cache_write(domain: str, subs: list[str]) -> None:
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        json.dump({"ts": time.time(), "domain": domain, "subdomains": sorted(set(subs))},
                  open(_cache_path(domain), "w", encoding="utf-8"))
    except Exception:
        pass


def _from_subfinder(domain: str, timeout: float = 60.0) -> list[str]:
    exe = shutil.which("subfinder")
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "-d", domain, "-silent", "-all"],
                             capture_output=True, text=True, timeout=timeout)
        return [ln.strip().lower() for ln in out.stdout.splitlines() if ln.strip().endswith(domain)]
    except Exception:
        return []


def _from_crtsh(domain: str, timeout: float = 25.0) -> list[str]:
    try:
        import httpx
    except Exception:
        return []
    names: set[str] = set()
    for _ in range(3):                                   # crt.sh is often slow / rate-limited
        try:
            r = httpx.get("https://crt.sh/", params={"q": f"%.{domain}", "output": "json"},
                          timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and r.text.strip().startswith("["):
                for entry in r.json():
                    for n in (entry.get("name_value", "") or "").split("\n"):
                        n = n.strip().lower().lstrip("*.")
                        if n.endswith(domain) and " " not in n:
                            names.add(n)
                break
        except Exception:
            continue
    return sorted(names)


def _from_certspotter(domain: str, timeout: float = 25.0) -> list[str]:
    """certSpotter CT aggregator -- a second public CT source, used when crt.sh is rate-limited."""
    try:
        import httpx
    except Exception:
        return []
    names: set[str] = set()
    try:
        r = httpx.get("https://api.certspotter.com/v1/issuances",
                      params={"domain": domain, "include_subdomains": "true",
                              "expand": "dns_names"},
                      timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and r.text.strip().startswith("["):
            for entry in r.json():
                for n in (entry.get("dns_names", []) or []):
                    n = (n or "").strip().lower().lstrip("*.")
                    if n.endswith(domain) and " " not in n:
                        names.add(n)
    except Exception:
        pass
    return sorted(names)


def discover(domain: str, use_cache: bool = True) -> list[str]:
    """Passive subdomain discovery with a disk cache and multiple CT sources, so a rate-limited
    source never makes discovery silently return nothing."""
    domain = domain.lower().lstrip(".")
    if use_cache:
        cached = _cache_read(domain)
        if cached:
            return cached
    found: set[str] = set()
    found.update(_from_subfinder(domain))
    if not found:
        found.update(_from_crtsh(domain))
    if not found:
        found.update(_from_certspotter(domain))
    result = sorted(found)
    if result:
        _cache_write(domain, result)
    elif use_cache:                                      # live fetch failed -> fall back to any stale cache
        try:
            p = _cache_path(domain)
            if os.path.exists(p):
                result = sorted(set(json.load(open(p, encoding="utf-8")).get("subdomains") or []))
        except Exception:
            pass
    return result
