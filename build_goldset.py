import os, re, csv, sys, time
sys.path.insert(0, r"D:\Adhikaar\backend")
from app.compliance.catalog import CHECKS
from app.compliance import crawler

OUT = r"D:\Adhikaar\gold_set"
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(OUT, "_build.log")

def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S") + " " + m + "\n")

SITES = [
    ("edu", "jnu.ac.in"), ("edu", "du.ac.in"), ("edu", "iima.ac.in"), ("edu", "iitb.ac.in"),
    ("ngo", "akshayapatra.org"), ("ngo", "tatatrusts.org"), ("ngo", "childrightsandyou.org"), ("ngo", "savethechildren.in"),
    ("sme", "robu.in"), ("sme", "veefin.com"), ("sme", "sudarshanpharma.com"), ("sme", "glen-india.com"),
]

def anchor(c):
    a = c.get("dpdp_anchor") or {}
    parts = []
    if a.get("rule"):
        parts.append(a["rule"])
    if a.get("act_section"):
        parts.append("Act " + a["act_section"])
    return "; ".join(parts)

open(LOG, "w").close()
# 1) rubric
with open(os.path.join(OUT, "RUBRIC.md"), "w", encoding="utf-8") as f:
    f.write("# ADHIKAAR Gold-Set Adjudication Rubric (47 DPDP duties)\n\n")
    f.write("How to use: for each site, open its policy text file (policy_*.txt), read it, and in\n")
    f.write("gold_labels_blank.csv assign ONE verdict per duty in the 'verdict' column. Do NOT consult\n")
    f.write("the Adhikaar output; judge only from the policy text and the statute. Optionally note the\n")
    f.write("supporting sentence in 'evidence_note'.\n\n")
    f.write("Verdict options:\n")
    f.write("- Compliant: the policy clearly states or commits to the required practice.\n")
    f.write("- Partial: the topic is mentioned but is vague, incomplete, or conditional.\n")
    f.write("- Gap: the practice is required and expected, but is absent from the policy.\n")
    f.write("- NotApplicable: the duty does not apply to this type of site.\n")
    f.write("- NotVerifiable: an internal control that cannot be judged from public text alone.\n\n")
    f.write("Note: if a site has no policy at all, most disclosure duties are 'Gap'.\n\n")
    for c in CHECKS:
        f.write("## Duty %s  (%s)\n" % (c["id"], c.get("category", "")))
        f.write("- Requirement: %s\n" % c.get("requirement", ""))
        f.write("- Statutory anchor: %s\n" % (anchor(c) or "(see Act)"))
        f.write("- In force under the IT Act today: %s\n" % ("yes" if c.get("in_force") else "no"))
        f.write("- Mandatory: %s\n\n" % ("yes" if c.get("mandatory") else "no"))
log("rubric written (%d duties)" % len(CHECKS))

# 2) fetch frozen policy text + 3) build blank CSV
rows = []
for sec, url in SITES:
    try:
        cr = crawler.crawl_static(url, budget=40, deadline=55)
        pol = [p for p in cr["pages"] if p.get("is_policy")]
        if not pol:
            cand = [p for p in cr["pages"] if re.search(r"privacy|policy|terms|legal", p["url"], re.I)]
            pol = sorted(cand, key=lambda p: -len(p.get("text", "")))[:1]
        fn = "policy_%s_%s.txt" % (sec, re.sub(r"[^a-z0-9]+", "_", url.lower()))
        with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
            f.write("SITE: %s  SECTOR: %s\nPOLICY PAGES FOUND: %s\n\n" % (url, sec, [p["url"] for p in pol]))
            if pol:
                body = ""
                for p in pol:
                    body += "\n===== PAGE: %s =====\n\n%s\n" % (p["url"], p.get("text", ""))
                f.write(body[:150000])
            else:
                f.write("(NO POLICY FOUND ON THIS SITE -- disclosure duties are expected to be Gap.)")
        for c in CHECKS:
            rows.append({"site": url, "sector": sec, "duty_id": c["id"], "category": c.get("category", ""),
                         "requirement": c.get("requirement", ""), "anchor": anchor(c),
                         "in_force": "yes" if c.get("in_force") else "no", "verdict": "", "evidence_note": ""})
        log("OK %s (%d policy pages)" % (url, len(pol)))
    except Exception as e:
        log("FAIL %s :: %s" % (url, str(e)[:120]))

with open(os.path.join(OUT, "gold_labels_blank.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["site", "sector", "duty_id", "category", "requirement", "anchor", "in_force", "verdict", "evidence_note"])
    w.writeheader()
    for r in rows:
        w.writerow(r)
log("PACKET BUILT: %d sites, %d label rows" % (len(SITES), len(rows)))
