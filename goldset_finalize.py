import os, re, sys, time, csv, glob
sys.path.insert(0, r"D:\Adhikaar\backend")
from app.compliance import crawler
from app.compliance.catalog import CHECKS
from playwright.sync_api import sync_playwright

OUT = r"D:\Adhikaar\gold_set"
LOG = os.path.join(OUT, "_finalize.log")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S") + " " + m + "\n")
    print(m, flush=True)

# render the two case-study companies
CASE = [
    ("sme", "networkintelligence.ai", [
        "https://www.networkintelligence.ai/privacy-policy/",
        "https://www.networkintelligence.ai/privacy-policy",
    ]),
    ("sme", "powersoft.in", [
        "https://www.powersoft.in/privacy-policy/",
        "https://www.powersoft.in/privacy-policy",
        "https://powersoft.in/privacy-policy/",
    ]),
]
open(LOG, "w").close()
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for sec, host, urls in CASE:
        ctx = browser.new_context(user_agent=UA, locale="en-US", ignore_https_errors=True)
        pg = ctx.new_page()
        found = []
        for u in urls:
            try:
                resp = pg.goto(u, wait_until="networkidle", timeout=35000)
                try:
                    pg.wait_for_timeout(1200)
                except Exception:
                    pass
                txt = re.sub(r"\s+\n", "\n", pg.inner_text("body")).strip()
                ok = bool(crawler._POLICY_TERMS.search(txt)) and len(txt) > 600
                log("  %s [%s] txt=%d policy=%s" % (u, resp.status if resp else "?", len(txt), ok))
                if ok:
                    found.append((str(pg.url), txt))
                    break
            except Exception as e:
                log("  %s ERR %s" % (u, str(e)[:80]))
        ctx.close()
        fn = "policy_%s_%s.txt" % (sec, re.sub(r"[^a-z0-9]+", "_", host.lower()))
        with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
            f.write("SITE: %s  SECTOR: %s  (JS-rendered, case study)\nPOLICY PAGES FOUND: %s\n\n" % (host, sec, [u for u, _ in found]))
            if found:
                body = ""
                for u, t in found:
                    body += "\n===== PAGE: %s =====\n\n%s\n" % (u, t[:60000])
                f.write(body[:150000])
            else:
                f.write("(NO POLICY FOUND)")
        log("%s -> %d policy pages (%d bytes)" % (host, len(found), os.path.getsize(os.path.join(OUT, fn))))
    browser.close()

# ---- rebuild CSV from substantial policy files only ----
SECTOR_OF = {}
for fn in glob.glob(os.path.join(OUT, "policy_*.txt")):
    base = os.path.basename(fn)
    m = re.match(r"policy_(edu|ngo|sme)_(.+)\.txt$", base)
    if not m:
        continue
    sec, hostslug = m.group(1), m.group(2)
    with open(fn, encoding="utf-8") as f:
        content = f.read()
    # body = everything after the header blank line
    parts = content.split("\n\n", 1)
    body = parts[1] if len(parts) > 1 else ""
    host = re.sub(r"_", ".", hostslug)
    # fix known multi-dot hosts
    host = host.replace("ac.in", "ac.in")  # noop, slugs already single-token per label
    substantial = len(body.strip()) > 2000 and bool(crawler._POLICY_TERMS.search(body))
    SECTOR_OF[fn] = (sec, host, len(body.strip()), substantial)

# recover true hostnames from a fixed map (slug -> host)
HOST_MAP = {
    "jnu_ac_in": "jnu.ac.in", "du_ac_in": "du.ac.in", "iima_ac_in": "iima.ac.in", "iitb_ac_in": "iitb.ac.in",
    "akshayapatra_org": "akshayapatra.org", "tatatrusts_org": "tatatrusts.org",
    "childrightsandyou_org": "childrightsandyou.org", "savethechildren_in": "savethechildren.in",
    "robu_in": "robu.in", "veefin_com": "veefin.com", "sudarshanpharma_com": "sudarshanpharma.com",
    "glen_india_com": "glen-india.com", "networkintelligence_ai": "networkintelligence.ai", "powersoft_in": "powersoft.in",
}

def anchor(c):
    a = c.get("dpdp_anchor") or {}
    parts = []
    if a.get("rule"):
        parts.append(a["rule"])
    if a.get("act_section"):
        parts.append("Act " + a["act_section"])
    return "; ".join(parts)

keep = []
for fn, (sec, host, blen, sub) in sorted(SECTOR_OF.items()):
    base = os.path.basename(fn)
    slug = re.match(r"policy_(edu|ngo|sme)_(.+)\.txt$", base).group(2)
    real = HOST_MAP.get(slug, host)
    log("CANDIDATE %s sector=%s bodylen=%d substantial=%s" % (real, sec, blen, sub))
    if sub:
        keep.append((sec, real))

rows = []
for sec, host in keep:
    for c in CHECKS:
        rows.append({"site": host, "sector": sec, "duty_id": c["id"], "category": c.get("category", ""),
                     "requirement": c.get("requirement", ""), "anchor": anchor(c),
                     "in_force": "yes" if c.get("in_force") else "no", "verdict": "", "evidence_note": ""})

with open(os.path.join(OUT, "gold_labels_blank.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["site", "sector", "duty_id", "category", "requirement", "anchor", "in_force", "verdict", "evidence_note"])
    w.writeheader()
    for r in rows:
        w.writerow(r)
log("FINAL GOLD SET: %d sites, %d label rows" % (len(keep), len(rows)))
log("SITES: %s" % ", ".join("%s(%s)" % (h, s) for s, h in keep))
