"""
subdomains.py -- PASSIVE subdomain discovery (no wordlist brute-forcing).

A compliance officer maps the attack surface without hammering the target: we read what the
Internet already publishes. Two passive sources, best first:

  1. subfinder (ProjectDiscovery) -- if the binary is on PATH, use it (aggregates dozens of
     passive sources: CT logs, DNS datasets, search engines).
  2. Certificate Transparency via crt.sh -- every TLS certificate a site issues names its
     subdomains, publicly logged. No requests to the target itself.

Returns real subdomains that actually exist -- never guessed names. Opt-in; off for research
Track-B minimal-footprint mode.
"""
from __future__ import annotations
import json
import shutil
import subprocess


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


def discover(domain: str) -> list[str]:
    """Passive subdomain discovery. subfinder if available, else Certificate Transparency."""
    domain = domain.lower().lstrip(".")
    found = _from_subfinder(domain)
    if not found:
        found = _from_crtsh(domain)
    return sorted(set(found))
