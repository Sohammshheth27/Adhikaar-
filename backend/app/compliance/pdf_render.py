"""
pdf_render.py -- render the Compliance and Recommendation reports as multi-page PDFs that
reproduce the Adhikaar report TEMPLATE 1:1: Calibri type, monochrome black-on-white, thin-bordered
white tables with bold headers and italic centred captions, a centred two-line running header, the
"Adhikaar" wordmark on the cover, a faint diagonal watermark on every page, and a footer carrying
"Confidential -- prepared for <board>, <org>    Page X of Y" with the authorship line.

Template DNA was reverse-engineered from the reference PDFs (fonts via PyMuPDF, logo/watermark
extracted to app/assets, colours sampled from the rendered pages).
"""
from __future__ import annotations
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
                                Table, TableStyle, PageBreak, NextPageTemplate, Image)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .catalog import CHECKS, PENALTY_BANDS, anchor_label
from .report_render import GRADE_MEANING, POSTURE, _exec_summary, _page_name

# ---- fonts: use the real Calibri family (falls back to Helvetica off-Windows) ----
_WF = r"C:\Windows\Fonts"
try:
    pdfmetrics.registerFont(TTFont("Calibri", os.path.join(_WF, "calibri.ttf")))
    pdfmetrics.registerFont(TTFont("Calibri-Bold", os.path.join(_WF, "calibrib.ttf")))
    pdfmetrics.registerFont(TTFont("Calibri-Italic", os.path.join(_WF, "calibrii.ttf")))
    pdfmetrics.registerFontFamily("Calibri", normal="Calibri", bold="Calibri-Bold",
                                  italic="Calibri-Italic", boldItalic="Calibri-Bold")
    BASE, BOLD, ITAL = "Calibri", "Calibri-Bold", "Calibri-Italic"
except Exception:
    BASE, BOLD, ITAL = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"

BLACK = colors.black
GREY = colors.HexColor("#333333")
_ASSETS = os.path.join(os.path.dirname(__file__), "..", "assets")
LOGO = os.path.join(_ASSETS, "img_8.png")
WM_SRC = os.path.join(_ASSETS, "img_8.png")       # clean wordmark (no filled background)
WM_FAINT = os.path.join(_ASSETS, "_wm8_ghost.png")
_WM_FADE = 0.86                                    # how far to fade toward white (higher = fainter)
AUTHOR_LINE = ("Developed by Sohamm Manish Shheth (sohamm.shheth24@sakec.ac.in) "
               "& Dr. Nilakshi Jain (nilakshi.jain@sakec.ac.in)")


def _band_amt(s: str) -> int:
    import re
    m = re.search(r"(\d[\d,]*)\s*crore", s or "")
    return int(m.group(1).replace(",", "")) if m else 0


def _collect_summary(rep):
    """Human phrase of the personal data collected, and the third parties observed."""
    fields = []
    for r in rep.per_page:
        if r.priority == "High" and r.processes:
            for f in r.processes.split(", "):
                if f and f not in fields and f not in ("personal data",):
                    fields.append(f)
    tp = sorted({t.get("domain", "") for t in rep.tracker_inventory if t.get("domain")})
    return fields, tp


def _ensure_watermark():
    """Make a faint (near-white) version of the wordmark once, for the page watermark."""
    if os.path.exists(WM_FAINT) or not os.path.exists(WM_SRC):
        return WM_FAINT if os.path.exists(WM_FAINT) else None
    try:
        from PIL import Image as PImage
        im = PImage.open(WM_SRC).convert("RGBA")
        px = im.load()
        for y in range(im.height):
            for x in range(im.width):
                r, g, b, a = px[x, y]
                fd = _WM_FADE
                px[x, y] = (int(r + (255 - r) * fd), int(g + (255 - g) * fd),
                            int(b + (255 - b) * fd), a)
        im.save(WM_FAINT)
        return WM_FAINT
    except Exception:
        return None


def _styles():
    ss = getSampleStyleSheet()
    def add(name, **kw):
        kw.setdefault("fontName", BASE)
        kw.setdefault("textColor", BLACK)
        ss.add(ParagraphStyle(name, parent=ss["Normal"], **kw))
    add("Body", fontSize=10.5, leading=14, spaceAfter=6)
    add("Cover", fontSize=25, leading=29, alignment=TA_CENTER)
    add("CoverOrg", fontName=BOLD, fontSize=17, leading=21, alignment=TA_CENTER)
    add("CoverSub", fontSize=11.5, leading=15, alignment=TA_CENTER)
    add("H1", fontName=BOLD, fontSize=16, leading=20, spaceBefore=12, spaceAfter=7)
    add("H2", fontName=BOLD, fontSize=12.5, leading=16, spaceBefore=10, spaceAfter=5)
    add("Caption", fontName=ITAL, fontSize=10, leading=13, alignment=TA_CENTER, spaceAfter=4)
    add("Cell", fontSize=9, leading=11.5)
    add("CellB", fontName=BOLD, fontSize=9, leading=11.5)
    add("CellBC", fontName=BOLD, fontSize=9, leading=11.5, alignment=TA_CENTER)
    return ss


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas for 'Page X of Y', plus the running header, watermark and footer."""
    def __init__(self, *a, header_l1="", header_l2="", footer="", watermark=None, **k):
        super().__init__(*a, **k)
        self._saved = []
        self._h1, self._h2, self._footer, self._wm = header_l1, header_l2, footer, watermark

    def showPage(self):
        self._saved.append(dict(self.__dict__)); self._startPage()

    def save(self):
        n = len(self._saved)
        for st in self._saved:
            self.__dict__.update(st)
            self._furniture(n)
            super().showPage()
        super().save()

    def _furniture(self, total):
        w, h = A4
        # centred two-line header
        self.setFillColor(BLACK)
        self.setFont(BOLD, 8.5)
        self.drawCentredString(w / 2, h - 12 * mm, self._h1)
        self.setFont(BASE, 7.5)
        self.drawCentredString(w / 2, h - 15.5 * mm, self._h2)
        # footer
        self.setFont(BASE, 6.8)
        self.setFillColor(GREY)
        self.drawString(16 * mm, 12 * mm, self._footer)
        self.drawString(16 * mm, 9 * mm, AUTHOR_LINE)
        self.drawRightString(w - 16 * mm, 12 * mm, f"Page {self._pageNumber} of {total}")


def _draw_watermark(c, doc):
    """Drawn on page START (before frame content) so it sits BEHIND the text, very faint."""
    wm = _ensure_watermark()
    if not wm:
        return
    w, h = A4
    c.saveState()
    c.translate(w / 2, h / 2)
    c.rotate(38)
    iw = 175 * mm
    ih = iw * 65.0 / 564.0
    try:
        c.drawImage(wm, -iw / 2, -ih / 2, iw, ih, mask="auto", preserveAspectRatio=True)
    except Exception:
        pass
    c.restoreState()


def _doc(path, h1, h2, footer):
    f = Frame(16 * mm, 15 * mm, A4[0] - 32 * mm, A4[1] - 34 * mm, id="body",
              leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc = BaseDocTemplate(path, pagesize=A4, title=h1)
    doc.addPageTemplates([PageTemplate(id="cover", frames=[f], onPage=_draw_watermark),
                          PageTemplate(id="body", frames=[f], onPage=_draw_watermark)])
    wm = _ensure_watermark()

    def maker(*a, **k):
        return NumberedCanvas(*a, header_l1=h1, header_l2=h2, footer=footer, watermark=wm, **k)
    doc._maker = maker
    return doc


# ---- monochrome table helpers (white bg, thin black grid, bold header row) ----
def _table(data, widths, ss, caption=None, header=True, align_center_cols=()):
    body = [[c if hasattr(c, "wrap") else Paragraph(str(c), ss["Cell"]) for c in row] for row in data]
    t = Table(body, colWidths=widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.5, BLACK), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
    if header:
        style += [("LINEBELOW", (0, 0), (-1, 0), 1.0, BLACK)]
    for c in align_center_cols:
        style.append(("ALIGN", (c, 0), (c, -1), "CENTER"))
    t.setStyle(TableStyle(style))
    if caption:
        return [Paragraph(caption, ss["Caption"]), t]
    return [t]


def _hcells(headers, ss, center=True):
    st = ss["CellBC"] if center else ss["CellB"]
    return [Paragraph(h, st) for h in headers]


def _bar(frac):
    """A small solid black horizontal bar whose length is proportional to frac (0-1)."""
    w = max(3 * mm, min(1.0, frac) * 20 * mm)
    t = Table([[""]], colWidths=[w], rowHeights=[2.6 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BLACK),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _kv(rows, ss, col0=52 * mm):
    data = [[Paragraph(f"{k}", ss["CellB"]), Paragraph(str(v), ss["Cell"])] for k, v in rows]
    return _table(data, [col0, A4[0] - 32 * mm - col0], ss, header=False)[0]


def _findings_table(rep, ss):
    data = [_hcells(["Sr.", "Finding", "DPDP provision", "Severity", "Maximum penalty",
                     "Where it applies"], ss)]
    for i, f in enumerate(rep.findings, 1):
        where = ", ".join(f.affected_urls[:2]) if f.affected_urls else "Policy-level (whole site)"
        data.append([Paragraph(str(i), ss["Cell"]), Paragraph(f.finding or f.title, ss["Cell"]),
                     Paragraph(anchor_label({"dpdp_anchor": f.dpdp_anchor}), ss["Cell"]),
                     Paragraph(f.severity, ss["Cell"]), Paragraph(f.penalty.max, ss["Cell"]),
                     Paragraph(where, ss["Cell"])])
    return _table(data, [9 * mm, 55 * mm, 30 * mm, 17 * mm, 24 * mm, 36 * mm], ss,
                  align_center_cols=(0, 3))[0]


def _perpage_table(rep, ss, cols="assets"):
    if cols == "assets":
        data = [_hcells(["Sr.", "Page", "URL", "Type", "Criticality",
                         "Personal data or behaviour observed"], ss)]
        for r in rep.per_page:
            data.append([str(r.sr), r.page, r.url, r.page_type, r.criticality, r.processes])
        return _table(data, [9 * mm, 22 * mm, 44 * mm, 13 * mm, 19 * mm, 64 * mm], ss)[0]
    data = [_hcells(["Sr.", "Page", "URL", "Processes", "Page-specific issue", "Priority"], ss)]
    for r in rep.per_page:
        data.append([str(r.sr), r.page, r.url, r.processes, r.issue, r.priority])
    return _table(data, [9 * mm, 20 * mm, 38 * mm, 33 * mm, 52 * mm, 19 * mm], ss)[0]


def _scope_section(rep, ss):
    """List every site/subdomain and every page assessed -- shown at the start of the report."""
    E = [Paragraph("Scope - Sites and Subdomains Assessed", ss["H1"])]
    subs = rep.coverage.get("subdomains") or []
    urls = rep.coverage.get("assessed_urls") or []
    E.append(Paragraph(f"This assessment covered the domain and subdomain(s) of {rep.site} listed "
                       f"below. {len(urls)} page(s) were rendered and assessed as an ordinary "
                       "visitor's browser would render them.", ss["Body"]))
    if subs:
        E.append(Paragraph("Domains and subdomains", ss["Caption"]))
        E += _table([_hcells(["#", "Site / subdomain"], ss)]
                    + [[str(i), s] for i, s in enumerate(subs, 1)],
                    [12 * mm, A4[0] - 32 * mm - 12 * mm], ss)
    if urls:
        E.append(Paragraph("Pages assessed", ss["Caption"]))
        E += _table([_hcells(["#", "Assessed URL"], ss)]
                    + [[str(i), u] for i, u in enumerate(urls, 1)],
                    [12 * mm, A4[0] - 32 * mm - 12 * mm], ss)
    E.append(PageBreak())
    return E


def _cover(rep, org, submitted_to, ss, report_type):
    E = [Spacer(1, 8 * mm)]
    if os.path.exists(LOGO):
        img = Image(LOGO, width=118 * mm, height=118 * mm * 65 / 564)
        img.hAlign = "CENTER"
        E += [img, Spacer(1, 22 * mm)]
    else:
        E.append(Spacer(1, 30 * mm))
    E.append(Paragraph(report_type, ss["Cover"]))
    E.append(Spacer(1, 3 * mm))
    E.append(Paragraph(org, ss["CoverOrg"]))
    E.append(Spacer(1, 6 * mm))
    E.append(Paragraph("Digital Personal Data Protection Act, 2023 and DPDP Rules, 2025", ss["CoverSub"]))
    E.append(Paragraph("Disclosure and Behaviour Assessment", ss["CoverSub"]))
    E.append(Spacer(1, 14 * mm))
    o = rep.overall
    E.append(_kv([
        ("Report Release Date", rep.generated_at),
        ("Type of Assessment", "DPDP disclosure and observed-behaviour assessment"),
        ("Type of Report", "First assessment report"),
        ("Assessed Property", rep.url or rep.site),
        ("Scope", f"{rep.coverage.get('n_pages', rep.pages_crawled)} page(s) of {rep.site}"),
        ("Assessment Grade", f"{o.grade} \u2014 {GRADE_MEANING[o.grade]}<br/>"
                             "Grade bands: A best, E weakest. The scale and the working are on the "
                             "dashboard overleaf."),
        ("Prepared Using", "Adhikaar"),
        ("Submitted To", f"{submitted_to}, {org}"),
    ], ss))
    E.append(PageBreak())
    return E


def build_compliance_pdf(rep, org=None, submitted_to="The Board of Trustees", out_path="compliance.pdf"):
    org = org or rep.site
    ss = _styles()
    doc = _doc(out_path, org, "DPDP Compliance Assessment",
               f"Confidential \u2014 prepared for {submitted_to}, {org}")
    o = rep.overall
    E = _cover(rep, org, submitted_to, ss, "Compliance Assessment Report")
    E.append(NextPageTemplate("body"))
    E += _scope_section(rep, ss)

    # Dashboard
    E.append(Paragraph("Assessment Dashboard", ss["H1"]))
    E.append(Paragraph("Every figure on this page is computed from the findings in section 2. It is "
                       f"a summary of that evidence, not an additional judgement. Assessed "
                       f"{rep.generated_at}.", ss["Body"]))
    E.append(Paragraph("Grade", ss["H2"]))
    grade_rows = [_hcells(["Grade", "Adequacy floor", "Meaning"], ss)]
    floors = {"A": "0.85", "B": "0.70", "C": "0.55", "D": "0.40", "E": "0.00"}
    for g in "ABCDE":
        mark = "  \u25c4 this assessment" if g == o.grade else ""
        grade_rows.append([Paragraph(g, ss["CellBC"]), Paragraph(floors[g], ss["Cell"]),
                           Paragraph(GRADE_MEANING[g] + mark, ss["Cell"])])
    E += _table(grade_rows, [22 * mm, 30 * mm, A4[0] - 32 * mm - 52 * mm], ss,
                caption="Grade bands and where this assessment falls", align_center_cols=(0, 1))

    # Category Exposure
    E.append(Paragraph("Category Exposure", ss["H2"]))
    _order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}
    by_cat: dict = {}
    for f in rep.findings:
        by_cat.setdefault(f.category, []).append(f)
    cat_sorted = sorted(by_cat.items(),
                        key=lambda kv: (min(_order.get(x.severity, 9) for x in kv[1]), -len(kv[1])))
    ce = [_hcells(["Category", "Weight", "Worst finding", "Open findings"], ss)]
    maxpen = max((_band_amt(f.penalty.max) for f in rep.findings), default=250) or 250
    for cat, fs in cat_sorted:
        worst = min(fs, key=lambda x: _order.get(x.severity, 9)).severity
        # weight bar proportional to the category's highest penalty band
        catpen = max(_band_amt(f.penalty.max) for f in fs)
        ce.append([Paragraph(cat, ss["Cell"]), _bar(catpen / maxpen),
                   Paragraph(worst, ss["Cell"]), Paragraph(str(len(fs)), ss["CellBC"])])
    E += _table(ce, [66 * mm, 24 * mm, 34 * mm, A4[0] - 32 * mm - 124 * mm], ss,
                caption="Each category scored by the most serious finding in it, worst first",
                align_center_cols=(1, 3))

    E.append(Paragraph("Severity Profile", ss["H2"]))
    sev = [_hcells(["Severity", "Count", "What the band means here"], ss),
           ["Critical", str(o.counts.get("Critical", 0)), "Personal data exposed on the property itself"],
           ["High", str(o.counts.get("High", 0)), "A mandatory duty unmet where personal data is collected"],
           ["Medium", str(o.counts.get("Medium", 0)), "Evidenced by third-party behaviour, or disclosed but incomplete"],
           ["Low", str(o.counts.get("Low", 0)), "Governance and best-practice items"],
           ["Info", str(o.counts.get("Info", 0)), "Disclosed but not verifiable from outside; recorded, not scored"]]
    E += _table(sev, [26 * mm, 18 * mm, A4[0] - 32 * mm - 44 * mm], ss, align_center_cols=(0, 1))
    E.append(Paragraph("What is working", ss["H2"]))
    met = o.counts.get("Requirements met", 0)
    E.append(Paragraph(f"The site is served over HTTPS; {met} of {len(CHECKS)} requirements is "
                       "already met; " + ("no personal data or sensitive files were found exposed on "
                       "the property itself." if not rep.exposure
                       else f"{len(rep.exposure)} exposure finding(s) were observed -- see below."), ss["Body"]))

    if rep.exposure:
        E.append(Paragraph("Data Exposure Observed", ss["H2"]))
        E.append(Paragraph("Sensitive files or personal records found readable on the property itself, "
                           "without authentication. These are the most serious findings and are treated "
                           "as Critical. Only the location and counts are recorded -- no file contents or "
                           "individual's data are reproduced.", ss["Body"]))
        ex = [_hcells(["Severity", "What was observed", "Where", "Provision"], ss)]
        for e in rep.exposure:
            ex.append([e.get("severity", ""), e.get("detail", ""),
                       ", ".join(e.get("found", []))[:70], e.get("provision", "")])
        E += _table(ex, [18 * mm, 82 * mm, 38 * mm, A4[0] - 32 * mm - 138 * mm], ss)

    # Distance to Remediation
    _beh = {"Consent Management", "Cross-border Transfers", "Technical Controls"}
    remaining = sum(1 for f in rep.findings if f.category in _beh
                    or (f.affected_urls and "Policy" not in (f.affected_urls[0] or "")))
    closes = len(rep.findings) - remaining
    if not rep.coverage.get("policy_found") and closes > 0:
        E.append(Paragraph("Distance to Remediation", ss["H2"]))
        E.append(Paragraph(f"Publishing the privacy notice closes {closes} of {len(rep.findings)} "
                           "findings, moving the assessment from E to D. The remaining "
                           f"{remaining} concern how the site behaves rather than what it discloses, "
                           "and need work on the site itself.", ss["Body"]))
        dt = [_hcells(["", "Findings", "Grade", "Adequacy"], ss),
              ["As assessed", str(len(rep.findings)), o.grade, f"{o.adequacy:.2f}"],
              ["With the notice published", str(remaining), "D", f"{(closes*1.0/len(CHECKS)):.2f}"]]
        E.append(_table(dt, [70 * mm, 30 * mm, 26 * mm, A4[0] - 32 * mm - 126 * mm], ss,
                        caption="What one document closes, and what it does not")[1])

    # Remediation Timeline
    E.append(Paragraph("Remediation Timeline", ss["H2"]))
    rt = [_hcells(["Window", "Actions", "Covering"], ss)]
    for win, sevs, cov in [("Immediate (this week)", ("Critical", "High"), "Privacy notice; security & breach; children's data; notice at forms"),
                           ("Within 30 days", ("Medium",), "Purpose & minimisation; retention; rights; published contact"),
                           ("Within 90 days", ("Low",), "Consent; processors; cross-border; governance")]:
        n = sum(1 for f in rep.findings if f.severity in sevs)
        rt.append([win, str(n), cov])
    E.append(_table(rt, [40 * mm, 20 * mm, A4[0] - 32 * mm - 60 * mm], ss,
                    caption="Where the work falls, from the prioritised action plan")[1])
    E.append(PageBreak())

    # Document Control
    E.append(Paragraph("Document Control", ss["H1"]))
    E.append(_kv([("Document Title", f"{org} - DPDP Compliance Assessment Report"),
                  ("Document Version", "1.0"),
                  ("Prepared By", "Adhikaar - automated DPDP assessment engine"),
                  ("Release Date", rep.generated_at),
                  ("Organisation Assessed", f"{org} ({rep.site})"),
                  ("Website Platform", rep.coverage.get("platform", "Unknown")),
                  ("Distribution", f"{submitted_to}, {org}")], ss))
    E.append(PageBreak())

    # Contents
    E.append(Paragraph("Contents", ss["H1"]))
    ss.add(ParagraphStyle("TocTop", parent=ss["Body"], fontName=BOLD, fontSize=10.5, spaceBefore=4, spaceAfter=1))
    ss.add(ParagraphStyle("TocSub", parent=ss["Body"], fontSize=10, leftIndent=10 * mm, spaceAfter=1))
    for t, sub in [("1  Introduction", 0), ("1.1  Engagement Scope", 1), ("1.2  Type of Assessment", 1),
                   ("1.3  Standards Referred", 1), ("1.4  Assessment Method", 1),
                   ("1.5  Executive Summary", 1), ("1.6  Summary of Findings", 1),
                   ("1.7  Page-by-Page Assessment", 1), ("1.8  How the Grade Was Reached", 1),
                   ("1.9  Severity Definitions", 1), ("2  Detailed Observations", 0),
                   ("3  Appendices", 0), ("3.1  Appendix A - Assessment Method in Detail", 1),
                   ("3.2  Appendix B - All 47 Requirements", 1),
                   ("3.3  Appendix C - Penalty Exposure Under the Schedule", 1),
                   ("3.4  Appendix D - Evidence Manifest", 1),
                   ("3.5  Appendix E - Third-Party and Cookie Inventory", 1),
                   ("3.6  Appendix F - Confidentiality, Glossary and Disclaimer", 1)]:
        E.append(Paragraph(t, ss["TocSub"] if sub else ss["TocTop"]))
    E.append(PageBreak())

    # 1 Introduction
    E.append(Paragraph("1  Introduction", ss["H1"]))
    E.append(Paragraph(f"This report presents the result of a Digital Personal Data Protection "
                       f"assessment of the web property operated by {org}. It examines what the "
                       "organisation publishes about its handling of personal data, and what its "
                       "website can be observed to do, against 47 requirements derived from the DPDP "
                       "Act, 2023 and the DPDP Rules, 2025.", ss["Body"]))
    E.append(Paragraph("1.1  Engagement Scope", ss["H2"]))
    E.append(Paragraph(f"The scope is the public web property below, as it stood on {rep.generated_at}. "
                       "Pages were discovered from the site's sitemap, robots directives, link graph "
                       "and common paths, and were rendered as an ordinary visitor's browser would.", ss["Body"]))
    E.append(Paragraph("Assets in scope", ss["Caption"]))
    E.append(_perpage_table(rep, ss, "assets"))
    E.append(Paragraph("1.2  Type of Assessment", ss["H2"]))
    E.append(Paragraph("External, unauthenticated assessment of published disclosures and observable "
                       "behaviour. No test attempted to bypass a control, submit data, or access any "
                       "account. Internal controls that cannot be verified from outside, such as "
                       "encryption at rest, access logging, staff training and processor contracts, are "
                       "recorded as disclosure-only and are never scored as failures.", ss["Body"]))
    E.append(Paragraph("1.3  Standards Referred", ss["H2"]))
    E.append(Paragraph("Digital Personal Data Protection Act, 2023 (India Code, Government of India, Act "
                       "22 of 2023). Digital Personal Data Protection Rules, 2025 (Gazette G.S.R. 846(E)). "
                       "Requirements are organised in a 47-item, 14-category framework, and every finding "
                       "cites the provision it relies on, verbatim, from those official sources.", ss["Body"]))
    E.append(Paragraph("1.4  Assessment Method", ss["H2"]))
    E.append(Paragraph("Each requirement is evaluated against the retrieved text and the observed "
                       "behaviour of the property. Where a requirement is addressed, the supporting clause "
                       "is quoted verbatim. Where nothing addresses it, the requirement is recorded as not "
                       "disclosed: silence is never read as compliance, and no finding is raised without "
                       "evidence.", ss["Body"]))
    E.append(Paragraph("1.5  Executive Summary", ss["H2"]))
    for para in _exec_summary(rep, org).split("\n\n"):
        E.append(Paragraph(para, ss["Body"]))
    E.append(Paragraph("1.6  Summary of Findings", ss["H2"]))
    E.append(Paragraph("Every open finding, worst first.", ss["Caption"]))
    E.append(_findings_table(rep, ss))
    E.append(PageBreak())

    # 1.7 Page-by-Page
    E.append(Paragraph("1.7  Page-by-Page Assessment", ss["H2"]))
    E.append(Paragraph("Each page assessed on its own signals.", ss["Caption"]))
    E.append(_perpage_table(rep, ss, "page"))
    # 1.8 How the Grade Was Reached
    E.append(Paragraph("1.8  How the Grade Was Reached", ss["H2"]))
    E.append(Paragraph("The grade is a disclosure-adequacy band. Each of the 47 requirements "
                       "contributes a weight by its verdict (Compliant 1.00, Not-externally-verifiable "
                       "0.75, Partial 0.50, otherwise 0); the total is divided by 47 and mapped to a "
                       "band. The working is printed so the grade can be checked rather than taken on "
                       "trust.", ss["Body"]))
    gw = [_hcells(["Verdict", "Requirements", "Weight", "Contribution"], ss),
          ["Disclosed (no finding raised)", str(met), "1.00", f"{met:.2f}"],
          ["Findings (weighted)", str(len(rep.findings)), "0-0.75", f"{o.adequacy*len(CHECKS)-met:.2f}"],
          ["Total", str(len(CHECKS)), "", f"{o.adequacy*len(CHECKS):.2f}"]]
    E += _table(gw, [68 * mm, 34 * mm, 26 * mm, A4[0] - 32 * mm - 128 * mm], ss, align_center_cols=(1, 2, 3))
    E.append(Paragraph(f"Adequacy = {o.adequacy*len(CHECKS):.2f} divided by {len(CHECKS)} = "
                       f"{o.adequacy:.2f}, which falls in band {o.grade} (band floor {floors[o.grade]}).", ss["Body"]))
    # 1.9 Severity Definitions
    E.append(Paragraph("1.9  Severity Definitions", ss["H2"]))
    E += _table([_hcells(["Band", "Meaning in this assessment"], ss),
        ["Critical", "An exposure observed on the property itself, such as personal records readable without authentication, or credentials carried over plain HTTP."],
        ["High", "A mandatory duty is unmet on a property that collects personal data."],
        ["Medium", "A duty evidenced only by third-party behaviour, or a disclosure that is present but incomplete."],
        ["Low", "Best-practice or internal-governance items whose absence from a public disclosure is not itself a breach."],
        ["Info", "Disclosed but not verifiable from outside; recorded, not scored."]],
        [26 * mm, A4[0] - 32 * mm - 26 * mm], ss)
    E.append(PageBreak())

    # 2 Detailed Observations -- one full labelled block per finding
    E.append(Paragraph("2  Detailed Observations", ss["H1"]))
    E.append(Paragraph("Each open finding is stated in full below with the evidence it rests on and the "
                       "provision it relies on. Findings are ordered worst first.", ss["Body"]))
    ss.add(ParagraphStyle("Lab", parent=ss["Body"], fontName=BOLD, fontSize=8.5, leading=11,
                          spaceBefore=3, spaceAfter=0, textColor=GREY))
    ss.add(ParagraphStyle("Val", parent=ss["Body"], fontSize=9.5, leading=12.5, spaceAfter=2))
    for i, f in enumerate(rep.findings, 1):
        E.append(Paragraph(f"2.{i}  {f.finding or f.title}", ss["H2"]))
        affected = ", ".join(f.affected_urls) if f.affected_urls else "Policy-level (whole site)"
        rows = [("SEVERITY RATING", f.severity), ("STATUS", f.status), ("REQUIREMENT", f.title),
                ("DPDP PROVISION", anchor_label({"dpdp_anchor": f.dpdp_anchor})),
                ("AFFECTED URL(S)", affected)]
        if f.evidence.policy_quote:
            rows.append(("EVIDENCE (verbatim)", '"' + f.evidence.policy_quote[:240] + '"'))
        if f.evidence.dpdp_quote:
            rows.append(("PROVISION (verbatim)", '"' + f.evidence.dpdp_quote[:280] + '"'))
        rows += [("DETAILED OBSERVATION", f.statement), ("IMPACT", f.impact),
                 ("RECOMMENDATION", f.recommendation),
                 ("MAXIMUM PENALTY EXPOSURE",
                  f"Maximum penalty: the Data Protection Board of India may impose {f.penalty.max} for "
                  "this class of breach under Section 33, after an inquiry weighing nature, gravity, "
                  "duration and mitigation. This is a statutory ceiling, not an automatic or per-finding "
                  "fine.")]
        for label, val in rows:
            E.append(Paragraph(label, ss["Lab"]))
            E.append(Paragraph(str(val), ss["Val"]))
        if i % 2 == 0:
            E.append(PageBreak())
        else:
            E.append(Spacer(1, 5 * mm))
    E.append(PageBreak())

    # 2A Detected data-processing technology (Nuclei tech-detect)
    _trk = rep.coverage.get("observed_trackers") or []
    _col = rep.coverage.get("observed_collectors") or []
    if _trk or _col:
        E.append(Paragraph("2A  Detected Data-Processing Technology", ss["H2"]))
        E.append(Paragraph("Fingerprinted on the live site, independent of what the policy discloses - "
                           "concrete data-flow evidence for the DPDP duties noted.", ss["Val"]))
        if _trk:
            E.append(Paragraph("Third-party trackers / analytics (external processors; data leaves the "
                               "site) - third-party sharing (s.8), cookie/consent (Rule 4):", ss["Lab"]))
            E.append(Paragraph(", ".join(_trk), ss["Val"]))
        if _col:
            E.append(Paragraph("Personal-data collection tools (the site collects & stores personal "
                               "data) - notice (s.5), retention (s.8(7)-(8)), security (s.8(5)):", ss["Lab"]))
            E.append(Paragraph(", ".join(_col), ss["Val"]))
        E.append(PageBreak())

    # 3 Appendices
    E.append(Paragraph("3  Appendices", ss["H1"]))
    E.append(Paragraph("3.1  Appendix A - Assessment Method in Detail", ss["H2"]))
    E.append(Paragraph("The 47 requirements were compiled from the DPDP Act, 2023 and the DPDP Rules, "
                       "2025 and grouped into 14 categories. For each requirement the engine searches the "
                       "retrieved policy text for the disclosure the provision requires and records a "
                       "verdict: Compliant (a clear disclosure is present), Partial (present but "
                       "incomplete), Not disclosed (none found), or Not externally verifiable (an internal "
                       "control that cannot be confirmed from outside). HTTPS is checked by observation. "
                       "Each verdict carries a weight (Compliant 1.00, Not-externally-verifiable 0.75, "
                       "Partial 0.50, otherwise 0); the mean over 47 is the adequacy, mapped to a grade "
                       "band. Behaviour observed on the site - trackers, cookies set before consent, and "
                       "forms collecting personal data - is recorded as separate, labelled evidence and is "
                       "never inferred from silence.", ss["Body"]))
    E.append(Paragraph("3.2  Appendix B - All 47 Requirements", ss["H2"]))
    E.append(Paragraph("The complete framework and this assessment verdict for each requirement.", ss["Caption"]))
    ab = [_hcells(["No.", "Category", "Requirement", "Provision", "Severity", "Verdict"], ss)]
    verdict_by = {}
    for f in rep.findings:
        import re as _re
        m = _re.match(r"c(\d+)-", f.id)
        if m:
            verdict_by[int(m.group(1))] = f.verdict
    for c in CHECKS:
        v = verdict_by.get(c["id"], "Compliant")
        ab.append([str(c["id"]), c["category"], c["requirement"], anchor_label(c),
                   c.get("priority", "-"), v])
    E.append(_table(ab, [8 * mm, 27 * mm, 66 * mm, 28 * mm, 15 * mm, 18 * mm], ss)[0])
    E.append(PageBreak())
    E.append(Paragraph("3.3  Appendix C - Penalty Exposure Under the Schedule", ss["H2"]))
    E.append(Paragraph("Every figure is a maximum the Data Protection Board of India may impose "
                       "under Section 33 after an inquiry. It is not an automatic fine, is not charged "
                       "per finding, and figures must never be added together.", ss["Body"]))
    pc = [_hcells(["Class of breach", "Maximum"], ss)] + [[k, v] for k, v in PENALTY_BANDS.items()]
    E.append(_table(pc, [55 * mm, A4[0] - 32 * mm - 55 * mm], ss)[0])
    E.append(Paragraph("3.4  Appendix D - Evidence Manifest", ss["H2"]))
    E.append(Paragraph("Every finding is grounded in evidence the assessment captured: the page it was "
                       "observed on, and where a disclosure was present, the verbatim clause. The pages "
                       "assessed and the behaviour observed are listed below; no personal data of any "
                       "individual is reproduced.", ss["Body"]))
    ev = [_hcells(["Sr.", "Page assessed", "Personal data / behaviour observed"], ss)]
    for r in rep.per_page:
        ev.append([str(r.sr), r.url, r.processes])
    E.append(_table(ev, [10 * mm, 62 * mm, A4[0] - 32 * mm - 72 * mm], ss)[0])
    # embedded page captures
    shots = [s for s in (rep.coverage.get("screenshots") or []) if s.get("path")]
    shots = [s for s in shots if os.path.exists(s["path"])]
    if shots:
        E.append(Paragraph("Page captures (evidence of the assessed pages)", ss["Caption"]))
        for s in shots[:6]:
            E.append(Paragraph(f"{s['page']} - {s['url']}", ss["CellB"]))
            try:
                img = Image(s["path"], width=150 * mm, height=100 * mm, kind="proportional")
                img.hAlign = "LEFT"
                E.append(img)
                E.append(Spacer(1, 4 * mm))
            except Exception:
                pass
    E.append(Paragraph("3.5  Appendix E - Third-Party and Cookie Inventory", ss["H2"]))
    if rep.tracker_inventory:
        E.append(Paragraph("Third parties observed loading before any consent interaction "
                           "(pre-consent), with the operator's jurisdiction.", ss["Body"]))
        tk = [_hcells(["Service", "Domain", "Operator jurisdiction"], ss)]
        for t in rep.tracker_inventory:
            tk.append([t.get("name", "?"), t.get("domain", ""), t.get("country", "")])
        E.append(_table(tk, [55 * mm, 70 * mm, A4[0] - 32 * mm - 125 * mm], ss)[0])
    else:
        E.append(Paragraph("No third-party trackers were observed on the assessed pages.", ss["Body"]))
    # Cookie inventory (values are never reproduced)
    ck = rep.cookie_inventory or []
    pre = sum(1 for c in ck if c.get("before_consent"))
    E.append(Paragraph("Cookies set on first load", ss["Caption"]))
    if ck:
        E.append(Paragraph(f"{len(ck)} cookie(s) were set on first load, {pre} of them before any "
                           "consent interaction (the assessment never accepts a banner). Cookie values "
                           "are not reproduced.", ss["Body"]))
        cc = [_hcells(["Name", "Domain", "Party", "Set before consent"], ss)]
        for c in ck[:30]:
            cc.append([c.get("name", ""), c.get("domain", ""),
                       "third-party" if c.get("third_party") else "first-party",
                       "Yes" if c.get("before_consent") else "No"])
        E.append(_table(cc, [45 * mm, 55 * mm, 28 * mm, A4[0] - 32 * mm - 128 * mm], ss,
                        align_center_cols=(3,))[0])
    else:
        E.append(Paragraph("No cookies were observed on first load.", ss["Body"]))
    # Consent-banner analysis
    E.append(Paragraph("Consent banner", ss["Caption"]))
    if rep.coverage.get("consent_banner"):
        E.append(Paragraph("A consent/cookie banner was detected. Note that the trackers and cookies "
                           "above were already set before any banner interaction, which is widely read "
                           "as pre-consent processing. Verify that the banner offers 'reject' as "
                           "prominently as 'accept' and does not pre-tick non-essential categories.", ss["Body"]))
    else:
        E.append(Paragraph("No consent/cookie banner was detected, yet third-party trackers and cookies "
                           "load on first visit; there is therefore no consent interaction at all before "
                           "personal data flows to third parties.", ss["Body"]))
    E.append(Paragraph("3.6  Appendix F - Confidentiality and Disclaimer", ss["H2"]))
    E.append(Paragraph(rep.disclaimer, ss["Body"]))

    doc.build(E, canvasmaker=doc._maker)
    return out_path


def build_recommendation_pdf(rep, org=None, submitted_to="The Board of Trustees", out_path="recommendation.pdf"):
    org = org or rep.site
    ss = _styles()
    doc = _doc(out_path, f"Adhikaar  \u2014  DPDP Compliance Assessment  \u2014  {rep.site}",
               "", f"Confidential \u2014 prepared for {submitted_to}, {org}")
    o = rep.overall
    E = _cover(rep, org, submitted_to, ss, "DPDP Compliance Report")
    E.append(NextPageTemplate("body"))
    E += _scope_section(rep, ss)

    E.append(Paragraph("1. Executive Summary", ss["H1"]))
    for para in _exec_summary(rep, org).split("\n\n"):
        E.append(Paragraph(para, ss["Body"]))
    E.append(Paragraph("Top findings", ss["H2"]))
    data = [_hcells(["#", "Finding", "DPDP reference", "Severity", "Max penalty", "Priority action"], ss)]
    top = [f for f in rep.findings if f.severity in ("Critical", "High")][:8]
    for i, f in enumerate(top, 1):
        data.append([Paragraph(str(i), ss["Cell"]), Paragraph(f.finding or f.title, ss["Cell"]),
                     Paragraph(anchor_label({"dpdp_anchor": f.dpdp_anchor}), ss["Cell"]),
                     Paragraph(f.severity, ss["Cell"]), Paragraph(f.penalty.max, ss["Cell"]),
                     Paragraph(f.recommendation, ss["Cell"])])
    E.append(_table(data, [7 * mm, 44 * mm, 30 * mm, 15 * mm, 20 * mm, A4[0] - 32 * mm - 116 * mm], ss,
                    align_center_cols=(0, 3))[0])
    top_band = max((f.penalty.max for f in top), key=_band_amt, default="up to 50 crore")
    E.append(Paragraph(f"Highest applicable band across open findings: the Board may impose {top_band} "
                       "under Section 33, after inquiry. This is a ceiling, not an amount owed.", ss["Body"]))
    E.append(PageBreak())

    E.append(Paragraph("2. Scope & Methodology", ss["H1"]))
    E.append(Paragraph(f"Adhikaar crawled the public pages of {rep.url or rep.site}, examined each "
                       "page's forms, embedded third parties and published content, and followed the "
                       "site's links to retrieve and read its privacy policy. Each observation is "
                       "compared against a specific provision of the DPDP Act, 2023 (India Code, Act 22 "
                       "of 2023) and the DPDP Rules, 2025 (Gazette G.S.R. 846(E)). Claims made in the "
                       "policy and behaviour observed on the site are kept as separate, labelled "
                       "evidence.", ss["Body"]))
    E.append(Paragraph("What could not be verified from outside: internal controls such as encryption "
                       "at rest, access logging, staff training and data-processing agreements cannot "
                       "be confirmed by an external scan. These are noted as disclosure-only and are "
                       "not scored as failures.", ss["Body"]))

    E.append(Paragraph("3. Key Findings", ss["H1"]))
    for i, f in enumerate(top, 1):
        E.append(Paragraph(f"{i}. {f.finding or f.title}", ss["H2"]))
        aff = (", ".join(_page_name(u) for u in f.affected_urls[:2])
               if f.affected_urls and "Policy" not in f.affected_urls[0] else "Whole site")
        E.append(Paragraph(f"<b>Severity:</b> {f.severity} &nbsp; <b>DPDP reference:</b> "
                           f"{anchor_label({'dpdp_anchor': f.dpdp_anchor})} &nbsp; <b>Affects:</b> {aff}", ss["Body"]))
        E.append(Paragraph(f"<b>What we found &amp; why it matters:</b> {f.statement} {f.impact}", ss["Body"]))
        E.append(Paragraph(f"<b>Maximum penalty:</b> {f.penalty.max} - the Board may impose this as a "
                           "maximum, after inquiry; not automatic, not summed.", ss["Body"]))
        E.append(Paragraph(f"<b>Recommended action:</b> {f.recommendation}", ss["Body"]))
    E.append(PageBreak())

    E.append(Paragraph("4. Per-Page Assessment", ss["H1"]))
    E.append(Paragraph("Each page is assessed on its own data and behaviour. Whole-site policy gaps "
                       "are addressed once above and are not repeated here.", ss["Body"]))
    E.append(_perpage_table(rep, ss, "page"))
    E.append(PageBreak())

    E.append(Paragraph("5. What the Privacy Notice Must Contain", ss["H1"]))
    if not rep.coverage.get("policy_found"):
        E.append(Paragraph("No privacy notice is published on this site, so there was no document to "
                           "assess. This table is the specification for the notice to be written.", ss["Body"]))
    spec = [_hcells(["DPDP requirement (named)", "What the notice must state"], ss),
            ["Notice - data categories listed (S.5, Rule 3)", "List every data category you collect and why."],
            ["Purpose stated (S.5, S.6(1))", "State a specific purpose per data category."],
            ["Consent - clear, affirmative, withdrawable (S.6)", "Take affirmative consent at each form and offer easy withdrawal."],
            ["Data-principal rights (S.11-S.14)", "Add a concrete route to exercise each right."],
            ["Grievance / DPO contact (S.8(9), S.13)", "Publish the DPO contact and a data-request route on the site."],
            ["Children's data (S.9)", "Enforce verifiable parental consent; never publish minors' records."],
            ["Retention & erasure (S.8(7)-(8), Rule 8)", "Add indicative retention periods per record type."],
            ["Security safeguards (S.8(5), Rule 6)", "Describe the safeguards (encryption, access control)."],
            ["Breach notification (Rule 7)", "Commit to notify affected users and the Board within 72 hours."],
            ["Cross-border transfer (S.16)", "Disclose that some providers process data outside India."],
            ["Cookie / tracker disclosure (Rule 3)", "List the cookies and third-party embeds used."],
            ["Notice is accessible (Rule 3)", "Link the policy from the footer of every page."]]
    E.append(_table(spec, [80 * mm, A4[0] - 32 * mm - 80 * mm], ss)[0])
    E.append(PageBreak())

    # 6. Purpose-of-Collection Guidance
    E.append(Paragraph("6. Purpose-of-Collection Guidance", ss["H1"]))
    E.append(Paragraph("The Act requires collection for a specified purpose and only what that "
                       "purpose needs. Use this table to state, for each collection point, why the "
                       "data is taken and on what lawful basis, and to disclose it in the notice.", ss["Body"]))
    fields, tp = _collect_summary(rep)
    pg = [_hcells(["Where collected", "Personal data", "Purpose to state", "Lawful basis", "What to do"], ss)]
    for r in rep.per_page:
        if r.priority == "High" and r.processes:
            pg.append([r.page + " form", r.processes, "Respond to and process the submission",
                       "Consent", "Add notice + consent; collect only the fields the purpose needs"])
    if tp:
        pg.append(["Analytics / embeds", "IP and device data via third parties",
                   "Website functionality and improvement", "Consent (non-essential)",
                   "Cookie notice + consent before loading non-essential embeds"])
    E.append(_table(pg, [24 * mm, 30 * mm, 38 * mm, 24 * mm, A4[0] - 32 * mm - 116 * mm], ss)[0])
    E.append(PageBreak())

    # 7. Prioritised Action Plan
    E.append(Paragraph("7. Prioritised Action Plan", ss["H1"]))
    for win, sevs in [("Immediate (this week)", ("Critical", "High")),
                      ("Within 30 days", ("Medium",)), ("Within 90 days", ("Low",))]:
        acts = [f for f in rep.findings if f.severity in sevs]
        if not acts:
            continue
        E.append(Paragraph(win, ss["H2"]))
        for f in acts[:8]:
            E.append(Paragraph(f"<b>{f.title}:</b> {f.recommendation}", ss["Body"]))
    E.append(PageBreak())

    # Annex A - Draft Privacy Notice (generated from observed collection points + third parties)
    E.append(Paragraph("Annex A - Draft Privacy Notice", ss["H1"]))
    E.append(Paragraph("Generated from the collection points and third parties this assessment observed "
                       "on the site. It is a starting point that already reflects how the website "
                       "behaves, not legal advice: every square bracket marks something only the "
                       "organisation can supply, and the whole draft should be reviewed before it is "
                       "published.", ss["Body"]))
    fld_phrase = ", ".join(fields) if fields else "personal data you provide"
    tp_phrase = ", ".join(tp) if tp else "third-party analytics and content providers"
    notice = [
        ("Who we are", f"{org} operates this website and decides why and how personal data collected "
                       "through it is processed. Under the Digital Personal Data Protection Act, 2023 "
                       f"this makes us the Data Fiduciary for that data. [Insert the registered office "
                       f"address of {org}.]"),
        ("What personal data we collect", f"Through this website we collect {fld_phrase}. We collect this "
                       "only where you provide it to us, and only the fields needed for the purpose "
                       "described below."),
        ("Why we collect it", "For each form, we collect the fields listed to respond to and process your "
                       "submission (lawful basis: consent). Analytics and embeds collect IP and device "
                       "data via third parties to run and improve the website (lawful basis: consent, "
                       "non-essential)."),
        ("The lawful basis we rely on", "Where the notice records consent, we ask for it by a clear "
                       "affirmative action before collecting the data, and you may withdraw it at any time "
                       "as easily as you gave it. [Confirm which basis applies to each item.]"),
        ("Who receives your data", f"Pages on this website load content and analytics provided by "
                       f"{tp_phrase}. These parties may receive your IP address and information about your "
                       "device and browser when a page loads. [List any other recipient this assessment "
                       "could not see.]"),
        ("How long we keep it", "[State a retention period for each category above, or the event that ends "
                       "it.] When the purpose is served and no law requires us to keep it, the data is erased."),
        ("Your rights", "You may ask us for a summary of the personal data we hold about you; ask us to "
                       "correct, complete, update or erase it; nominate another person to exercise these "
                       "rights on your behalf; and raise a grievance. If you are not satisfied with our "
                       "response, you may complain to the Data Protection Board of India."),
        ("Children", "If we knowingly collect the personal data of anyone under eighteen, we obtain "
                       "verifiable consent from a parent or lawful guardian first, and we do not track, "
                       "behaviourally monitor or direct advertising at children."),
        ("How we protect it", "[Describe the safeguards actually in place - encryption in transit and at "
                       "rest, access control, and logs retained for the period Rule 6 requires.] If a "
                       "personal data breach occurs we will inform you without delay and report it to the "
                       "Data Protection Board within the period the Rules require."),
        ("How to contact us", "[Insert the name or designation and a working e-mail address for the person "
                       "who answers data-protection questions. A generic enquiry form is not sufficient.]"),
        ("Changes to this notice", "We will publish any change to this notice on this page and update the "
                       "date below. [Insert the date of publication.]"),
    ]
    for head, body in notice:
        E.append(Paragraph(head, ss["H2"]))
        E.append(Paragraph(body, ss["Body"]))
    E.append(PageBreak())

    # Appendix B - DPDP references used
    E.append(Paragraph("Appendix B - DPDP references used", ss["H1"]))
    for r in [
        "S.5 - Notice to be given before or with a request for consent.",
        "S.6 - Consent must be free, specific, informed, unconditional and unambiguous, by clear affirmative action, and withdrawable.",
        "S.8 - General obligations of a data fiduciary: accuracy, security safeguards, retention limits, published grievance contact.",
        "S.9 - Children's data: verifiable parental consent; no tracking, behavioural monitoring or targeted ads to children.",
        "S.11-S.14 - Rights of the data principal: access, correction & erasure, grievance redressal, nomination.",
        "S.16 - Transfer of personal data outside India (permitted except to restricted countries).",
        "Rule 3 - Content and accessibility of the notice.",
        "Rule 4 - Consent Manager registration and obligations.",
        "Rule 6 - Reasonable security safeguards.",
        "Rule 7 - Intimation of a personal-data breach (Board within 72 hours, as notified).",
        "Rule 8 - Retention and erasure.",
    ]:
        E.append(Paragraph("\u2022 " + r, ss["Body"]))
    E.append(Paragraph("Sources: DPDP Act, 2023 - India Code, Government of India (Act 22 of 2023). DPDP "
                       "Rules, 2025 - Gazette notification G.S.R. 846(E). Penalty ceilings are from the "
                       "Schedule to the Act and are imposed by the Data Protection Board under Section 33 "
                       "after inquiry.", ss["Body"]))

    # Confidentiality
    E.append(Paragraph("Confidentiality", ss["H1"]))
    E.append(Paragraph(f"This report is prepared for {submitted_to}, {org} and assesses that "
                       "organisation's published disclosures and observable website behaviour. It is "
                       "intended for the addressee and those they choose to share it with, such as their "
                       "data-protection adviser or auditor. It contains no personal data of any individual.", ss["Body"]))
    doc.build(E, canvasmaker=doc._maker)
    return out_path
