import os, re, csv, json, time, io, sys
import httpx
sys.path.insert(0, r"D:\Adhikaar\backend")
from app.compliance.catalog import CHECKS
from app.rag import semantic as S
import importlib.util
spec = importlib.util.spec_from_file_location("llm_run_rag", r"D:\Adhikaar\llm_run_rag.py")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
OUT = r"D:\Adhikaar\gold_set"

env = {}
with open(r"D:\Adhikaar\backend\.llm_env", encoding="utf-8") as f:
    for line in f:
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1); env[k] = v
URL = env["ADHIKAAR_LLM_BASE_URL"].rstrip("/") + "/chat/completions"
KEY = env["ADHIKAAR_LLM_API_KEY"]; MODEL = env["ADHIKAAR_LLM_MODEL"]

def anchor(c):
    a = c.get("dpdp_anchor") or {}
    p = []
    if a.get("rule"): p.append(a["rule"])
    if a.get("act_section"): p.append("Act " + a["act_section"])
    return "; ".join(p)
DUTY_BLOCK = "\n".join(f'{c["id"]}. {c["requirement"]} [anchor: {anchor(c) or "DPDP"}]' for c in CHECKS)
SYSTEM = ("You are an experienced Data Protection Officer auditing a PUBLISHED privacy notice against "
          "India's DPDP Act 2023 and DPDP Rules 2025. Judge ONLY from the policy text. Never invent a quote. "
          "Verdicts: Compliant (clear concrete commitment), Partial (addressed but vague/incomplete), "
          "Gap (expected but absent), NotVerifiable (internal control unconfirmable from public text). "
          "For Compliant/Partial give the single VERBATIM sentence; else empty. STRICT JSON only. "
          "Keep each evidence sentence short.")

def big_sentences(text, cap=4000):
    out, seen = [], set()
    for p in re.split(r"(?<=[.!?])\s+|\n+|•|\|", text or ""):
        p = re.sub(r"\s+", " ", p).strip()
        if 15 <= len(p) <= 400 and p.lower() not in seen:
            seen.add(p.lower()); out.append(p)
        if len(out) >= cap: break
    return out

def digest(text, topk=4, floor=0.22):
    from sentence_transformers import util
    sents = big_sentences(text)
    model = S._model()
    emb = model.encode(sents, convert_to_tensor=True, normalize_embeddings=True, batch_size=128)
    chosen = set()
    for cid, ex in S._EX_EMB.items():
        col = util.cos_sim(ex, emb).max(dim=0).values
        for j in col.argsort(descending=True).tolist()[:topk]:
            if float(col[j]) >= floor: chosen.add(j)
    return "\n".join(sents[j] for j in sorted(chosen))[:24000]

def salvage(txt):
    """Robust parse: json first, then regex-extract complete entries from (even truncated) output."""
    out = {}
    s = re.sub(r"^```(json)?|```$", "", (txt or "").strip(), flags=re.I | re.M).strip()
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        try:
            for k, v in json.loads(s[i:j + 1]).items():
                cid = int(re.sub(r"\D", "", str(k)))
                out[cid] = (str(v.get("verdict", "")).strip(), str(v.get("evidence", "")).strip())
            return out
        except Exception:
            pass
    for mm in re.finditer(r'"(\d+)"\s*:\s*\{\s*"verdict"\s*:\s*"([^"]+)"\s*,\s*"evidence"\s*:\s*"((?:[^"\\]|\\.)*)"', s):
        out[int(mm.group(1))] = (mm.group(2).strip(), mm.group(3).strip())
    return out

def load_body(p):
    c = open(p, encoding="utf-8").read(); return (c.split("\n\n", 1)[1] if "\n\n" in c else c).strip()

text = load_body(os.path.join(OUT, "policy_ngo_akshayapatra_org.txt"))
ctx = digest(text)
body = {"model": MODEL, "temperature": 0, "max_tokens": 9000,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": "Requirements:\n" + DUTY_BLOCK +
                      "\n\nRelevant policy passages:\n\"\"\"\n" + ctx + "\n\"\"\"\n\n"
                      'JSON mapping each id (string) to {"verdict":...,"evidence":...}. All 47 ids. JSON only.'}]}
r = httpx.post(URL, headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, json=body, timeout=120.0)
print("HTTP", r.status_code)
txt = r.json()["choices"][0]["message"]["content"]
v = salvage(txt)
print("parsed", len(v), "/47 ; raw len", len(txt))
lowtext = re.sub(r"\s+", " ", text.lower())
newrows = {}
for c in CHECKS:
    vv, ev = v.get(c["id"], ("Gap", ""))
    if vv not in ("Compliant", "Partial", "Gap", "NotVerifiable"):
        vv = {"Not disclosed": "Gap", "Not externally verifiable": "NotVerifiable"}.get(vv, "Gap")
    gr = ""
    if vv in ("Compliant", "Partial") and len(ev) > 15:
        gr = "yes" if re.sub(r"\s+", " ", ev.lower())[:60] in lowtext else "no"
    newrows[c["id"]] = {"site": "akshayapatra.org", "duty_id": c["id"], "verdict_llm": vv,
                        "evidence_llm": ev[:300], "quote_grounded": gr}

# splice into llm_rag_verdicts.csv
path = os.path.join(OUT, "llm_rag_verdicts.csv")
allrows = list(csv.DictReader(open(path, encoding="utf-8")))
for row in allrows:
    if row["site"] == "akshayapatra.org":
        nr = newrows[int(row["duty_id"])]
        row["verdict_llm"] = nr["verdict_llm"]; row["evidence_llm"] = nr["evidence_llm"]; row["quote_grounded"] = nr["quote_grounded"]
with open(path, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["site", "duty_id", "verdict_llm", "evidence_llm", "quote_grounded"])
    w.writeheader()
    for row in allrows: w.writerow(row)
import collections
print("akshaya new dist:", dict(collections.Counter(newrows[c["id"]]["verdict_llm"] for c in CHECKS)))
print("spliced OK")
