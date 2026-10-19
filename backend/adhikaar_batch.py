"""
adhikaar_batch.py -- portfolio mode. Assess a list of sites and emit per-site reports plus a
cross-site summary (CSV + Markdown), for auditing a sector or a research campaign.

    python adhikaar_batch.py sites.txt --out ../examples/portfolio [--static] [--budget 12]

sites.txt: one entry per line, "url" or "url,Org Name". Blank lines and # comments ignored.
"""
from __future__ import annotations
import argparse
import csv
import re
from pathlib import Path

from app.compliance import crawler, exposure
from app.compliance.engine import compliance_report
from app.compliance.report_render import render_compliance, render_recommendation

try:
    from app.compliance.pdf_render import build_compliance_pdf, build_recommendation_pdf
    _PDF = True
except Exception:
    _PDF = False


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-") or "site"


def assess_one(url, org, budget, static):
    try:
        cr = crawler.crawl_static(url, budget) if static else crawler.crawl(url, budget)
    except Exception:
        cr = crawler.crawl_static(url, budget)
    try:
        exp = exposure.probe(url)
    except Exception:
        exp = []
    site = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    rep = compliance_report(url=url, pages=cr["pages"], exposure_findings=exp,
                            is_https=url.startswith("https"), site=site, page_budget=budget,
                            platform=cr.get("platform", "Unknown"),
                            archived_policy=cr.get("archived_policy"),
                            policy_found=cr.get("policy_found"),
                            subdomains=cr.get("subdomains"))
    rep.tracker_inventory = cr.get("trackers", [])
    rep.cookie_inventory = cr.get("cookies", [])
    return rep, org or site


def main():
    ap = argparse.ArgumentParser(description="Adhikaar portfolio assessment")
    ap.add_argument("sites")
    ap.add_argument("--out", default="portfolio")
    ap.add_argument("--budget", type=int, default=12)
    ap.add_argument("--static", action="store_true")
    args = ap.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    rows = []
    entries = []
    for ln in Path(args.sites).read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = [p.strip() for p in ln.split(",", 1)]
        url = parts[0] if parts[0].startswith("http") else "https://" + parts[0]
        entries.append((url, parts[1] if len(parts) > 1 else None))

    print(f"assessing {len(entries)} site(s) ...")
    for i, (url, org) in enumerate(entries, 1):
        try:
            rep, name = assess_one(url, org, args.budget, args.static)
        except Exception as e:
            print(f"[{i}/{len(entries)}] {url}: ERROR {e}")
            rows.append({"site": url, "org": org or "", "grade": "ERR", "adequacy": "",
                         "findings": "", "high": "", "exposure": "", "trackers": ""})
            continue
        o = rep.overall
        d = out / slug(name)
        d.mkdir(exist_ok=True)
        (d / "Compliance.md").write_text(render_compliance(rep, org=name), encoding="utf-8")
        (d / "report.json").write_text(rep.model_dump_json(indent=1), encoding="utf-8")
        if _PDF:
            build_compliance_pdf(rep, org=name, out_path=str(d / "Compliance.pdf"))
            build_recommendation_pdf(rep, org=name, out_path=str(d / "Recommendation.pdf"))
        rows.append({"site": rep.site, "org": name, "grade": o.grade,
                     "adequacy": o.adequacy, "findings": len(rep.findings),
                     "high": o.counts.get("High", 0), "exposure": len(rep.exposure),
                     "trackers": len(rep.tracker_inventory)})
        print(f"[{i}/{len(entries)}] {rep.site}: grade {o.grade} ({o.adequacy:.2f}), "
              f"{len(rep.findings)} findings, {len(rep.exposure)} exposure")

    # portfolio summary
    with (out / "portfolio.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["site", "org", "grade", "adequacy", "findings", "high", "exposure", "trackers"])
        w.writeheader(); w.writerows(rows)
    graded = [r for r in rows if r["grade"] not in ("ERR", "")]
    from collections import Counter
    dist = Counter(r["grade"] for r in graded)
    md = ["# Adhikaar Portfolio Summary\n",
          f"{len(graded)} site(s) assessed. Grade distribution: "
          + ", ".join(f"{g} {dist.get(g,0)}" for g in "ABCDE") + ".\n",
          f"Sites with an exposure finding: {sum(1 for r in graded if r['exposure'])}.\n",
          "| Site | Grade | Adequacy | Findings | High | Exposure | Trackers |",
          "|---|---|---|---|---|---|---|"]
    for r in sorted(graded, key=lambda x: str(x["grade"])):
        md.append(f"| {r['org']} ({r['site']}) | {r['grade']} | {r['adequacy']} | {r['findings']} "
                  f"| {r['high']} | {r['exposure']} | {r['trackers']} |")
    (out / "portfolio.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nwrote {out/'portfolio.csv'} and {out/'portfolio.md'}")


if __name__ == "__main__":
    main()
