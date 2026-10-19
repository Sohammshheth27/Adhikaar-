import os, re, sys, time, csv, glob, json
sys.path.insert(0, r"D:\Adhikaar\backend")
from app.compliance.catalog import CHECKS
from app.compliance.engine import _judge
from app.rag import semantic as S
from app.rag import verify as V

OUT = r"D:\Adhikaar\gold_set"
LOG = os.path.join(OUT, "_ablation.log")

def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S") + " " + m + "\n")
    print(m, flush=True)

HOST_MAP = {
    "jnu_ac_in": "jnu.ac.in", "du_ac_in": "du.ac.in", "iima_ac_in": "iima.ac.in",
    "akshayapatra_org": "akshayapatra.org", "tatatrusts_org": "tatatrusts.org",
    "savethechildren_in": "savethechildren.in", "robu_in": "robu.in",
    "networkintelligence_ai": "networkintelligence.ai", "powersoft_in": "powersoft.in",
}
KEEP = set(HOST_MAP.values())

def load_body(path):
    with open(path, encoding="utf-8") as f:
        c = f.read()
    parts = c.split("\n\n", 1)
    return (parts[1] if len(parts) > 1 else "").strip()

def grounded(v_tuple):
    # evidence-grounding: a verdict backed by a non-empty quote
    return bool(v_tuple[2] and v_tuple[2].strip())

open(LOG, "w").close()
rows = []            # per site x duty: the 3 config verdicts + nli evidence
summary = {c: {"Compliant": 0, "Partial": 0, "Gap": 0, "Not disclosed": 0,
               "Not externally verifiable": 0, "_grounded": 0}
           for c in ("rules", "semantic", "nli")}
timings = {"semantic_build": [], "nli_build": []}
retracted = 0        # semantic-Compliant that NLI pulls back to non-Compliant
upgraded = 0         # semantic non-Compliant that NLI raises to Compliant
n_sites = 0

for path in sorted(glob.glob(os.path.join(OUT, "policy_*.txt"))):
    base = os.path.basename(path)
    m = re.match(r"policy_(edu|ngo|sme)_(.+)\.txt$", base)
    if not m:
        continue
    sec, slug = m.group(1), m.group(2)
    host = HOST_MAP.get(slug)
    if host not in KEEP:
        continue
    text = load_body(path)
    if len(text) < 2000:
        continue
    n_sites += 1
    ptext = text[:60000]
    site_text = text[:40000]
    url = "https://" + host
    try:
        signals = V.structural_signals(ptext, [url], text)
    except Exception as e:
        signals = {}
        log("  signals ERR %s :: %s" % (host, str(e)[:70]))
    signals["is_https"] = True

    t0 = time.perf_counter()
    sem_semantic = S.judge_all(site_text) if S.available() else {}
    timings["semantic_build"].append(time.perf_counter() - t0)

    t0 = time.perf_counter()
    try:
        raw = V.judge_all_verified(site_text, signals) if V.nli_available() else {}
        sem_nli = {cid: (v, s, ev) for cid, (v, s, ev, _r) in raw.items()}
    except Exception as e:
        sem_nli = {}
        log("  NLI ERR %s :: %s" % (host, str(e)[:70]))
    timings["nli_build"].append(time.perf_counter() - t0)

    for ch in CHECKS:
        cid = ch["id"]
        vr = _judge(ch, ptext, True, None)
        vs = _judge(ch, ptext, True, sem_semantic.get(cid))
        vn = _judge(ch, ptext, True, sem_nli.get(cid))
        for cfg, vt in (("rules", vr), ("semantic", vs), ("nli", vn)):
            summary[cfg][vt[0]] = summary[cfg].get(vt[0], 0) + 1
            if grounded(vt):
                summary[cfg]["_grounded"] += 1
        if vs[0] == "Compliant" and vn[0] != "Compliant":
            retracted += 1
        if vs[0] != "Compliant" and vn[0] == "Compliant":
            upgraded += 1
        rows.append({"site": host, "sector": sec, "duty_id": cid,
                     "verdict_rules": vr[0], "verdict_semantic": vs[0], "verdict_nli": vn[0],
                     "conf_nli": round(vn[1], 2), "evidence_nli": (vn[2] or "")[:300]})
    log("done %s (%d chars)" % (host, len(text)))

# write per-duty config verdicts (join key for accuracy once labels arrive)
with open(os.path.join(OUT, "config_verdicts.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["site", "sector", "duty_id", "verdict_rules",
                                      "verdict_semantic", "verdict_nli", "conf_nli", "evidence_nli"])
    w.writeheader()
    for r in rows:
        w.writerow(r)

total = n_sites * len(CHECKS)
def pct(x):
    return round(100.0 * x / total, 1) if total else 0.0
rep = {
    "n_sites": n_sites, "n_duties": len(CHECKS), "total_judgements": total,
    "verdict_distribution": {c: {k: v for k, v in summary[c].items() if k != "_grounded"} for c in summary},
    "evidence_grounding_rate_pct": {c: pct(summary[c]["_grounded"]) for c in summary},
    "nli_vs_semantic": {"retracted_compliant": retracted, "upgraded_to_compliant": upgraded},
    "latency_sec_per_site": {
        "semantic_build_mean": round(sum(timings["semantic_build"]) / max(1, len(timings["semantic_build"])), 2),
        "nli_build_mean": round(sum(timings["nli_build"]) / max(1, len(timings["nli_build"])), 2),
    },
    "note": "Behaviour deltas only; no human labels used. LLM judge OFF (optional overlay). "
            "Accuracy (P/R/F1, macro-F1, FPR) computes after gold_labels are filled, joining on site+duty_id.",
}
with open(os.path.join(OUT, "ablation_summary.json"), "w", encoding="utf-8") as f:
    json.dump(rep, f, indent=2)
log("ABLATION DONE: %d sites x %d duties = %d judgements/config" % (n_sites, len(CHECKS), total))
log(json.dumps(rep, indent=2))
