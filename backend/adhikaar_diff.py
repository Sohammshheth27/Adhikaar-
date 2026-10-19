"""
adhikaar_diff.py -- compare two Adhikaar assessments of the same site over time and report what changed.

    python adhikaar_diff.py old/report.json new/report.json

Reads two report JSONs (written by adhikaar_scan.py / adhikaar_batch.py) and prints the grade/adequacy movement,
which findings were resolved, which are new, and which severities changed.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def by_id(rep):
    out = {}
    for f in rep.get("findings", []):
        m = re.match(r"(c\d+)-", f.get("id", ""))
        out[m.group(1) if m else f.get("id")] = f
    return out


def main():
    ap = argparse.ArgumentParser(description="Diff two Adhikaar assessments")
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--out", default=None, help="Optional Markdown output path")
    args = ap.parse_args()

    a, b = load(args.old), load(args.new)
    oa, ob = a["overall"], b["overall"]
    fa, fb = by_id(a), by_id(b)

    resolved = [fa[k] for k in fa if k not in fb]
    added = [fb[k] for k in fb if k not in fa]
    changed = [(fa[k], fb[k]) for k in fa if k in fb and fa[k]["severity"] != fb[k]["severity"]]

    L = []
    L.append(f"# Adhikaar Re-assessment Diff — {b.get('site','')}")
    L.append(f"\n**Grade:** {oa['grade']} -> {ob['grade']}  |  "
             f"**Adequacy:** {oa['adequacy']:.2f} -> {ob['adequacy']:.2f}  |  "
             f"**Findings:** {len(a['findings'])} -> {len(b['findings'])}")
    delta = ob["adequacy"] - oa["adequacy"]
    L.append(f"**Net movement:** {'improved' if delta > 0 else 'worse' if delta < 0 else 'no change'} "
             f"({delta:+.2f} adequacy).\n")

    L.append(f"## Resolved ({len(resolved)})")
    for f in resolved:
        L.append(f"- [resolved] {f.get('finding') or f.get('title')} ({f['severity']})")
    L.append(f"\n## New ({len(added)})")
    for f in added:
        L.append(f"- [new] {f.get('finding') or f.get('title')} ({f['severity']})")
    L.append(f"\n## Severity changed ({len(changed)})")
    for old, new in changed:
        L.append(f"- {old.get('finding') or old.get('title')}: {old['severity']} -> {new['severity']}")

    report = "\n".join(L)
    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
