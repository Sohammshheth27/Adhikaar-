"""
run_pipeline.py <url> -- the full Adhikaar pipeline, end to end:
  CRAWLER (discovery + render)  ->  SCRAPER (all pages + docs -> clean corpus)
    ->  RAG (semantic mapping of the corpus to each requirement, with evidence)
    ->  COMPLIANCE (score + grade) + IT-Act(in force) vs DPDP(2027) breakdown.
"""
import os, sys, re, json
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", r"E:\ms-playwright")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, r"D:\Adhikaar\backend")

from app.compliance import crawler, scraper, exposure               # noqa: E402
from app.compliance.engine import compliance_report                 # noqa: E402
from app.compliance.catalog import CHECKS                           # noqa: E402
from app.rag import semantic                                        # noqa: E402

LAW = json.load(open(r"E:\Adhikar_RECOVERED\research\paper\validation\law_map.json", encoding="utf-8"))
SPDI = {int(k) for k, v in LAW.items() if v["law_source"].startswith("IT Act")}
W = {"Compliant": 1.0, "Not externally verifiable": 0.75, "Partial": 0.5, "Not disclosed": 0.0, "Gap": 0.0}
_SLUG = re.compile(r"^c(\d+)-")
CATN = {c["id"]: c["requirement"] for c in CHECKS}


def run(url):
    print(f"[1/4] CRAWLER: discovery + render  {url}", flush=True)
    crawl = crawler.crawl(url, 20)
    pages = crawl.get("pages", [])
    print(f"      {len(pages)} pages rendered, {len(crawl.get('subdomains', []))} subdomains", flush=True)

    print("[2/4] SCRAPER: extract all pages + documents -> clean corpus", flush=True)
    corpus = scraper.scrape_site(pages)
    kinds = {}
    for c in corpus:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    total = sum(len(c["text"]) for c in corpus)
    print(f"      corpus: {len(corpus)} resources {kinds}, {total} chars clean text", flush=True)

    print(f"[3/4] RAG: semantic mapping to provisions (available={semantic.available()})", flush=True)
    corpus_text = "\n\n".join(c["text"] for c in corpus if c.get("text"))
    sem_ev = semantic.judge_all(corpus_text) if semantic.available() else {}
    eng_pages = [{"url": c["url"], "text": c["text"], "html": "", "is_policy": True}
                 for c in corpus if len(c.get("text", "")) >= 50]
    exp = []
    try:
        exp = exposure.probe(url, pages=pages, subdomains=crawl.get("subdomains"))
    except Exception:
        pass
    site = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    rep = compliance_report(url=url, pages=eng_pages, exposure_findings=exp,
                            is_https=url.startswith("https"), site=site, page_budget=20,
                            policy_found=any(len(c.get("text", "")) > 800 for c in corpus), observed_tech={})
    d = rep.model_dump(mode="json"); ov = d.get("overall") or {}
    findings = d.get("findings") or []
    print("[4/4] scored.\n", flush=True)

    verdict, quote = {}, {}
    for f in findings:
        m = _SLUG.match(f.get("id") or "")
        if m:
            verdict[int(m.group(1))] = f.get("verdict")
            quote[int(m.group(1))] = (f.get("evidence") or {}).get("policy_quote", "")
    for c in CHECKS:
        verdict.setdefault(c["id"], "Compliant")
        rag = sem_ev.get(c["id"])
        if rag and rag[2] and not quote.get(c["id"]):
            quote[c["id"]] = rag[2]                    # RAG-retrieved evidence sentence

    has_policy = verdict.get(33) == "Compliant"; https = verdict.get(38) == "Compliant"
    exposure_found = bool(exp)
    it_violation = (not has_policy) or exposure_found or (not https)
    in_force = sum(W.get(verdict[i], 0.0) for i in SPDI) / len(SPDI)

    print("=" * 66)
    print(f"  ADHIKAAR SCORE  --  {url}")
    print("=" * 66)
    print(f"  Grade: {ov.get('grade')}   DPDP readiness (adequacy): {ov.get('adequacy')}  ({int((ov.get('adequacy') or 0)*100)}% of 47 duties)")
    print(f"  Privacy policy present: {'YES' if has_policy else 'NO'}   HTTPS: {'yes' if https else 'no'}   data exposure: {'YES' if exposure_found else 'no'}")
    print(f"  IN-FORCE IT Act / SPDI 2011 adherence: {int(in_force*100)}%   -> {'VIOLATES the in-force law today' if it_violation else 'meets the in-force minimum'}")
    print(f"  DPDP Act 2023 (from 2027) readiness: {int((ov.get('adequacy') or 0)*100)}%")
    met = sum(1 for c in CHECKS if verdict[c['id']] == 'Compliant')
    print(f"  Duties met: {met}/47")
    print("\n  Sample evidence (disclosed duties, RAG-retrieved quote):")
    shown = 0
    for c in CHECKS:
        i = c["id"]
        if verdict[i] == "Compliant" and quote.get(i) and shown < 6:
            print(f"    #{i} {CATN[i][:44]}: \"{quote[i][:90]}\"")
            shown += 1
    print("\n  Top gaps (in-force IT Act duties not met):")
    for i in sorted(SPDI):
        if verdict[i] != "Compliant":
            print(f"    #{i} [{LAW[str(i)]['law_source'].split(' (')[0]}] {CATN[i][:50]} -> {verdict[i]}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "https://www.tataneu.com/")
