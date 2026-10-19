"""
ui_map.py -- map the 47-duty engine result into the shape the Scanner web UI renders.

The frontend (Scanner.dc.html) expects:
    { risk:  {level, summary, collects[], baseline, rights},
      checks:[{id,title,citation,verdict,evidence,evidence_page,finding,fix}],   # 12 grouped checks
      coverage:{reached[], unreached[{page,reason}]} }

Each UI check aggregates a group of the 47 DPDP duties. Verdict per group = the strongest grounded
verdict among its duties (so a UI area reads PASS when the site genuinely addresses it). Evidence and
fixes come straight from the engine's findings -- verbatim, never synthesised.
"""
from __future__ import annotations

# UI check id, title, citation, and the DPDP duty ids it aggregates.
UI_CHECKS = [
    ("notice", "Notice present and itemised", "Act s.5 + Rules r.3", [1, 2, 3]),
    ("notice_means", "Notice states how to withdraw, exercise rights, complain", "Rules r.3", [3, 11, 16]),
    ("consent", "Consent free, specific, informed, unambiguous, affirmative", "Act s.6(1)", [4, 12]),
    ("withdrawal", "Withdrawal as easy as giving", "Act s.6(4)-(6)", [11]),
    ("banner", "Consent/cookie banner: reject as easy as accept", "Act s.6(1) + Rules r.4", [12, 34]),
    ("contact", "Business contact published", "Act s.8(9)", [21]),
    ("grievance", "Grievance-redressal mechanism", "Act s.8(10)", [19]),
    ("rights", "Rights mechanism (access, correct, erase, nominate)", "Act ss.11-14", [16, 17, 18, 20]),
    ("retention", "Retention and erasure", "Act s.8(7)-(8) + Rules r.8", [8]),
    ("security", "Security safeguards and breach readiness", "Act s.8(5)-(6) + Rules r.7", [9, 10, 38, 39]),
    ("children", "Children's data", "Act s.9", [15]),
    ("crossborder", "Cross-border transfer disclosure", "Act s.16", [27]),
]

# our verdict -> UI verdict
_V = {"Compliant": "PASS", "Partial": "PARTIAL", "Gap": "GAP",
      "Not disclosed": "GAP", "Not externally verifiable": "COULD_NOT_VERIFY"}
_RANK = {"PASS": 4, "PARTIAL": 3, "COULD_NOT_VERIFY": 2, "GAP": 1, "NOT_APPLICABLE": 0}

_EXPECTED = ["home", "privacy notice", "cookie policy", "grievance contact", "rights page"]


def _page_kinds(pages: list[dict]) -> list[str]:
    """Which of the expected obligation-surface pages we actually reached."""
    reached = []
    if pages:
        reached.append("home")
    joined = " ".join((p.get("url", "") + " " + ("policy" if p.get("is_policy") else "")) for p in pages).lower()
    if "policy" in joined or "privacy" in joined:
        reached.append("privacy notice")
    if "cookie" in joined:
        reached.append("cookie policy")
    if "grievance" in joined or "contact" in joined or "nodal" in joined:
        reached.append("grievance contact")
    if "rights" in joined or "data-request" in joined or "dsr" in joined:
        reached.append("rights page")
    return reached


def ui_report(rep, crawl: dict, org: str | None = None) -> dict:
    pages = crawl.get("pages", [])
    # 47 verdicts: a duty NOT in findings is Compliant; a flagged duty carries its own verdict.
    by_id = {}
    for f in rep.findings:
        m = getattr(f, "id", "") or ""
        num = "".join(ch for ch in m.split("-")[0] if ch.isdigit())
        if num:
            by_id[int(num)] = f
    verdict_of = {}                                   # duty id -> our verdict
    quote_of, fix_of, page_of = {}, {}, {}
    for cid in range(1, 48):
        f = by_id.get(cid)
        if f is None:
            verdict_of[cid] = "Compliant"
        else:
            verdict_of[cid] = f.verdict
            ev = getattr(f, "evidence", None)
            quote_of[cid] = getattr(ev, "policy_quote", "") if ev else ""
            page_of[cid] = getattr(ev, "policy_source_url", "") if ev else ""
            fix_of[cid] = getattr(f, "recommendation", "") or ""

    checks = []
    for uid, title, citation, duties in UI_CHECKS:
        uverds = [_V.get(verdict_of.get(d, "Not disclosed"), "GAP") for d in duties]
        best = max(uverds, key=lambda v: _RANK.get(v, 0))
        # evidence from the strongest duty that has a quote
        ev, evpage, fix = "", "", ""
        for d in sorted(duties, key=lambda d: -_RANK.get(_V.get(verdict_of.get(d, ""), "GAP"), 0)):
            if quote_of.get(d):
                ev, evpage = quote_of[d], page_of.get(d, "")
                break
        if best in ("GAP", "PARTIAL"):
            fix = next((fix_of[d] for d in duties if fix_of.get(d)), "")
        if best == "PASS":
            finding = "Addressed on the pages we read."
        elif best == "COULD_NOT_VERIFY":
            finding = "This lives on a control we can't verify externally, so it isn't scored against the site."
        elif best == "PARTIAL":
            finding = "Partly addressed — disclosed but incomplete or vague."
        else:
            finding = "We couldn't find this on the pages we read. Under " + citation + ", it is expected."
        checks.append({"id": uid, "title": title, "citation": citation, "verdict": best,
                       "evidence": ev or None, "evidence_page": evpage or None,
                       "finding": finding, "fix": fix or None})

    # risk block
    grade = rep.overall.grade
    level = "Low" if grade in ("A", "B") else "Medium" if grade == "C" else "High"
    chrome = {"navigation", "menu", "footer"}
    collects = sorted({c for p in pages for c in (p.get("data_collected") or []) if c not in chrome})[:8]
    adeq = rep.overall.adequacy
    summary = (f"On the pages we read, this service scores {int(adeq * 100)}% on the DPDP disclosure "
               f"surface (grade {grade}). " +
               ("It names specific data categories it collects." if collects else
                "We could not confirm exactly what personal data it collects from the pages read."))
    rights = ("Your most useful levers here are the right to access a summary of your data (Act s.11) "
              "and to seek correction or erasure (Act s.12).")
    baseline = ("Judged against what a service of this kind would reasonably disclose — guidance, not a legal ruling.")

    reached = _page_kinds(pages)
    unreached = [{"page": p, "reason": "not linked from or reachable on the pages crawled"}
                 for p in _EXPECTED if p not in reached]

    cov = getattr(rep, "coverage", {}) or {}
    data_categories = cov.get("data_categories", []) or []
    enforceability = cov.get("enforceability", {}) or {}
    # Exposure findings (leaked records, misconfig) are higher-severity than a missing clause --
    # surface them so a Critical public-data leak is visible on the Scanner UI.
    exposure = [{"id": e.get("id"), "severity": e.get("severity"),
                 "detail": e.get("detail"), "found": e.get("found", []),
                 "provision": e.get("provision", "")} for e in (getattr(rep, "exposure", []) or [])]

    # ---- Full 47-duty breakdown (compliant / non-compliant + severity) for the results page ----
    from .catalog import CHECKS as _CHECKS
    from urllib.parse import urlparse as _urlparse
    try:
        from .it_act import _MAP as _ITMAP        # the duty ids enforceable today under the IT Act / SPDI
    except Exception:
        _ITMAP = {}
    _CAT = {c["id"]: c for c in _CHECKS}

    def _anchor(c):
        a = c.get("dpdp_anchor") or {}
        parts = []
        if a.get("rule"):
            parts.append(a["rule"])
        if a.get("act_section"):
            parts.append("Act " + a["act_section"])
        return "; ".join(parts)

    duties = []
    for cid in range(1, 48):
        c = _CAT.get(cid, {})
        f = by_id.get(cid)
        v = verdict_of.get(cid, "Not disclosed")
        duties.append({
            "id": cid,
            "requirement": c.get("requirement", getattr(f, "title", "") if f else ""),
            "category": c.get("category", ""),
            "anchor": _anchor(c),
            "mandatory": bool(c.get("mandatory")),
            "in_force": bool(c.get("in_force")),
            "it_act": cid in _ITMAP,                       # enforceable TODAY under IT Act / SPDI Rules
            "verdict": v,
            "compliant": v == "Compliant",
            "severity": (getattr(f, "severity", "") if f else ""),
        })

    # ---- Site map: a real link graph (nodes = crawled pages, edges = links between them) ----
    _urls = [p.get("url", "") for p in pages if p.get("url")]
    _ispolicy = {p.get("url"): bool(p.get("is_policy")) for p in pages}
    _base = ((getattr(rep, "url", "") or "") or (_urls[0] if _urls else "")).rstrip("/")

    def _host(u):
        return _urlparse(u).netloc.lower()

    def _label(u):
        pth = _urlparse(u).path.rstrip("/")
        return pth if pth else "/"
    _cap = _urls[:260]                                   # cap graph nodes so the SVG stays renderable
    _idx = {u: i for i, u in enumerate(_cap)}
    # The subdomain inventory is the FULL real set: passive discovery (CT logs) UNION every host we
    # actually crawled -- not merely the hosts of the capped graph nodes. So the count reflects the
    # site's real breadth even when the force-graph only renders a sample of the pages.
    _node_hosts = {_host(u) for u in _cap if _host(u)}
    _all_subs = sorted(set(crawl.get("subdomains") or []) | {_host(u) for u in _urls if _host(u)})
    nodes = []
    for u in _cap:
        nodes.append({"id": _idx[u], "label": _label(u), "host": _host(u),
                      "home": (u.rstrip("/") == _base) or (_urlparse(u).path in ("", "/")),
                      "policy": _ispolicy.get(u, False)})
    g_edges = []
    for s, t in (crawl.get("edges") or []):
        if s in _idx and t in _idx:
            g_edges.append([_idx[s], _idx[t]])
    sitemap = {
        "count": len(_urls),
        "n_pages": cov.get("n_pages", len(_urls)),
        "crawled_total": len(_urls),                     # pages actually crawled
        "shown": len(_cap),                              # pages drawn in the graph (sampled if capped)
        "subdomains": _all_subs,
        "n_subdomains": len(_all_subs),
        "node_hosts": sorted(_node_hosts),               # subdomains represented in the graph itself
        "nodes": nodes,
        "edges": g_edges[:1500],
    }

    # ---- Behaviour: third-party trackers + cookies set before any consent, categorised ----
    # Cookies are split into strictly-necessary (session/security/CMP, lawful before consent) and
    # consent-requiring (analytics/advertising/social). The headline figure is the number of
    # consent-requiring cookies set BEFORE the visitor chose, and we credit a site that offers a
    # banner while still flagging trackers that fire before the choice.
    from collections import Counter as _Counter
    from .crawler import (tracker_category as _tcat, _TRACKER_DOMAINS as _TD,
                          cookie_necessity as _necessity, is_cmp_cookie as _is_cmp)
    _trk = getattr(rep, "tracker_inventory", None) or []
    _ck = getattr(rep, "cookie_inventory", None) or []

    def _cookie_cat(c):
        dom = (c.get("domain") or "").lstrip(".").lower()
        for d, (nm, _cc) in _TD.items():
            if dom.endswith(d):
                return _tcat(nm)
        return "Third-party" if c.get("third_party") else "Functional"
    trackers = [{"name": (t.get("name") or t.get("domain") or "tracker"),
                 "category": (t.get("category") or _tcat(t.get("name", ""))),
                 "jurisdiction": (t.get("country") or "")} for t in _trk if isinstance(t, dict)]
    cookies_list = []
    for c in _ck:
        if not isinstance(c, dict):
            continue
        _nm = c.get("name", "")
        _tp = bool(c.get("third_party"))
        _need = _necessity(_nm, c.get("domain", ""), _tp)
        cookies_list.append({"name": _nm, "domain": (c.get("domain") or "").lstrip("."),
                             "category": _cookie_cat(c), "party": ("third-party" if _tp else "first-party"),
                             "essential": (_need == "necessary")})
    _catc = _Counter(t["category"] for t in trackers)
    # A consent banner is present if the CMP left its own cookie or a crawled page showed a notice.
    _banner = any(_is_cmp(c.get("name", "")) for c in _ck if isinstance(c, dict)) \
        or any(p.get("consent_banner") for p in pages)
    _pre = [c for c in _ck if isinstance(c, dict) and c.get("before_consent")]
    _pre_nonessential = [c for c in _pre if _necessity(c.get("name", ""), c.get("domain", ""),
                                                        bool(c.get("third_party"))) == "consent_required"]
    _n_necessary = sum(1 for c in cookies_list if c["essential"])
    # Reject-verification probe (homepage): did an explicit reject actually remove the trackers?
    _cp = (crawl.get("consent_probe") or {}) if isinstance(crawl, dict) else {}
    _reject_tested = bool(_cp.get("reject_control_found"))
    _persist = _cp.get("persisted_after_reject") or []
    _removed = _cp.get("removed_after_reject") or []
    _reject_honoured = (len(_persist) == 0) if _reject_tested else None
    behaviour = {
        "n_trackers": len(trackers),
        "trackers": trackers[:40],
        "tracker_categories": [{"name": k, "count": v} for k, v in _catc.most_common()],
        "n_cookies": len(_ck),
        "n_cookies_necessary": _n_necessary,
        "n_cookies_pre_consent": len(_pre),                       # all cookies before any choice (incl. necessary)
        "n_nonessential_pre_consent": len(_pre_nonessential),     # the legally salient figure
        "consent_banner_present": bool(_banner) or bool(_cp.get("banner_detected")),
        "reject_tested": _reject_tested,                          # a reject control was found and clicked
        "reject_honoured": _reject_honoured,                      # True = all non-essential removed; False = some persisted
        "n_persist_after_reject": len(_persist),
        "n_removed_after_reject": len(_removed),
        "cookies": cookies_list[:120],
    }

    return {
        "risk": {"level": level, "summary": summary, "collects": collects,
                 "baseline": baseline, "rights": rights,
                 "data_categories": data_categories},
        "checks": checks,
        "exposure": exposure,
        "enforceability": enforceability,
        "coverage": {"reached": reached, "unreached": unreached,
                     "data_categories": data_categories},
        "grade": grade, "adequacy": adeq, "org": org or rep.site if hasattr(rep, "site") else org,
        "duties": duties, "sitemap": sitemap, "behaviour": behaviour,
    }
