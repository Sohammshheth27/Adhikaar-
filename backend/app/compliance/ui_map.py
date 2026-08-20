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
    return {
        "risk": {"level": level, "summary": summary, "collects": collects,
                 "baseline": baseline, "rights": rights},
        "checks": checks,
        "coverage": {"reached": reached, "unreached": unreached},
        "grade": grade, "adequacy": adeq, "org": org or rep.site if hasattr(rep, "site") else org,
    }
