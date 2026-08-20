"""
adhikaar_iterate.py -- convergence harness. Crawl once (cached), then repeatedly score+render and
diff against the reference reports until they match.

    python adhikaar_iterate.py crawl        # live-crawl cyberpeace.org -> crawl_cache.json (do once)
    python adhikaar_iterate.py compare      # load cache -> engine -> render -> gap report vs reference
"""
from __future__ import annotations
import sys, json, re
from pathlib import Path

from app.compliance import crawler, exposure
from app.compliance.engine import compliance_report
from app.compliance.report_render import render_compliance, render_recommendation

HERE = Path(__file__).resolve().parent
CACHE = HERE.parent / "_reference" / "crawl_cyberpeace.json"
REF_C = HERE.parent / "_reference" / "compliance.txt"
URL = "https://cyberpeace.org"
ORG = "CyberPeace Foundation"

# Ground truth from your reference Compliance report:
REF = {"grade": "E", "adequacy": 0.02, "findings": 46, "met": 1,
       "Critical": 0, "High": 15, "Medium": 9, "Low": 22, "Info": 0,
       "platform": "Webflow", "pages": 5, "policy_found": False}


def do_crawl():
    shots = str(HERE.parent / "_shots" / "cyberpeace")
    crawl = crawler.crawl(URL, budget=12, screenshot_dir=shots)
    try:
        crawl["exposure"] = exposure.probe(URL)
    except Exception as e:
        crawl["exposure"] = []; print("exposure skipped:", e)
    # drop html to keep the cache lean; keep text
    for p in crawl["pages"]:
        p.pop("html", None)
    CACHE.write_text(json.dumps(crawl, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"cached {len(crawl['pages'])} pages, platform={crawl['platform']}, "
          f"policy_found={crawl['policy_found']}, archived={bool(crawl['archived_policy'])}, "
          f"trackers={[t['name'] for t in crawl['trackers']]}")


def do_compare():
    crawl = json.loads(CACHE.read_text(encoding="utf-8"))
    site = "cyberpeace.org"
    # archive.org can time out mid-crawl; backfill it here so iteration doesn't need a re-crawl
    if not crawl.get("policy_found") and not crawl.get("archived_policy"):
        crawl["archived_policy"] = crawler.archive_policy(site)
        CACHE.write_text(json.dumps(crawl, ensure_ascii=False, indent=1), encoding="utf-8")
    rep = compliance_report(url=URL, pages=crawl["pages"], exposure_findings=crawl.get("exposure", []),
                            is_https=True, site=site, page_budget=12,
                            platform=crawl.get("platform", "Unknown"),
                            archived_policy=crawl.get("archived_policy"),
                            policy_found=crawl.get("policy_found"),
                            subdomains=crawl.get("subdomains"))
    rep.tracker_inventory = crawl.get("trackers", [])
    rep.cookie_inventory = crawl.get("cookies", [])
    o = rep.overall
    got = {"grade": o.grade, "adequacy": o.adequacy, "findings": len(rep.findings),
           "met": o.counts.get("Requirements met", 0),
           "Critical": o.counts.get("Critical", 0), "High": o.counts.get("High", 0),
           "Medium": o.counts.get("Medium", 0), "Low": o.counts.get("Low", 0),
           "Info": o.counts.get("Info", 0), "platform": crawl.get("platform"),
           "pages": len(crawl["pages"]), "policy_found": crawl.get("policy_found")}

    print("metric           reference     mine        match")
    print("-" * 52)
    ok = 0
    for k in REF:
        m = "OK " if got.get(k) == REF[k] else "XX "
        ok += got.get(k) == REF[k]
        print(f"{k:15s} {str(REF[k]):12s} {str(got.get(k)):11s} {m}")
    print("-" * 52)
    print(f"metrics matching: {ok}/{len(REF)}")

    # render + save so wording can be diffed
    out = HERE.parent / "examples"
    (out / "CyberPeace-Foundation-Compliance.md").write_text(
        render_compliance(rep, org=ORG), encoding="utf-8")
    (out / "CyberPeace-Foundation-Recommendation.md").write_text(
        render_recommendation(rep, org=ORG), encoding="utf-8")
    # PDFs
    from app.compliance.pdf_render import build_compliance_pdf, build_recommendation_pdf
    cp = build_compliance_pdf(rep, org=ORG, out_path=str(out / "CyberPeace-Foundation-Compliance.pdf"))
    rp = build_recommendation_pdf(rep, org=ORG, out_path=str(out / "CyberPeace-Foundation-Recommendation.pdf"))
    print(f"PDFs: {cp} , {rp}")

    # quick wording check: are the 'finding' phrasings present in the reference text?
    ref = REF_C.read_text(encoding="utf-8", errors="ignore").lower()
    miss = [f.finding for f in rep.findings if f.finding and f.finding.lower()[:35] not in ref]
    if miss:
        print(f"\nfinding wordings NOT found verbatim in reference ({len(miss)}):")
        for m in miss[:12]:
            print("  -", m)
    else:
        print("\nall finding wordings appear in the reference text.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "compare"
    (do_crawl if cmd == "crawl" else do_compare)()
