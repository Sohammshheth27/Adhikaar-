import os, re, csv, glob, json, time, io, sys
import httpx
sys.path.insert(0, r"D:\Adhikaar\backend")
from app.compliance.catalog import CHECKS
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

DUTY_BLOCK = "\n".join(
    f'{c["id"]}. {c["requirement"]} [anchor: {anchor(c) or "DPDP"}]' for c in CHECKS)

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

def build_user(policy_text):
    return ("Requirements (id. text [anchor]):\n" + DUTY_BLOCK +
            "\n\nPolicy text:\n\"\"\"\n" + policy_text[:24000] + "\n\"\"\"\n\n"
            'Return a JSON object mapping each requirement id (string) to '
            '{"verdict":"Compliant"|"Partial"|"Gap"|"NotVerifiable","evidence":"<verbatim or empty>"}. '
            "All 47 ids must be present. JSON only.")

def call(policy_text, attempts=5):
    body = {"model": MODEL, "temperature": 0, "max_tokens": 6000,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": build_user(policy_text)}]}
    last = None
    for a in range(attempts):
        try:
            r = httpx.post(URL, headers={"Authorization": "Bearer " + KEY,
                           "Content-Type": "application/json"}, json=body, timeout=120.0)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            if r.status_code in (429, 500, 502, 503):
                wait = 5 * (a + 1)
                print("  retry (HTTP %d) in %ds" % (r.status_code, wait), flush=True); time.sleep(wait); last = r.text; continue
            return None
        except Exception as e:
            last = str(e); time.sleep(4 * (a + 1))
    print("  FAILED:", (last or "")[:150], flush=True); return None

def parse(txt):
    if not txt: return {}
    s = txt.strip()
    s = re.sub(r"^```(json)?|```$", "", s, flags=re.I | re.M).strip()
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j < 0: return {}
    try:
        obj = json.loads(s[i:j + 1])
    except Exception:
        return {}
    out = {}
    for k, v in obj.items():
        try: cid = int(re.sub(r"\D", "", str(k)))
        except Exception: continue
        if isinstance(v, dict):
            out[cid] = (str(v.get("verdict", "")).strip(), str(v.get("evidence", "")).strip())
        else:
            out[cid] = (str(v).strip(), "")
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
    verdicts = parse(call(text))
    norm = {}
    for c in CHECKS:
        v, ev = verdicts.get(c["id"], ("Gap", ""))
        if v not in ("Compliant", "Partial", "Gap", "NotVerifiable"):
            v = {"Not disclosed": "Gap", "Not externally verifiable": "NotVerifiable"}.get(v, "Gap")
        norm[c["id"]] = (v, ev)
    # hallucination check: evidence present in policy?
    lowtext = re.sub(r"\s+", " ", text.lower())
    for c in CHECKS:
        v, ev = norm[c["id"]]
        grounded = ""
        if v in ("Compliant", "Partial") and len(ev) > 15:
            probe = re.sub(r"\s+", " ", ev.lower())[:60]
            grounded = "yes" if probe and probe in lowtext else "no"
        rows.append({"site": host, "duty_id": c["id"], "verdict_llm": v,
                     "evidence_llm": ev[:300], "quote_grounded": grounded})
    got = len(verdicts)
    print("done %s (%d/47 parsed, %.1fs)" % (host, got, time.time() - t0), flush=True)

with open(os.path.join(OUT, "llm_verdicts.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["site", "duty_id", "verdict_llm", "evidence_llm", "quote_grounded"])
    w.writeheader()
    for r in rows: w.writerow(r)
print("WROTE llm_verdicts.csv (%d rows)" % len(rows))
# quick grounding stat
pos = [r for r in rows if r["quote_grounded"] in ("yes", "no")]
gr = [r for r in pos if r["quote_grounded"] == "yes"]
print("LLM positive-verdict quotes grounded in policy: %d/%d (%.1f%%)"
      % (len(gr), len(pos), 100 * len(gr) / max(1, len(pos))))
