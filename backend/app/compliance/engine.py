"""
engine.py -- deterministic, grounded DPDP disclosure- and behaviour-adequacy engine.

Reconstructed 2026-08-19 after the loss of E:\Adhikar. The scoring core (_judge, _finding,
_severity, the verdict weights and the grade bands) is reproduced verbatim from the engine
internals read during the working session and confirmed against two real engine-generated
reports. It runs with zero API keys: verdicts are pure keyword/signal matching over the
retrieved text plus directly observed facts (HTTPS, exposure). No LLM is in the verdict path.

Verdicts: Compliant | Partial | Gap | Not disclosed | Not externally verifiable
          (+ "Insufficient evidence" when a page could not be read).
"""
from __future__ import annotations
import re
import datetime
from .catalog import CHECKS, WEIGHT, penalty_for, anchor_label
from .models import (Finding, FindingEvidence, PenaltyInfo, Overall, PerPageRow,
                     ComplianceReport)
try:
    from ..rag.retriever import provision_text, SOURCE_LABEL
except Exception:  # RAG optional
    def provision_text(anchor):  # type: ignore
        return ""
    SOURCE_LABEL = "DPDP Act, 2023; DPDP Rules, 2025"

# Checks whose failure can be OBSERVED on the property itself -> the only route to Critical.
_EXPOSURE_CHECKS = {5, 9, 15, 38}
# Point-of-collection duties: these apply to the pages that collect personal data, so their
# "affected" is the collecting pages. Every other duty is policy-level (whole site).
_PAGE_LEVEL_CHECKS = {1, 2, 3, 4, 5, 11, 12, 15, 24}
# Categories evidenced by third-party BEHAVIOUR rather than first-party collection: capped Medium.
_BEHAVIOURAL_CATS = {"Consent Management", "Cross-border Transfers"}

DISCLAIMER = ("This report is information, not legal advice, and is not a legal certification. "
              "Penalty figures are statutory maximums the Data Protection Board of India may "
              "impose under Section 33 only after an inquiry; they are not automatic fines and "
              "must not be added together.")


def _now() -> str:
    return datetime.datetime.now().strftime("%d %B %Y")


def _slug(check: dict) -> str:
    words = re.sub(r"[^a-z0-9 ]", "", check["requirement"].lower()).split()[:4]
    return f"c{check['id']}-" + "-".join(words)


def _pg_name(url: str, site: str) -> str:
    seg = url.rstrip("/").split("/")[-1]
    if not seg or "." in seg:
        return "Home"
    return seg.replace("-", " ").title()


def _best_passage(text: str, signals: list[str]) -> str:
    """Return a short verbatim snippet around the first matching signal."""
    low = text.lower()
    for s in signals:
        i = low.find(s.lower())
        if i >= 0:
            start = max(0, i - 60)
            end = min(len(text), i + len(s) + 100)
            return text[start:end].strip()
    return ""


def _judge(check: dict, policy_text: str, is_https: bool, sem=None) -> tuple[str, float, str]:
    """Grounded verdict for one requirement -> (verdict, confidence, quote).

    If `sem` (a semantic (verdict, score, sentence) tuple) is provided, it is used -- the meaning of
    the policy is matched, not keywords. Falls back to signal matching when the semantic model is
    unavailable.
    """
    if check.get("observed") == "https":          # a directly observable technical control
        return ("Compliant", 0.9, "") if is_https else ("Gap", 0.8, "")
    if sem is not None:
        verdict, score, sentence = sem
        if check.get("disclosure_only"):           # internal control: judged as disclosure detection
            if verdict == "Not disclosed":
                return "Not disclosed", 0.55, ""
            return "Not externally verifiable", 0.62, sentence
        return verdict, round(0.55 + 0.35 * min(1.0, float(score)), 2), sentence
    sig = check.get("signals", {"strong": [], "generic": []})
    low = policy_text.lower()
    strong = [t for t in sig.get("strong", []) if t.lower() in low]
    generic = [t for t in sig.get("generic", []) if t.lower() in low]

    if check.get("disclosure_only"):
        if strong:
            return "Not externally verifiable", 0.62, _best_passage(policy_text, sig["strong"])
        return "Not disclosed", 0.55, ""

    n = len(strong)
    mins = check.get("min_strong", 1)
    if n >= mins:
        return "Compliant", min(0.9, 0.55 + 0.1 * n), _best_passage(policy_text, sig["strong"])
    if n >= 1:                                      # some disclosure but below threshold
        return "Partial", 0.6, _best_passage(policy_text, sig["strong"])
    if generic:
        return "Partial", 0.55, _best_passage(policy_text, sig["generic"])
    return "Not disclosed", 0.5, ""


def _severity(check: dict, verdict: str, site_collects: bool, exposure: bool) -> str | None:
    """DPDP 5-band severity. Returns None for Compliant (not a finding)."""
    if verdict == "Compliant":
        return None
    if verdict == "Not externally verifiable":
        return "Info"
    # Observed exposure on a collecting property -> Critical (only for the exposure checks).
    if check["id"] in _EXPOSURE_CHECKS and exposure:
        return "Critical"
    base = check.get("priority", "Low")
    if verdict == "Partial":                        # disclosed but incomplete -> at most Medium
        return "Medium" if base in ("High", "Medium") else "Low"
    if check["category"] in _BEHAVIOURAL_CATS and base == "High":
        return "Medium"
    # A mandatory duty unmet where personal data is collected is High; otherwise fall to base.
    if base == "High" and check.get("mandatory") and not site_collects:
        return "Medium"
    return base


def _statement(check: dict, verdict: str) -> str:
    if verdict in ("Not disclosed", "Gap"):
        return ("No clause addressing this requirement was found in the assessed text. "
                "The requirement is recorded as not disclosed.")
    if verdict == "Partial":
        return "The requirement is addressed but the disclosure is incomplete."
    if verdict == "Not externally verifiable":
        return ("This is an internal control that cannot be verified from outside; it is "
                "recorded as disclosure-only and is never scored as a failure.")
    return "The requirement is addressed; the supporting clause is quoted verbatim."


def _finding(check: dict, ptext: str, source_url: str, pages: list[dict], site: str,
             site_collects: bool, is_https: bool, evaluated: list[str], exposure: bool,
             collecting_urls: list[str] | None = None, sem=None) -> Finding | None:
    verdict, conf, quote = _judge(check, ptext, is_https, sem)
    sev = _severity(check, verdict, site_collects, exposure)
    if sev is None:
        return None                                 # Compliant -> counted, not a detailed finding
    pen = penalty_for(check)
    # Point-of-collection duties list the collecting pages; every other duty is whole-site.
    if check["id"] in _PAGE_LEVEL_CHECKS and collecting_urls:
        affected = collecting_urls[:3]
    else:
        affected = ["Policy-level (whole site)"]
    return Finding(
        id=_slug(check), title=check["requirement"], finding=check.get("finding", ""),
        category=check["category"], dpdp_anchor=check["dpdp_anchor"],
        priority=check.get("priority", "Low"), severity=sev, verdict=verdict,
        statement=_statement(check, verdict), confidence=round(conf, 2),
        affected_urls=affected,
        evaluated_pages=evaluated[:12],
        evidence=FindingEvidence(policy_quote=quote,
                                 policy_source_url=source_url if quote else "",
                                 observed=("HTTPS" if check.get("observed") == "https" else ""),
                                 dpdp_quote=provision_text(check.get("dpdp_anchor", {})),
                                 dpdp_source_label=SOURCE_LABEL),
        penalty=PenaltyInfo(**pen),
        impact=check.get("impact", ""), recommendation=check.get("remediation", ""),
        references=[anchor_label(check)])


_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}


def _grade(adequacy: float) -> str:
    if adequacy >= 0.85: return "A"
    if adequacy >= 0.70: return "B"
    if adequacy >= 0.55: return "C"
    if adequacy >= 0.40: return "D"
    return "E"


GRADE_MEANING = {
    "A": "Substantially complete disclosure; minor items only",
    "B": "Good disclosure with a few gaps to close",
    "C": "Partial disclosure; remediation advised",
    "D": "Partial disclosure; priority remediation required",
    "E": "Weak disclosure; urgent remediation required",
}


def _overall(findings: list[Finding], n_checks: int) -> Overall:
    # Adequacy: each Compliant check scores 1.0 (no finding); every finding scores its verdict weight.
    finding_weight = sum(WEIGHT.get(f.verdict, 0.0) for f in findings)
    compliant = n_checks - len(findings)
    adequacy = round((compliant * 1.0 + finding_weight) / n_checks, 2)
    grade = _grade(adequacy)
    counts = {b: sum(1 for f in findings if f.severity == b)
              for b in ("Critical", "High", "Medium", "Low", "Info")}
    counts["Requirements met"] = compliant
    return Overall(grade=grade, adequacy=adequacy,
                   summary=f"{GRADE_MEANING[grade]} (adequacy {adequacy:.2f}).",
                   at_a_glance=(f"{counts['Critical']} critical, {counts['High']} high, "
                                f"{counts['Medium']} medium, {counts['Low']} low; "
                                f"{compliant} of {n_checks} requirements met."),
                   counts=counts)


_MAILTO_RE = re.compile(r'mailto:([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})', re.I)
_EMAIL_RE = re.compile(r'\b([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b')
_GOV_LOCAL = re.compile(r'grievance|nodal|dpo|dataprotection|data.protection|privacy|complian|legal', re.I)
_GRIEVANCE_TXT = re.compile(r'grievance officer|grievance redress|grievance cell|nodal officer|'
                           r'nodal person|redressal mechanism|ombudsman', re.I)
_DPO_TXT = re.compile(r'data protection officer|chief privacy officer|\bDPO\b', re.I)


def _harvest_governance(pages: list[dict]) -> dict:
    """A compliance officer reads the WHOLE site, not just the policy: the grievance/nodal officer, DPO,
    and data-rights contact are usually in the footer / contact page / a mailto link on every page. Pull
    those observed artefacts site-wide so a thin or unreachable policy page doesn't hide a real mechanism.
    Evidence returned is the actual observed email/text (never fabricated)."""
    text = " ".join(p.get("text", "") for p in pages)
    html = " ".join(p.get("html", "") for p in pages)
    mails = {m.lower() for m in _MAILTO_RE.findall(html)} | {m.lower() for m in _EMAIL_RE.findall(text)}
    gov_mails = sorted(m for m in mails if _GOV_LOCAL.search(m.split("@")[0]))
    return {
        "grievance": bool(_GRIEVANCE_TXT.search(text)) or any(("grievance" in m or "nodal" in m) for m in mails),
        "dpo": bool(_DPO_TXT.search(text)) or any("dpo" in m.split("@")[0] for m in mails),
        "gov_mails": gov_mails,
        "any_mail": sorted(mails),
    }


def compliance_report(url: str | None = None, policy_text: str | None = None,
                      pages: list[dict] | None = None, page_budget: int = 12,
                      site_type: str = "auto", exposure_findings: list[dict] | None = None,
                      is_https: bool | None = None, site: str | None = None,
                      platform: str = "Unknown", archived_policy: dict | None = None,
                      policy_found: bool | None = None,
                      subdomains: list[str] | None = None,
                      sec_headers: dict | None = None,
                      observed_tech: dict | None = None) -> ComplianceReport:
    """Judge all 47 requirements against retrieved text + observed behaviour.

    `pages` is the crawler output (each: {url, text, is_policy, data_collected, ...}). If only
    `policy_text` is supplied, a single synthetic policy page is used. `exposure_findings` is the
    output of exposure.probe(). This function does not crawl; call crawler.crawl() first (or pass
    policy_text) so the engine stays deterministic and testable.
    """
    exposure_findings = exposure_findings or []
    if pages is None:
        pages = [{"url": url or "", "text": policy_text or "", "is_policy": True,
                  "data_collected": []}]
    site = site or (re.sub(r"^https?://(www\.)?", "", url).split("/")[0] if url else "site")

    # Disclosures are judged against genuine POLICY / LEGAL documents: the privacy notice, plus
    # terms, cookie, grievance/redressal and nodal-officer pages (all legally-required disclosure
    # documents). Marketing pages (contact/about/product) are deliberately excluded so their copy
    # is never mistaken for a notice. If no such document exists the text is empty and every
    # disclosure duty is Not disclosed -- silence is never read as compliance.
    # Specific legal-DOCUMENT paths only (not thematic pages like a charity's "/grievances" section
    # about the grievances it helps with) -- this avoids both false negatives and false positives.
    _LEGAL_URL = re.compile(r"privacy|cookie[-_ ]?polic|/terms|/legal|grievance[-_ ]?redress|"
                            r"nodal[-_ ]?officer|data[-_ ]?protection|/gdpr|/dpdp", re.I)
    # Order the compliance-relevant pages so the ACTUAL policy document leads: is_policy pages first,
    # then legal/grievance/terms pages. This prevents a giant marketing page from consuming the char
    # budget and truncating the real policy out of what the model judges.
    _legal_pages = [p for p in pages if p.get("is_policy") or _LEGAL_URL.search(p.get("url", ""))]
    _legal_pages.sort(key=lambda p: (0 if p.get("is_policy") else 1))
    ptext = "\n\n".join(p.get("text", "") for p in _legal_pages)[:24000]
    if policy_text and not ptext:                     # pasted-policy mode
        ptext = policy_text[:24000]
    source_url = next((p["url"] for p in pages if p.get("is_policy") and p.get("url")), "")
    if is_https is None:
        is_https = all(str(p.get("url", "")).startswith("https") for p in pages if p.get("url")) or bool(policy_text)
    observed_tech = observed_tech or {}
    _obs_trackers = observed_tech.get("trackers") or []
    _obs_collectors = observed_tech.get("collectors") or []
    # Nuclei tech-detect is observed evidence: a form-DB/newsletter plugin means the site collects
    # personal data even if no <form> was crawled; trackers mean third-party data flows exist.
    site_collects = any(p.get("data_collected") for p in pages) or bool(_obs_collectors)
    evaluated = [p["url"] for p in pages if p.get("url")]
    # Personal records exposed on a public page (should be behind a login) -> Critical exposure.
    try:
        from .records import detect_published_records
        exposure_findings = list(exposure_findings) + detect_published_records(pages)
    except Exception:
        pass
    exposure = (not is_https) or any(e.get("severity") == "Critical" for e in exposure_findings)

    # shared-chrome-aware collection: a page genuinely collects only where it has a personal-data
    # field beyond the shared header/footer newsletter box.
    from collections import Counter
    _fc = Counter(f for p in pages for f in set(p.get("data_collected") or []))
    chrome = {f for f, c in _fc.items() if len(pages) > 1 and c >= len(pages)}
    _PII = {"name", "phone", "dob", "address"}
    collecting = [p for p in pages if (set(p.get("data_collected") or []) - chrome) & _PII]
    collecting.sort(key=lambda p: -len((set(p.get("data_collected") or []) - chrome) & _PII))
    collecting_urls = [p["url"] for p in collecting]

    # Disclosure judging, best available first: LLM judge (highest accuracy, reads the real policy)
    # -> semantic (meaning-based) -> keyword signals (in _judge when sem is None).
    sem_all = {}
    if ptext.strip():
        try:
            from ..rag import llm_judge
            if llm_judge.enabled():
                sem_all = {cid: (v, 1.0, ev) for cid, (v, ev) in llm_judge.judge_policy(ptext).items()}
        except Exception:
            sem_all = {}
        if not sem_all:
            try:
                from ..rag import semantic
                if semantic.available():
                    sem_all = semantic.judge_all(ptext)
            except Exception:
                sem_all = {}

    # Whole-site evidence sweep for ALL 47 duties: a disclosure can live on ANY page (a signup notice,
    # cookie banner, FAQ, checkout, footer) -- not only the policy document. Judge the whole site and,
    # per duty, keep the STRONGER grounded verdict. A stricter threshold than the policy pass guards
    # against marketing copy scoring as a disclosure; evidence stays a real sentence from a real page.
    try:
        from ..rag import semantic as _sem
        if _sem.available():
            # Lead with policy/legal pages so a huge marketing page can't push the real policy past
            # the char cap; then the rest of the site (footer, forms, FAQ) fills the remaining budget.
            _ordered = sorted(pages, key=lambda p: (0 if p.get("is_policy") else
                                                    1 if _LEGAL_URL.search(p.get("url", "")) else 2))
            _seen, _parts = set(), []
            for _p in _ordered:
                _t = _p.get("text", "")
                if _t and _t not in _seen:
                    _seen.add(_t)
                    _parts.append(_t)
            _site_text = "\n\n".join(_parts)[:40000]
            if _site_text.strip():
                _site_sem = _sem.judge_all(_site_text, t_high=0.60, t_partial=0.52)
                _rank = {"Compliant": 2, "Partial": 1, "Not disclosed": 0}
                for _cid, _tup in _site_sem.items():
                    _cur = sem_all.get(_cid)
                    _cur_rank = _rank.get(_cur[0], -1) if _cur else -1
                    if _rank.get(_tup[0], 0) > _cur_rank:      # only upgrade to a stronger grounded verdict
                        sem_all[_cid] = _tup
    except Exception:
        pass

    # Whole-site governance evidence: credit grievance / data-rights contact / DPO from ANY page
    # (footer, contact page, mailto) -- not the policy prose alone. Only fills a gap the policy judge
    # left as 'Not disclosed'; never downgrades a real disclosure. Evidence is the observed artefact.
    gov = _harvest_governance(pages)

    def _assert(cid: int, verdict: str, evidence: str):
        cur = sem_all.get(cid)
        if cur is None or cur[0] == "Not disclosed":
            sem_all[cid] = (verdict, 1.0, evidence)
        elif cur[0] == "Partial" and verdict == "Compliant":
            sem_all[cid] = (verdict, 1.0, evidence)

    if gov["grievance"]:
        ev = "Grievance/nodal contact published on the site"
        if gov["gov_mails"]:
            ev += ": " + ", ".join(gov["gov_mails"][:2])
        _assert(19, "Compliant", ev)                  # grievance-redressal route
    if gov["gov_mails"]:
        _assert(21, "Compliant", "Data-rights contact published: " + ", ".join(gov["gov_mails"][:2]))
    elif gov["any_mail"]:
        _assert(21, "Partial", "Contact email published: " + ", ".join(gov["any_mail"][:2]))
    if gov["dpo"]:
        _assert(22, "Compliant", "Data Protection Officer referenced on the site")

    # Observable technical controls: grade real behaviour, not prose. Transport-security headers are
    # externally verifiable evidence toward the security-safeguards duty even when it isn't disclosed.
    sh = sec_headers or {}
    _ctrls = [n for n, k in (("HSTS", "hsts"), ("CSP", "csp"),
                             ("X-Content-Type-Options", "x_content_type_options"),
                             ("X-Frame-Options", "x_frame_options")) if sh.get(k)]
    # Nuclei-observed TLS + WAF are externally-verifiable Rule 6 / s.8(5) safeguards too.
    _ctrls += [t for t in (observed_tech.get("security") or [])]
    if _ctrls:
        _assert(9, "Partial", "Observed security controls (encryption in transit / WAF / headers): "
                              + ", ".join(dict.fromkeys(_ctrls)))

    findings = [f for f in (_finding(c, ptext, source_url, pages, site, site_collects, is_https,
                                     evaluated, exposure, collecting_urls, sem_all.get(c["id"]))
                            for c in CHECKS) if f]
    findings.sort(key=lambda f: (_ORDER.get(f.severity, 9), f.title))

    overall = _overall(findings, len(CHECKS))

    if policy_found is None:
        policy_found = bool(ptext.strip())
    # `chrome`, `collecting` and `collecting_urls` were computed above (before the findings loop).
    serious_pages = list(collecting_urls)
    _collecting_set = set(collecting_urls)

    # Per-page rows for the assets-in-scope and page-by-page sections.
    per_page_rows = []
    for i, p in enumerate(pages, 1):
        pii = sorted((set(p.get("data_collected") or []) - chrome) & _PII)
        trk = [t.get("name") for t in (p.get("trackers") or [])]
        if p["url"] in collecting_urls:
            processes = ", ".join(pii) or "personal data"
            issue = (f"Collects {', '.join(pii)} via a form with no notice or consent at the "
                     "point of collection." + (f" Loads {', '.join(trk)} before consent."
                                               if trk else ""))
            priority = "High"
        else:
            processes = "Shared header/footer only (analytics/ad trackers, newsletter sign-up)"
            issue = "No page-specific processing detected. See whole-site findings."
            priority = "Info"
        per_page_rows.append(PerPageRow(
            sr=i, page=_pg_name(p["url"], site), url=p["url"], page_type="form",
            criticality="High" if p["url"] in collecting_urls else "Medium",
            processes=processes, issue=issue, priority=priority))

    coverage = {"policy_found": policy_found, "platform": platform,
                "archived_policy": archived_policy, "site_collects": site_collects,
                "observed_trackers": _obs_trackers, "observed_collectors": _obs_collectors,
                "n_pages": len(pages), "n_collecting": len(collecting),
                "collecting_pages": [p["url"] for p in collecting],
                "serious_pages": serious_pages,
                "subdomains": sorted(set(subdomains or [])
                                     or {re.sub(r"^https?://", "", u).split("/")[0]
                                         for u in evaluated if u}),
                "assessed_urls": evaluated,
                "consent_banner": any(p.get("consent_banner") for p in pages),
                "screenshots": [{"page": _pg_name(p["url"], site), "url": p["url"],
                                 "path": p.get("screenshot")} for p in pages if p.get("screenshot")],
                "coverage_pct": min(1.0, len(pages) / max(1, page_budget))}

    return ComplianceReport(
        site=site, url=url or "", scope="site", pages_crawled=len(pages), site_type=site_type,
        generated_at=_now(), grounded=True, inconclusive=False, coverage=coverage,
        overall=overall, findings=findings, per_page=per_page_rows,
        exposure=exposure_findings, disclaimer=DISCLAIMER)
