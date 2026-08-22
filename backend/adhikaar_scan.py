"""
adhikaar_scan.py -- one-shot Adhikaar DPDP assessment: crawl -> probe exposure -> score -> report.

Usage:
    python adhikaar_scan.py https://example.org --org "Example Foundation" --out D:/Adhikaar/examples
    python adhikaar_scan.py https://example.org --static      # no-JS httpx fallback (no Playwright)

Produces <org>-Compliance.md and <org>-Recommendation.md in the output directory.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

from app.compliance import crawler, exposure
from app.compliance.engine import compliance_report
from app.compliance.report_render import render_compliance, render_recommendation


def slugify(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-") or "site"


def main():
    ap = argparse.ArgumentParser(description="Adhikaar DPDP assessment")
    ap.add_argument("url")
    ap.add_argument("--org", default=None, help="Organisation name for the report cover")
    ap.add_argument("--out", default=".", help="Output directory")
    ap.add_argument("--budget", type=int, default=12, help="Page budget")
    ap.add_argument("--static", action="store_true", help="Use httpx fallback (no JS render)")
    ap.add_argument("--fuzz", action="store_true", help="Discover subdomains via a wordlist (opt-in)")
    ap.add_argument("--no-exposure", action="store_true", help="Skip the exposure probe")
    args = ap.parse_args()

    print(f"[1/4] Crawling {args.url} (budget {args.budget}) ...")
    try:
        shots = str(Path(args.out) / "_shots" / slugify(args.org or "site"))
        crawl = crawler.crawl_static(args.url, args.budget) if args.static \
            else crawler.crawl(args.url, args.budget, screenshot_dir=shots, fuzz=args.fuzz)
    except Exception as e:
        print(f"  Playwright crawl failed ({e}); falling back to static fetch.")
        crawl = crawler.crawl_static(args.url, args.budget)
    if not crawl.get("pages") and not args.static:
        print("  Browser crawl returned no pages (site may block automation); using static fetch.")
        crawl = crawler.crawl_static(args.url, args.budget)
    pages = crawl["pages"]
    print(f"      {len(pages)} page(s) rendered; {len(crawl.get('trackers', []))} tracker(s) seen.")

    exp = []
    if not args.no_exposure:
        print("[2/4] Probing for exposed files (signal-only) ...")
        try:
            exp = exposure.probe(args.url, pages=crawl.get("pages"), subdomains=crawl.get("subdomains"))
        except Exception as e:
            print(f"      exposure probe skipped: {e}")
    print(f"      {len(exp)} exposure finding(s).")

    print("[3/4] Scoring against the 47 DPDP requirements ...")
    site = re.sub(r"^https?://(www\.)?", "", args.url).split("/")[0]
    is_https = args.url.startswith("https")
    rep = compliance_report(url=args.url, pages=pages, exposure_findings=exp,
                            is_https=is_https, site=site, page_budget=args.budget,
                            platform=crawl.get("platform", "Unknown"),
                            archived_policy=crawl.get("archived_policy"),
                            policy_found=crawl.get("policy_found"),
                            subdomains=crawl.get("subdomains"),
                            sec_headers=crawl.get("sec_headers"))
    rep.tracker_inventory = crawl.get("trackers", [])
    rep.cookie_inventory = crawl.get("cookies", [])
    print(f"      Grade {rep.overall.grade} (adequacy {rep.overall.adequacy:.2f}); "
          f"{len(rep.findings)} finding(s).")

    print("[4/4] Rendering reports (Markdown + PDF) ...")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    name = slugify(args.org or site)
    (out / f"{name}-Compliance.md").write_text(render_compliance(rep, org=args.org), encoding="utf-8")
    (out / f"{name}-Recommendation.md").write_text(render_recommendation(rep, org=args.org), encoding="utf-8")
    (out / f"{name}-report.json").write_text(rep.model_dump_json(indent=1), encoding="utf-8")
    try:
        from app.compliance.pdf_render import build_compliance_pdf, build_recommendation_pdf
        build_compliance_pdf(rep, org=args.org, out_path=str(out / f"{name}-Compliance.pdf"))
        build_recommendation_pdf(rep, org=args.org, out_path=str(out / f"{name}-Recommendation.pdf"))
        print(f"      wrote {name}-Compliance.pdf / .md and {name}-Recommendation.pdf / .md in {out}")
    except Exception as e:
        print(f"      Markdown written; PDF step skipped ({e}). pip install reportlab to enable.")


if __name__ == "__main__":
    main()
