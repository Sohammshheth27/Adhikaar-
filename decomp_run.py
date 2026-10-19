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

# Per-duty sub-criteria. Convention: q[0] = "topic addressed?"; q[1:] = specific/concrete requirement(s).
# Derivation: all of q[1:] yes -> Compliant; else any yes -> Partial; else Gap.
SUBQ = {
 1:["Does the policy say it collects personal data?","Does it list SPECIFIC categories of personal data (e.g. name, email, phone, address)?"],
 2:["Does it state purposes for collecting data?","Are the purposes SPECIFIC rather than generic (not just 'business purposes')?"],
 3:["Is a privacy notice present as readable prose?","Is it written in plain, understandable language?"],
 4:["Does it reference a basis for processing (consent or lawful/legitimate use)?","Is a specific lawful basis named?"],
 5:["Does it address collecting only necessary data (data minimisation)?","Is there a commitment to limit collection to what the purpose needs?"],
 6:["Does it describe any legitimate uses relied upon?","Do those uses fall within lawful legitimate-use categories (legal compliance, employment, emergencies, etc.)?"],
 7:["Does it mention keeping data accurate or up to date?","Is there an explicit commitment to accuracy/correction?"],
 8:["Does it mention data retention or deletion?","Does it state a specific retention period OR an 'erase when the purpose ends' commitment?"],
 9:["Does it mention security measures?","Are specific safeguards named (encryption, access control, etc.)?"],
 10:["Does it mention personal-data breaches?","Is there a commitment to notify affected users and/or the regulator?"],
 11:["Does it mention withdrawing consent?","Is a route to withdraw stated that is as easy as giving consent?"],
 12:["Does it describe how consent is obtained?","Is consent a clear affirmative action, unbundled and not pre-ticked?"],
 13:["Does it mention a Consent Manager mechanism?","Is the Consent Manager route specifically acknowledged?"],
 14:["Does it mention consent records or reviewing consent?","Can users review consent given, or are records of consent maintained (stated)?"],
 15:["Does it address children's or minors' data?","Does it commit to verifiable parental consent for under-18s?","Does it commit to no tracking, behavioural monitoring or targeted ads to children?"],
 16:["Does it mention users' rights over their data?","Is the right to access/obtain a summary of one's personal data disclosed?"],
 17:["Does it mention users' rights over their data?","Is the right to correct or update personal data disclosed?"],
 18:["Does it mention users' rights over their data?","Is the right to erasure/deletion of personal data disclosed?"],
 19:["Does it mention a complaint or grievance route?","Is a readily available grievance-redressal route disclosed (named contact or mechanism)?"],
 20:["Does it mention nomination?","Is the right to nominate someone to exercise data rights disclosed?"],
 21:["Is any contact for data or privacy queries published?","Is a reachable grievance officer or dedicated data-queries contact named?"],
 22:["Does it mention a Data Protection Officer?","Is a DPO appointed AND published with a contact?"],
 23:["Does it mention processors or service providers handling data?","Does it state processors are engaged under a valid contract/agreement?"],
 24:["Does it mention sharing data with third parties?","Are the third parties, recipients or their categories disclosed?"],
 25:["Does it mention sub-processors or onward service providers?","Is sub-processor oversight or responsibility addressed?"],
 26:["Does it mention obligations placed on processors?","Do security obligations flow down to processors (stated)?"],
 27:["Does it mention international or cross-border data transfer?","Are transfers of personal data outside India specifically disclosed?"],
 28:["Does it address transfer restrictions or approved/restricted countries?","Is compliance with restricted-country notification addressed?"],
 29:["Does it mention where data is stored?","Is the data storage location or country disclosed?"],
 30:["Does it mention a data-protection impact assessment?","Is a DPIA stated to be undertaken?"],
 32:["Does it mention privacy or data-minimisation by design?","Are minimisation-by-design measures addressed?"],
 36:["Is the notice available in an accessible form?","Is it offered in Indian languages or accessible formats where relevant?"],
 39:["Does it mention encryption?","Is encryption at rest specifically disclosed?"],
 40:["Does it mention access control?","Are access controls and logging disclosed?"],
}
STRUCT = {33, 34, 35, 37, 38}
INTNV = {31, 41, 42, 43, 44, 45, 46, 47}

def build_prompt_block():
    lines = []
    for c in CHECKS:
        if c["id"] not in SUBQ: continue
        qs = SUBQ[c["id"]]
        lines.append("%d. %s" % (c["id"], c["requirement"]))
        for i, q in enumerate(qs, 1):
            lines.append("   q%d: %s" % (i, q))
    return "\n".join(lines)
BLOCK = build_prompt_block()

SYSTEM = ("You are a meticulous Data Protection Officer. For each requirement you are given numbered "
          "yes/no sub-questions. Answer each STRICTLY from the policy text provided: 'yes' only if the "
          "policy clearly supports it, otherwise 'no'. Do not infer beyond the text. Output STRICT JSON only.")

def big_sentences(text, cap=4000):
    out, seen = [], set()
    for p in re.split(r"(?<=[.!?])\s+|\n+|•|\|", text or ""):
        p = re.sub(r"\s+", " ", p).strip()
        if 15 <= len(p) <= 400 and p.lower() not in seen:
            seen.add(p.lower()); out.append(p)
        if len(out) >= cap: break
    return out

def digest(text, topk=5, floor=0.20):
    from sentence_transformers import util
    sents = big_sentences(text)
    model = S._model()
    emb = model.encode(sents, convert_to_tensor=True, normalize_embeddings=True, batch_size=128)
    chosen = set()
    for cid, ex in S._EX_EMB.items():
        col = util.cos_sim(ex, emb).max(dim=0).values
        for j in col.argsort(descending=True).tolist()[:topk]:
            if float(col[j]) >= floor: chosen.add(j)
    return "\n".join(sents[j] for j in sorted(chosen))[:26000]

def call(ctx, attempts=5):
    user = ("Requirements with sub-questions:\n" + BLOCK +
            "\n\nPolicy passages:\n\"\"\"\n" + ctx + "\n\"\"\"\n\n"
            'Return JSON mapping each requirement id (string) to {"a": ["yes"|"no", ...one per sub-question in order]}. '
            "Include every listed id. JSON only, no prose.")
    body = {"model": MODEL, "temperature": 0, "max_tokens": 8000,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
    last = None
    for a in range(attempts):
        try:
            r = httpx.post(URL, headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
                           json=body, timeout=150.0)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            if r.status_code in (429, 500, 502, 503):
                w = 5 * (a + 1); print("  retry %d in %ds" % (r.status_code, w), flush=True); time.sleep(w); last = r.text; continue
            return None
        except Exception as e:
            last = str(e); time.sleep(4 * (a + 1))
    print("  FAILED", (last or "")[:150], flush=True); return None

def parse_answers(txt):
    out = {}
    s = re.sub(r"^```(json)?|```$", "", (txt or "").strip(), flags=re.I | re.M).strip()
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        try:
            obj = json.loads(s[i:j + 1])
            for k, v in obj.items():
                cid = int(re.sub(r"\D", "", str(k)))
                a = v.get("a", v) if isinstance(v, dict) else v
                if isinstance(a, list):
                    out[cid] = [str(x).strip().lower().startswith("y") for x in a]
            if out: return out
        except Exception:
            pass
    # salvage: regex per id with a list
    for mm in re.finditer(r'"(\d+)"\s*:\s*\{[^}]*"a"\s*:\s*\[([^\]]*)\]', s):
        cid = int(mm.group(1))
        out[cid] = [t.strip().strip('"').lower().startswith("y") for t in mm.group(2).split(",") if t.strip()]
    return out

def derive(cid, ans):
    qs = SUBQ[cid]
    if not ans or len(ans) < len(qs):
        ans = (ans or []) + [False] * (len(qs) - len(ans or []))
    strong = all(ans[1:]) if len(qs) > 1 else ans[0]
    anyyes = any(ans)
    return "Compliant" if strong else ("Partial" if anyyes else "Gap")

# NLI (for structural routing + guardrail)
TMAP = {"Compliant": "Compliant", "Partial": "Partial", "Not disclosed": "Gap",
        "Not externally verifiable": "NotVerifiable", "Insufficient evidence": "Gap"}
NLI = {}
with open(os.path.join(OUT, "config_verdicts.csv"), encoding="utf-8") as f:
    for d in csv.DictReader(f):
        NLI[(d["site"], int(d["duty_id"]))] = TMAP.get(d["verdict_nli"], d["verdict_nli"])

def load_body(p):
    c = open(p, encoding="utf-8").read(); return (c.split("\n\n", 1)[1] if "\n\n" in c else c).strip()

HOST_MAP = {"jnu_ac_in": "jnu.ac.in", "du_ac_in": "du.ac.in", "iima_ac_in": "iima.ac.in",
            "akshayapatra_org": "akshayapatra.org", "tatatrusts_org": "tatatrusts.org",
            "savethechildren_in": "savethechildren.in", "robu_in": "robu.in",
            "networkintelligence_ai": "networkintelligence.ai", "powersoft_in": "powersoft.in"}

rows = []
for path in sorted(glob.glob(os.path.join(OUT, "policy_*.txt"))):
    m = re.match(r"policy_(edu|ngo|sme)_(.+)\.txt$", os.path.basename(path))
    if not m: continue
    host = HOST_MAP.get(m.group(2))
    if not host: continue
    text = load_body(path)
    if len(text) < 2000: continue
    t0 = time.time()
    ans = parse_answers(call(digest(text)))
    for c in CHECKS:
        cid = c["id"]
        if cid in STRUCT:
            v = NLI[(host, cid)]
        elif cid in INTNV:
            v = "NotVerifiable"
        else:
            v = derive(cid, ans.get(cid))
        rows.append({"site": host, "duty_id": cid, "verdict": v})
    print("done %s (%d/34 content answered, %.1fs)" % (host, sum(1 for c in SUBQ if c in ans), time.time() - t0), flush=True)

with open(os.path.join(OUT, "decomp_verdicts.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["site", "duty_id", "verdict"]); w.writeheader()
    for r in rows: w.writerow(r)
print("WROTE decomp_verdicts.csv (%d rows)" % len(rows))
