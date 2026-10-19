import json, urllib.request, time

# Remaining 13 sites after the memory-reap stopped the full run at smilefoundationindia (17/30).
SITES = [
    ("ngo", "teachforindia.org"), ("ngo", "wwfindia.org"), ("ngo", "actionaidindia.org"),
    ("sme", "robu.in"), ("sme", "glen-india.com"), ("sme", "veefin.com"), ("sme", "sudarshanpharma.com"),
    ("sme", "sealmaticindia.com"), ("sme", "kpgreenengineering.com"), ("sme", "supershaktimetaliks.com"),
    ("sme", "tridentlifeline.com"), ("sme", "zelioebikes.com"), ("sme", "solariumenergy.in"),
]
OUT = r"D:\Adhikaar\demo_results.jsonl"      # APPEND -- keep the 17 already done
LOG = r"D:\Adhikaar\demo_campaign.log"


def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S") + " " + m + "\n")


def scan(url):
    body = json.dumps({"url": url, "force": True}).encode()
    req = urllib.request.Request("http://127.0.0.1:8010/scan", data=body,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=900))


log("RESUME START %d remaining sites" % len(SITES))
done = 0
for sec, url in SITES:
    t = time.time()
    try:
        d = scan(url)
        sm = d.get("sitemap", {}); bh = d.get("behaviour", {}); enf = d.get("enforceability", {}); exp = d.get("exposure", [])
        rec = {"sector": sec, "url": url,
               "dpdp_grade": d.get("grade"), "dpdp_adequacy": round((d.get("adequacy") or 0) * 100),
               "itact_grade": enf.get("it_act_grade"),
               "pages": sm.get("n_pages"), "subdomains": sm.get("n_subdomains"),
               "trackers": bh.get("n_trackers"),
               "nonessential_pre_consent": bh.get("n_nonessential_pre_consent"),
               "banner": bh.get("consent_banner_present"),
               "reject_tested": bh.get("reject_tested"), "reject_honoured": bh.get("reject_honoured"),
               "exposures": len(exp), "secs": round(time.time() - t),
               "duties": [{"id": x.get("id"), "verdict": x.get("verdict"), "category": x.get("category"),
                           "it_act": x.get("it_act")} for x in (d.get("duties") or [])]}
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        done += 1
        log("OK %s grade=%s itact=%s %ds (%d/%d)" % (url, d.get("grade"), enf.get("it_act_grade"), rec["secs"], done, len(SITES)))
    except Exception as e:
        log("FAIL %s :: %s" % (url, str(e)[:160]))
log("RESUME DONE %d/%d" % (done, len(SITES)))
