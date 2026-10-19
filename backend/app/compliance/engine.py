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


import os as _os
_VERIFY_DISABLED = _os.environ.get("ADHIKAAR_VERIFY", "1") == "0"


def _grounded_judge(text: str, signals: dict) -> dict:
    """Stage-2 verified disclosure judge -> {cid: (verdict, score, evidence)}.

    Uses the routed two-stage verifier (verify.judge_all_verified: deterministic crawl signals for
    existence duties, an assertion gate for disclosure lists, and NLI ENTAILMENT for propositional
    claims) -- the layer that rejects topically-similar-but-non-committal matches a cosine threshold
    would over-credit. Falls back to the Stage-1-only semantic judge when the NLI cross-encoder is
    unavailable (or ADHIKAAR_VERIFY=0), so the engine always runs. The 4-tuple from the verifier is
    reduced to the (verdict, score, evidence) 3-tuple the engine's _judge consumes."""
    if not text.strip():
        return {}
    if not _VERIFY_DISABLED:
        try:
            from ..rag import verify as _V
            if _V.nli_available():
                raw = _V.judge_all_verified(text, signals)
                return {cid: (v, s, ev) for cid, (v, s, ev, _r) in raw.items()}
        except Exception:
            pass
    try:
        from ..rag import semantic as _S
        if _S.available():
            return _S.judge_all(text)
    except Exception:
        pass
    return {}


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
    # The institution's OWN notice counts only if it lives on the PRIMARY host (the scanned site or
    # its www variant) -- a privacy policy that exists only on a separate, third-party-powered
    # subdomain (e.g. an alumni portal running a vendor's SaaS template) does not discharge the
    # Data Fiduciary's notice duty for the main property, so it is recorded separately, not judged.
    def _host(u):
        return re.sub(r"^https?://", "", str(u or "")).split("/")[0].lower()
    _base = re.sub(r"^www\.", "", (site or _host(url)).lower())
    _primary_hosts = {_base, "www." + _base} if _base else set()
    _own = lambda p: (not _primary_hosts) or _host(p.get("url", "")) in _primary_hosts
    _legal_pages = [p for p in pages if _own(p)
                    and (p.get("is_policy") or _LEGAL_URL.search(p.get("url", "")))]
    _legal_pages.sort(key=lambda p: (0 if p.get("is_policy") else 1))
    # Cap the policy text the judge sees. Must be large enough to hold a full long policy (razorpay's
    # is ~28k chars) plus its legal/grievance pages, or duties addressed late in the policy are
    # truncated away and wrongly scored 'Not disclosed'.
    ptext = "\n\n".join(p.get("text", "") for p in _legal_pages)[:60000]
    if policy_text and not ptext:                     # pasted-policy mode
        ptext = policy_text[:60000]
    source_url = next((p["url"] for p in _legal_pages if p.get("is_policy") and p.get("url")), "")
    # policies found only on non-primary (e.g. third-party-powered) subdomains -- observed, not counted
    _offsite_policies = [{"url": p.get("url", ""), "host": _host(p.get("url", ""))}
                         for p in pages if p.get("is_policy") and not _own(p)]
    if is_https is None:
        # The duty is "the SITE serves over HTTPS" -- judge the primary host's own pages, not every
        # crawled URL across all subdomains (a single http link on a third-party subdomain must not
        # flip a site-level transport-security verdict, nor spuriously trip the exposure penalty).
        _own_urls = [str(p.get("url", "")) for p in pages if p.get("url") and _own(p)]
        _https_urls = _own_urls or [str(p.get("url", "")) for p in pages if p.get("url")]
        is_https = (bool(_https_urls) and all(u.startswith("https") for u in _https_urls)) or bool(policy_text)
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

    # Structural crawl signals for the verified judge's existence-duty lane (#33 privacy policy,
    # #34 cookie policy, #35 terms, #37 contact, #38 HTTPS) -- decided from observed facts, not text.
    _all_urls = [p.get("url", "") for p in pages if p.get("url")]
    try:
        from ..rag import verify as _V
        signals = _V.structural_signals(ptext, _all_urls, " ".join(p.get("text", "") for p in pages))
    except Exception:
        signals = {}
    signals["is_https"] = is_https

    # Disclosure judging over the WHOLE SITE in ONE grounded pass: a disclosure can live on ANY page
    # (a signup notice, cookie banner, FAQ, checkout, footer), not only the policy document. We lead
    # with the policy/legal pages so a huge marketing page can't push the real policy past the char
    # cap, then let the rest of the site fill the remaining budget. The grounded judge (the verified
    # NLI two-stage judge, or the Stage-1 semantic fallback) is strict on its own -- the assertion
    # gate + entailment stop marketing copy scoring as a disclosure -- so a single whole-site pass
    # gives both recall and precision, at half the NLI cost of the old policy-then-site two passes.
    _ordered = sorted(pages, key=lambda p: (0 if p.get("is_policy") else
                                            1 if _LEGAL_URL.search(p.get("url", "")) else 2))
    _seen, _parts = set(), []
    for _p in _ordered:
        _t = _p.get("text", "")
        if _t and _t not in _seen:
            _seen.add(_t)
            _parts.append(_t)
    _site_text = "\n\n".join(_parts)[:40000]
    if not _site_text.strip() and policy_text:          # pasted-policy mode
        _site_text = policy_text[:40000]

    sem_all = _grounded_judge(_site_text, signals) if _site_text.strip() else {}

    # Deployed primary judge (gated on ADHIKAAR_LLM_JUDGE + an API key): the routed RAG + LLM + NLI
    # pipeline validated against the human gold set (Cohen's kappa ~0.56, 4-class; ~0.69, 3-class;
    # gap-screening F1 ~0.85). The LLM (fed a semantic-retrieval digest of the whole policy) is the
    # PRIMARY verdict on disclosure-content duties; the NLI judge (sem_all) acts as a guardrail that
    # softens an LLM "Compliant" it cannot entail; structural duties keep their crawl-signal verdict
    # and inherently-internal duties are routed to "Not externally verifiable". Falls back silently to
    # the NLI/semantic sem_all when the LLM is unavailable, so the engine always runs with zero keys.
    _STRUCTURAL_DUTIES = {33, 34, 35, 37, 38}
    _INTERNAL_DUTIES = {31, 41, 42, 43, 44, 45, 46, 47}
    try:
        from ..rag import llm_judge
        if ptext.strip() and llm_judge.enabled():
            _llm4 = llm_judge.judge_policy_rag(ptext)
            _g2e = {"Compliant": "Compliant", "Partial": "Partial",
                    "Gap": "Not disclosed", "NotVerifiable": "Not externally verifiable"}
            for _c in CHECKS:
                _cid = _c["id"]
                if _cid in _STRUCTURAL_DUTIES:
                    continue                                   # keep the crawl-signal verdict
                if _cid in _INTERNAL_DUTIES:                   # internal control: unverifiable from outside
                    _prev = sem_all.get(_cid)
                    sem_all[_cid] = ("Not externally verifiable", 0.75, _prev[2] if _prev else "")
                    continue
                if _cid not in _llm4:
                    continue
                _v4, _ev = _llm4[_cid]
                _nli = sem_all.get(_cid, (None,))[0]
                if _v4 == "Compliant" and _nli == "Not disclosed":   # guardrail: unsupported compliance
                    _v4 = "Partial"
                if _v4 == "Gap" and _nli == "Compliant":             # NLI entails a disclosure the LLM missed
                    _v4 = "Partial"
                if _v4 == "Compliant" and _nli == "Partial":
                    _v4 = "Partial"
                sem_all[_cid] = (_g2e.get(_v4, "Not disclosed"), 0.9, _ev)
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

    # Authoritative: the institution's own notice is a policy on the primary host (or a pasted policy).
    # This overrides any crawler-level flag that counted a policy on a third-party-powered subdomain.
    if pages:
        policy_found = bool(source_url) or bool(policy_text and policy_text.strip())
    elif policy_found is None:
        policy_found = bool(ptext.strip())

    findings = [f for f in (_finding(c, ptext, source_url, pages, site, site_collects, is_https,
                                     evaluated, exposure, collecting_urls, sem_all.get(c["id"]))
                            for c in CHECKS) if f]

    # The main site has no notice of its own, but a vendor template exists on another subdomain:
    # record it explicitly so the gap (reliance on a processor's template) is visible, not hidden.
    if pages and not policy_found and _offsite_policies:
        _op = _offsite_policies[0]["host"]
        findings.append(Finding(
            id="obs-no-own-privacy-notice",
            title="The institution publishes its own privacy notice",
            finding="The main site publishes no privacy notice of its own",
            category="Transparency",
            priority="High", severity="High",
            verdict="Not disclosed",
            statement=(f"No privacy notice was found on the primary site ({_base}). A privacy/cookie "
                       f"policy exists only on a separate, third-party-powered subdomain ({_op}) and is "
                       "a vendor template that names the institution merely as 'Operator'. Under the "
                       "DPDP Act the institution is the Data Fiduciary and must publish its own notice; "
                       "a service-provider's template on one portal does not discharge that duty for the "
                       "main property."),
            impact=("Visitors to the main site are given no notice of what personal data is collected, "
                    "for what purpose, or how to exercise their rights."),
            recommendation=("Publish a DPDP-compliant privacy notice on the primary domain itself "
                            "(linked from the footer), naming the data-protection / grievance contact "
                            "and the route to make access, correction and erasure requests."),
            references=["DPDP Act 2023 s.5", "DPDP Act 2023 s.8(5)"],
            affected_urls=[url or _base]))

    findings.sort(key=lambda f: (_ORDER.get(f.severity, 9), f.title))

    overall = _overall(findings, len(CHECKS))
    # `chrome`, `collecting` and `collecting_urls` were computed above (before the findings loop).
    serious_pages = list(collecting_urls)
    _collecting_set = set(collecting_urls)

    # Per-page rows for the assets-in-scope and page-by-page sections. On a large (deep) crawl we
    # keep every data-collecting page plus a sample of the rest, so the report stays readable instead
    # of listing thousands of near-identical rows. The full page count is in coverage.n_pages.
    _pp_order = ([p for p in pages if p["url"] in collecting_urls]
                 + [p for p in pages if p["url"] not in collecting_urls])
    per_page_rows = []
    for i, p in enumerate(_pp_order[:80], 1):
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

    # Data-category inventory: which categories of personal / sensitive / financial data the site
    # handles (Aadhaar, PAN, payment card, GSTIN, voter id, passport), detected by Presidio over the
    # crawled text. Report-facing context (counts only); a government identifier or card raises the
    # data-sensitivity of the assessment. Empty when presidio is unavailable.
    data_categories = []
    try:
        from . import pii
        if pii.available():
            # Cap the combined text so the inventory scan stays fast on a large crawl; per-page leak
            # detection (records.detect_published_records) still runs over every page in full.
            _allpii = (" ".join(p.get("text", "") for p in pages))[:200000] or (policy_text or "")
            data_categories = pii.categories(_allpii)
    except Exception:
        data_categories = []

    # Enforceable-today (IT Act, 2000 s.43A + SPDI Rules, 2011) layer: mark which of the unmet duties
    # ALSO have a basis enforceable now (applicable when the site handles sensitive data / SPDI),
    # versus those that only become enforceable on DPDP commencement. References on the affected
    # findings gain the present-law provision so the reader sees the current legal exposure.
    enforceability = {}
    try:
        from . import it_act as _ita
        _fields = {f_ for p in pages for f_ in (p.get("data_collected") or [])}
        _spdi = _ita.handles_spdi(data_categories, _fields)
        _unmet_ids = []
        for _f in findings:
            _m = re.match(r"c(\d+)-", _f.id)
            if not _m:
                continue
            _did = int(_m.group(1))
            _unmet_ids.append(_did)
            _basis = _ita.enforceable_today(_did)
            if _basis and _spdi:
                _ref = f"Enforceable today - {_basis['provision']}"
                if _ref not in _f.references:
                    _f.references.append(_ref)
        enforceability = _ita.summary(_unmet_ids, _spdi)
        # IT Act grade: the same adequacy/grade machinery, but restricted to the duties that ALSO have
        # a present IT Act, 2000 / SPDI Rules, 2011 basis -- so a site carries a present-law grade
        # alongside its (prospective) DPDP grade. `applicable_now` says whether it bites today (SPDI
        # observed) or becomes enforceable on DPDP commencement.
        _W = {"Compliant": 1.0, "Not externally verifiable": 0.75, "Partial": 0.5,
              "Not disclosed": 0.0, "Gap": 0.0}
        _fverd = {}
        for _f in findings:
            _mm = re.match(r"c(\d+)-", _f.id)
            if _mm:
                _fverd[int(_mm.group(1))] = _f.verdict
        _inforce = list(_ita._MAP.keys())
        if _inforce:
            _ia = round(sum(_W.get(_fverd.get(d, "Compliant"), 0.0) for d in _inforce) / len(_inforce), 2)
            enforceability["it_act_adequacy"] = _ia
            enforceability["it_act_grade"] = _grade(_ia)
            enforceability["it_act_duty_count"] = len(_inforce)
    except Exception:
        enforceability = {}

    coverage = {"policy_found": policy_found, "platform": platform,
                "offsite_policies": _offsite_policies,
                "archived_policy": archived_policy, "site_collects": site_collects,
                "observed_trackers": _obs_trackers, "observed_collectors": _obs_collectors,
                "data_categories": data_categories, "enforceability": enforceability,
                "n_pages": len(pages), "n_collecting": len(collecting),
                "collecting_pages": [p["url"] for p in collecting],
                "serious_pages": serious_pages,
                "subdomains": sorted(set(subdomains or [])
                                     or {re.sub(r"^https?://", "", u).split("/")[0]
                                         for u in evaluated if u}),
                "assessed_urls": evaluated[:150],   # cap the listed URLs; n_pages holds the true total
                "consent_banner": any(p.get("consent_banner") for p in pages),
                "screenshots": [{"page": _pg_name(p["url"], site), "url": p["url"],
                                 "path": p.get("screenshot")} for p in pages if p.get("screenshot")],
                "coverage_pct": min(1.0, len(pages) / max(1, page_budget))}

    return ComplianceReport(
        site=site, url=url or "", scope="site", pages_crawled=len(pages), site_type=site_type,
        generated_at=_now(), grounded=True, inconclusive=False, coverage=coverage,
        overall=overall, findings=findings, per_page=per_page_rows,
        exposure=exposure_findings, disclaimer=DISCLAIMER)
