"""
report_render.py -- render a ComplianceReport as a formatted Markdown report.

Reproduces the structure of the Adhikaar assessment report (cover, dashboard, executive
summary, summary of findings, detailed observations, and appendices A/B/C/F). Markdown is
chosen so it converts cleanly to PDF/HTML; the section order and wording follow the real
engine output. Two products are produced: the full Compliance report and the shorter
Recommendation report (top findings + prioritised action plan).
"""
from __future__ import annotations
from .catalog import CHECKS, PENALTY_BANDS, anchor_label
from .models import ComplianceReport

AUTHORS = ("Developed by Sohamm Manish Shheth (sohamm.shheth24@sakec.ac.in) & "
           "Dr. Nilakshi Jain (nilakshi.jain@sakec.ac.in)")
GRADE_MEANING = {
    "A": "Substantially complete disclosure; minor items only",
    "B": "Good disclosure with a few gaps to close",
    "C": "Partial disclosure; remediation advised",
    "D": "Partial disclosure; priority remediation required",
    "E": "Weak disclosure; urgent remediation required",
}
POSTURE = {"A": "STRONG", "B": "GOOD", "C": "MODERATE", "D": "PARTIAL", "E": "WEAK"}


def _page_name(url: str) -> str:
    seg = url.rstrip("/").split("/")[-1]
    if not seg or "." in seg:            # domain root -> Home
        return "Home"
    return seg.replace("-", " ").title()


def _exec_summary(rep: ComplianceReport, org: str) -> str:
    cov = rep.coverage
    o = rep.overall
    platform = cov.get("platform", "Unknown")
    lead = (f"The {org} website is served on {platform}. " if platform and platform != "Unknown"
            else f"The {org} website was assessed. ")
    parts = [lead]
    if not cov.get("policy_found"):
        parts.append("No privacy policy could be located on the site after following its links. ")
        arch = cov.get("archived_policy")
        if arch:
            parts.append(
                f"One was published at {arch['url']} and was last seen there on "
                f"{arch['last_seen']}; that address no longer serves it, so the notice appears to "
                "have been lost in a site change rather than never written. Restoring it at the "
                "address the site already links to is the fastest remedy. ")
        parts.append(
            "The central problem is that no privacy notice is published at all; beyond that, "
            "nothing commits the organisation to notify a personal-data breach, children's data "
            "is not protected as the Act requires and data is collected with no notice at the "
            "point of collection.")
    else:
        parts.append(f"A privacy notice was located and assessed. {o.summary}")
    para1 = "".join(parts)

    n_pages = cov.get("n_pages", rep.pages_crawled)
    n_coll = cov.get("n_collecting", 0)
    serious = [_page_name(u) for u in cov.get("serious_pages", [])[:2]]
    serious_txt = " and ".join(serious) if serious else "the collecting pages"
    para2 = (f"All {n_pages} crawled page(s) were assessed; {n_coll} collect or process personal "
             f"data on the page itself. The pages carrying the most serious findings are "
             f"{serious_txt}. Overall posture: {POSTURE[o.grade]} compliance - urgent remediation "
             "required. Most gaps are fixable within 30 to 90 days without new software; the "
             "priority is to protect any publicly exposed personal data and to make the privacy "
             "notice reachable at the point of collection.")
    return para1 + "\n\n" + para2


def render_compliance(rep: ComplianceReport, org: str | None = None,
                      submitted_to: str = "The Board of Trustees") -> str:
    org = org or rep.site
    o = rep.overall
    L: list[str] = []
    A = L.append

    # --- Cover ---
    A(f"# {org}\n## DPDP Compliance Assessment\n")
    A("**Digital Personal Data Protection Act, 2023 and DPDP Rules, 2025** — "
      "Disclosure and Behaviour Assessment\n")
    A(f"| | |\n|---|---|")
    A(f"| Report Release Date | {rep.generated_at} |")
    A(f"| Type of Assessment | DPDP disclosure and observed-behaviour assessment |")
    A(f"| Assessed Property | {rep.url or rep.site} |")
    A(f"| Scope | {rep.pages_crawled} page(s) of {rep.site} |")
    A(f"| Assessment Grade | **{o.grade}** — {GRADE_MEANING[o.grade]} |")
    A(f"| Prepared Using | Adhikaar — automated DPDP assessment engine |")
    A(f"| Submitted To | {submitted_to}, {org} |\n")
    A(f"*Confidential — prepared for {submitted_to}, {org}. {AUTHORS}.*\n")
    A("---\n")

    # --- Dashboard ---
    A("## Assessment Dashboard\n")
    A("Every figure on this page is computed from the findings, not an additional judgement.\n")
    A("**Grade bands** (adequacy floor): A 0.85 · B 0.70 · C 0.55 · D 0.40 · E 0.00. "
      f"This assessment: **{o.grade}** (adequacy {o.adequacy:.2f}).\n")
    A("### Severity Profile\n")
    A("| Severity | Count | What the band means |\n|---|---|---|")
    A(f"| Critical | {o.counts.get('Critical',0)} | Personal data exposed on the property itself |")
    A(f"| High | {o.counts.get('High',0)} | A mandatory duty unmet where personal data is collected |")
    A(f"| Medium | {o.counts.get('Medium',0)} | Third-party behaviour, or disclosed but incomplete |")
    A(f"| Low | {o.counts.get('Low',0)} | Governance and best-practice items |")
    A(f"| Info | {o.counts.get('Info',0)} | Disclosed but not verifiable from outside |")
    A(f"\n**Requirements met:** {o.counts.get('Requirements met',0)} of {len(CHECKS)}.\n")

    # Category exposure (worst finding per category)
    A("### Category Exposure\n")
    A("| Category | Worst finding | Open findings |\n|---|---|---|")
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}
    by_cat: dict[str, list] = {}
    for f in rep.findings:
        by_cat.setdefault(f.category, []).append(f)
    for cat, fs in sorted(by_cat.items(), key=lambda kv: min(order.get(x.severity, 9) for x in kv[1])):
        worst = min(fs, key=lambda x: order.get(x.severity, 9)).severity
        A(f"| {cat} | {worst} | {len(fs)} |")
    A("\n---\n")

    # --- Executive Summary ---
    A("## 1. Executive Summary\n")
    A(_exec_summary(rep, org) + "\n")

    # --- Summary of Findings ---
    A("## 1.6 Summary of Findings\n")
    A("Every open finding, worst first.\n")
    A("| Sr. | Finding | DPDP provision | Severity | Max penalty | Where it applies |\n"
      "|---|---|---|---|---|---|")
    for i, f in enumerate(rep.findings, 1):
        where = ", ".join(f.affected_urls[:2]) if f.affected_urls else "Policy-level (whole site)"
        A(f"| {i} | {f.finding or f.title} | {anchor_label({'dpdp_anchor': f.dpdp_anchor})} | "
          f"{f.severity} | {f.penalty.max} | {where} |")
    A("")

    # --- Detailed Observations ---
    A("## 2. Detailed Observations\n")
    for i, f in enumerate([x for x in rep.findings if x.severity in ("Critical", "High", "Medium")], 1):
        A(f"### 2.{i} {f.finding or f.title}\n")
        A(f"- **Severity:** {f.severity}  ·  **Status:** {f.status}  ·  **Verdict:** {f.verdict}")
        A(f"- **Requirement:** {f.title}")
        A(f"- **DPDP provision:** {anchor_label({'dpdp_anchor': f.dpdp_anchor})}  ·  "
          f"**Maximum penalty:** {f.penalty.max}")
        A(f"- **Affected:** {', '.join(f.affected_urls) if f.affected_urls else 'Policy-level (whole site)'}")
        if f.evidence.policy_quote:
            A(f"- **Evidence:** \"{f.evidence.policy_quote[:200]}\"")
        A(f"- **Observation:** {f.statement}")
        A(f"- **Impact:** {f.impact}")
        A(f"- **Recommendation:** {f.recommendation}\n")

    # --- Appendices ---
    A("## Appendix A — Assessment Method\n")
    A("External, unauthenticated assessment of published disclosures and observable behaviour. "
      "No test attempted to bypass a control, submit data or access any account. Internal "
      "controls that cannot be verified from outside (encryption at rest, access logging, staff "
      "training, processor contracts) are recorded as disclosure-only and never scored as "
      "failures. Each of the 47 requirements contributes a weight by its verdict "
      "(Compliant 1.0, Not-externally-verifiable 0.75, Partial 0.5, otherwise 0); the total over "
      "47 gives the adequacy, mapped to a grade band.\n")

    A("## Appendix B — All 47 Requirements\n")
    A("| No. | Category | Requirement | Provision | Severity |\n|---|---|---|---|---|")
    for c in CHECKS:
        A(f"| {c['id']} | {c['category']} | {c['requirement']} | {anchor_label(c)} | "
          f"{c.get('priority','-')} |")
    A("")

    A("## Appendix C — Penalty Exposure Under the Schedule\n")
    A("Every figure is a maximum the Data Protection Board of India may impose under Section 33 "
      "after an inquiry. It is not an automatic fine, is not charged per finding, and figures "
      "must never be added together.\n")
    A("| Class of breach | Maximum |\n|---|---|")
    for band, mx in PENALTY_BANDS.items():
        A(f"| {band} | {mx} |")
    A("")

    A("## Appendix F — Confidentiality and Disclaimer\n")
    A(rep.disclaimer + "\n")
    A(f"*{AUTHORS}.*")
    return "\n".join(L)


def render_recommendation(rep: ComplianceReport, org: str | None = None,
                          submitted_to: str = "The Board of Trustees") -> str:
    org = org or rep.site
    o = rep.overall
    L: list[str] = []
    A = L.append
    A(f"# DPDP Compliance Report — {org}\n")
    A(f"**{rep.url or rep.site}**  ·  Compliance posture: **{POSTURE[o.grade]}** "
      f"(grade {o.grade}, adequacy {o.adequacy:.2f})\n")
    A(f"Report date {rep.generated_at}  ·  Prepared using Adhikaar — Data Rights Companion  ·  "
      f"Submitted to {submitted_to}, {org}\n")
    A("> This report is information, not legal advice, and is not a legal certification. Penalty "
      "figures are statutory maximums under Section 33, imposed only after an inquiry; they are "
      "not automatic fines and must not be added together.\n")

    A("## 1. Executive Summary\n")
    A(f"{o.at_a_glance} Overall posture: {POSTURE[o.grade]} compliance. Most gaps are fixable "
      "within 30 to 90 days without new software; the priority is to protect any exposed "
      "personal data and to make the privacy notice reachable at the point of collection.\n")

    A("## Top findings\n")
    A("| # | Finding | DPDP reference | Severity | Max penalty | Priority action |\n"
      "|---|---|---|---|---|---|")
    top = [f for f in rep.findings if f.severity in ("Critical", "High")][:8]
    for i, f in enumerate(top, 1):
        A(f"| {i} | {f.finding or f.title} | {anchor_label({'dpdp_anchor': f.dpdp_anchor})} | "
          f"{f.severity} | {f.penalty.max} | {f.recommendation} |")
    A("")

    # Prioritised action plan by window
    A("## Prioritised Action Plan\n")
    windows = {"Immediate (this week)": ("Critical", "High"),
               "Within 30 days": ("Medium",), "Within 90 days": ("Low",)}
    for win, sevs in windows.items():
        acts = [f for f in rep.findings if f.severity in sevs]
        if not acts:
            continue
        A(f"**{win}**")
        for f in acts[:8]:
            A(f"- {f.recommendation} ({f.title})")
        A("")
    A(f"*{AUTHORS}.*")
    return "\n".join(L)
