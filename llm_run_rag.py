import os, re, csv, glob, json, time, io, sys
import httpx
sys.path.insert(0, r"D:\Adhikaar\backend")
from app.compliance.catalog import CHECKS
from app.rag import semantic as S
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

OUT = r"D:\Adhikaar\gold_set"
env = {}
with open(r"D:\Adhikaar\backend\.llm_env", encoding="utf-8") as f:
    for line in f:
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1); env[k] = v
URL = env["ADHIKAAR_LLM_BASE_URL"].rstrip("/") + "/chat/completions"
KEY = env["ADHIKAAR_LLM_API_KEY"]; MODEL = env["ADHIKAAR_LLM_MODEL"]

HOST_MAP = {
    "jnu_ac_in": "jnu.ac.in", "du_ac_in": "du.ac.in", "iima_ac_in": "iima.ac.in",
    "akshayapatra_org": "akshayapatra.org", "tatatrusts_org": "tatatrusts.org",
    "savethechildren_in": "savethechildren.in", "robu_in": "robu.in",
    "networkintelligence_ai": "networkintelligence.ai", "powersoft_in": "powersoft.in",
}

def anchor(c):
    a = c.get("dpdp_anchor") or {}
    p = []
    if a.get("rule"): p.append(a["rule"])
    if a.get("act_section"): p.append("Act " + a["act_section"])
    return "; ".join(p)

DUTY_BLOCK = "\n".join(f'{c["id"]}. {c["requirement"]} [anchor: {anchor(c) or "DPDP"}]' for c in CHECKS)

SYSTEM = (
    "You are an experienced Data Protection Officer auditing an organisation's PUBLISHED privacy "
    "notice against India's DPDP Act 2023 and DPDP Rules 2025. Judge ONLY from the policy text "
    "provided. Never infer a disclosure that is not present; never invent a quote. For each "
    "requirement assign exactly one verdict:\n"
    "  Compliant   = the policy CLEARLY COMMITS to / satisfies the requirement (a specific, concrete "
    "statement, not a vague gesture).\n"
    "  Partial     = the topic is ADDRESSED but the statement is vague, incomplete, or conditional.\n"
    "  Gap         = the requirement is expected but is ABSENT from the policy.\n"
    "  NotVerifiable = an INTERNAL control (e.g. staff training, internal audits, security measures) "
    "that cannot be confirmed from public policy text.\n"
    "For Compliant or Partial, give the single most relevant VERBATIM sentence copied exactly from "
    "the policy; otherwise empty. Output STRICT JSON only, no markdown, no prose."
)

def build_user(ctx):
    return ("Requirements (id. text [anchor]):\n" + DUTY_BLOCK +
            "\n\nMost relevant policy passages (retrieved from the full policy):\n\"\"\"\n" + ctx[:24000] +
            "\n\"\"\"\n\n"
            'Return a JSON object mapping each requirement id (string) to '
            '{"verdict":"Compliant"|"Partial"|"Gap"|"NotVerifiable","evidence":"<verbatim or empty>"}. '
            "All 47 ids must be present. JSON only.")

def big_sentences(text, cap=4000):
    parts = re.split(r"(?<=[.!?])\s+|\n+|•|\|", text or "")
    out, seen = [], set()
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip()
        if 15 <= len(p) <= 400 and p.lower() not in seen:
            seen.add(p.lower()); out.append(p)
        if len(out) >= cap:
            break
    return out

def retrieve_digest(text, topk=4, floor=0.22):
    """Union of the top-k most relevant sentences per duty, across the WHOLE policy, in order."""
    from sentence_transformers import util
    sents = big_sentences(text)
    if not sents:
        return text[:24000], 0
    model = S._model()                       # also populates S._EX_EMB
    emb = model.encode(sents, convert_to_tensor=True, normalize_embeddings=True, batch_size=128)
    chosen = set()
    for cid, ex_emb in S._EX_EMB.items():
        col = util.cos_sim(ex_emb, emb).max(dim=0).values   # best exemplar sim per sentence
        order = col.argsort(descending=True).tolist()
        taken = 0
        for j in order:
            if float(col[j]) < floor:
                break
            chosen.add(j); taken += 1
            if taken >= topk:
                break
    idx = sorted(chosen)
    digest = "\n".join(sents[j] for j in idx)
    return digest[:24000], len(idx)

def call(ctx, attempts=5):
    body = {"model": MODEL, "temperature": 0, "max_tokens": 6000,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": build_user(ctx)}]}
    last = None
    for a in range(attempts):
        try:
            r = httpx.post(URL, headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
                           json=body, timeout=120.0)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            if r.status_code in (429, 500, 502, 503):
                w = 5 * (a + 1); print("  retry %d in %ds" % (r.status_code, w), flush=True); time.sleep(w); last = r.text; continue
            return None
        except Exception as e:
            last = str(e); time.sleep(4 * (a + 1))
    print("  FAILED", (last or "")[:150], flush=True); return None

def parse(txt):
    if not txt: return {}
    s = re.sub(r"^```(json)?|```$", "", txt.strip(), flags=re.I | re.M).strip()
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j < 0: return {}
    try: obj = json.loads(s[i:j + 1])
    except Exception: return {}
    out = {}
    for k, v in obj.items():
        try: cid = int(re.sub(r"\D", "", str(k)))
        except Exception: continue
        out[cid] = (str(v.get("verdict", "")).strip(), str(v.get("evidence", "")).strip()) if isinstance(v, dict) else (str(v).strip(), "")
    return out

def load_body(path):
    c = open(path, encoding="utf-8").read()
    return (c.split("\n\n", 1)[1] if "\n\n" in c else c).strip()

rows = []
for path in sorted(glob.glob(os.path.join(OUT, "policy_*.txt"))):
    m = re.match(r"policy_(edu|ngo|sme)_(.+)\.txt$", os.path.basename(path))
    if not m: continue
    host = HOST_MAP.get(m.group(2))
    if not host: continue
    text = load_body(path)
    if len(text) < 2000: continue
    t0 = time.time()
    digest, nsel = retrieve_digest(text)
    verdicts = parse(call(digest))
    lowtext = re.sub(r"\s+", " ", text.lower())
    for c in CHECKS:
        v, ev = verdicts.get(c["id"], ("Gap", ""))
        if v not in ("Compliant", "Partial", "Gap", "NotVerifiable"):
            v = {"Not disclosed": "Gap", "Not externally verifiable": "NotVerifiable"}.get(v, "Gap")
        gr = ""
        if v in ("Compliant", "Partial") and len(ev) > 15:
            gr = "yes" if re.sub(r"\s+", " ", ev.lower())[:60] in lowtext else "no"
        rows.append({"site": host, "duty_id": c["id"], "verdict_llm": v, "evidence_llm": ev[:300], "quote_grounded": gr})
    print("done %s (digest %d sents from %d chars, %d/47, %.1fs)"
          % (host, nsel, len(text), len(verdicts), time.time() - t0), flush=True)

with open(os.path.join(OUT, "llm_rag_verdicts.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["site", "duty_id", "verdict_llm", "evidence_llm", "quote_grounded"])
    w.writeheader()
    for r in rows: w.writerow(r)
pos = [r for r in rows if r["quote_grounded"] in ("yes", "no")]
gr = [r for r in pos if r["quote_grounded"] == "yes"]
print("WROTE llm_rag_verdicts.csv (%d rows); quotes grounded %d/%d (%.1f%%)"
      % (len(rows), len(gr), len(pos), 100 * len(gr) / max(1, len(pos))))
