"""
build_corpus.py -- build a fine-tuning corpus from REAL privacy policies (no synthetic text).

For each real site, crawl its policy, have the LLM judge label every duty with the verbatim evidence
sentence, and emit (sentence, duty_id, label) training pairs:
  * positive: the evidence sentence for a duty the policy discloses;
  * negatives: that same sentence paired with OTHER duties, plus other policy sentences for the duty.

    ADHIKAAR_LLM_JUDGE=1  ADHIKAAR_LLM_API_KEY=...  python build_corpus.py sites.txt --out corpus.jsonl

sites.txt: one URL per line (site or a direct policy URL). Uses your API key only to LABEL real text.
"""
from __future__ import annotations
import argparse
import json
import random
import re
from pathlib import Path

from app.compliance import crawler
from app.compliance.catalog import CHECKS
from app.rag import llm_judge


def _text_from(cr: dict) -> str:
    pages = cr.get("pages", [])
    return "\n\n".join(p.get("text", "") for p in pages if p.get("is_policy")) or \
           "\n\n".join(p.get("text", "") for p in pages)


def _policy_text(url: str) -> str:
    # Browser crawl first (JS-rendered policies), fall back to plain httpx.
    for fn, kw in ((crawler.crawl, {"budget": 8}), (crawler.crawl_static, {"budget": 8})):
        try:
            txt = _text_from(fn(url, **kw))
            if txt.strip():
                return txt
        except Exception:
            continue
    return ""


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [re.sub(r"\s+", " ", p).strip() for p in parts if 15 <= len(p.strip()) <= 400]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sites")
    ap.add_argument("--out", default="corpus.jsonl")
    ap.add_argument("--neg-per-pos", type=int, default=3)
    args = ap.parse_args()

    if not llm_judge.enabled():
        print("Set ADHIKAAR_LLM_JUDGE=1 and ADHIKAAR_LLM_API_KEY to label real policies."); return

    ids = [c["id"] for c in CHECKS]
    rows = []
    urls = [u.strip() for u in Path(args.sites).read_text(encoding="utf-8").splitlines()
            if u.strip() and not u.startswith("#")]
    outp = Path(args.out)
    for i, url in enumerate(urls, 1):
        try:
            text = _policy_text(url if url.startswith("http") else "https://" + url)
        except Exception as e:
            print(f"[{i}/{len(urls)}] {url}: crawl failed ({type(e).__name__})"); continue
        if not text.strip():
            print(f"[{i}/{len(urls)}] {url}: no policy text"); continue
        try:
            labels = llm_judge.judge_policy(text)                  # {id: (verdict, evidence)}
        except Exception as e:
            print(f"[{i}/{len(urls)}] {url}: label failed ({type(e).__name__}) -- skipped"); continue
        sents = _sentences(text)
        n_pos = 0
        for cid, (verdict, ev) in labels.items():
            if verdict in ("Compliant", "Partial") and ev:
                rows.append({"sentence": ev, "duty": cid, "label": 1, "url": url})
                n_pos += 1
                # hard negatives: same sentence vs other duties
                for other in random.sample([d for d in ids if d != cid], args.neg_per_pos):
                    rows.append({"sentence": ev, "duty": other, "label": 0, "url": url})
                # negatives: other policy sentences vs this duty
                for s in random.sample(sents, min(args.neg_per_pos, len(sents))):
                    if s != ev:
                        rows.append({"sentence": s, "duty": cid, "label": 0, "url": url})
        print(f"[{i}/{len(urls)}] {url}: {n_pos} disclosed duties -> pairs so far {len(rows)}")
        with outp.open("w", encoding="utf-8") as f:                # flush after each policy
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        import time as _t
        _t.sleep(4)                                                # pace requests under the rate cap

    with Path(args.out).open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    pos = sum(1 for r in rows if r["label"] == 1)
    print(f"\nwrote {args.out}: {len(rows)} pairs ({pos} positive) from {len(urls)} real policies")


if __name__ == "__main__":
    main()
