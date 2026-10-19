import os, re, sys, time
sys.path.insert(0, r"D:\Adhikaar\backend")
from app.compliance import crawler
from playwright.sync_api import sync_playwright

OUT = r"D:\Adhikaar\gold_set"
LOG = os.path.join(OUT, "_render.log")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S") + " " + m + "\n")
    print(m, flush=True)

# (sector, host, [candidate policy URLs to render])
TARGETS = [
    ("ngo", "childrightsandyou.org", [
        "https://www.childrightsandyou.org/privacy-policy/",
        "https://www.childrightsandyou.org/privacy-policy",
        "https://www.childrightsandyou.org/terms-and-conditions/",
    ]),
    ("sme", "robu.in", [
        "https://robu.in/privacy-policy/",
        "https://robu.in/terms-and-conditions/",
    ]),
    ("sme", "veefin.com", [
        "https://www.veefin.com/privacy-policy/",
        "https://www.veefin.com/terms-conditions/",
    ]),
    ("sme", "sudarshanpharma.com", [
        "https://sudarshanpharma.com/privacy-policy/",
        "https://www.sudarshanpharma.com/privacy-policy/",
        "https://sudarshanpharma.com/privacy-policy",
        "https://sudarshanpharma.com/terms-and-conditions/",
    ]),
    ("sme", "glen-india.com", [
        "https://www.glen-india.com/privacy-policy",
        "https://www.glen-india.com/privacy-policy/",
        "https://www.glen-india.com/pages/privacy-policy",
    ]),
]

open(LOG, "w").close()
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for sec, host, urls in TARGETS:
        ctx = browser.new_context(user_agent=UA, locale="en-US", ignore_https_errors=True)
        pg = ctx.new_page()
        found = []
        for u in urls:
            try:
                resp = pg.goto(u, wait_until="networkidle", timeout=35000)
                status = resp.status if resp else None
                try:
                    pg.wait_for_timeout(1200)
                except Exception:
                    pass
                txt = pg.inner_text("body")
                txt = re.sub(r"\s+\n", "\n", txt).strip()
                ok = bool(crawler._POLICY_TERMS.search(txt)) and len(txt) > 600
                log("  %s [%s] txt=%d policy=%s" % (u, status, len(txt), ok))
                if ok:
                    found.append((str(pg.url), txt))
            except Exception as e:
                log("  %s ERR %s" % (u, str(e)[:80]))
        ctx.close()
        # dedupe
        seen, uniq = set(), []
        for u, t in found:
            key = t[:200]
            if key not in seen:
                seen.add(key); uniq.append((u, t))
        fn = "policy_%s_%s.txt" % (sec, re.sub(r"[^a-z0-9]+", "_", host.lower()))
        path = os.path.join(OUT, fn)
        with open(path, "w", encoding="utf-8") as f:
            f.write("SITE: %s  SECTOR: %s  (JS-rendered)\nPOLICY PAGES FOUND: %s\n\n" % (host, sec, [u for u, _ in uniq]))
            if uniq:
                body = ""
                for u, t in uniq:
                    body += "\n===== PAGE: %s =====\n\n%s\n" % (u, t[:60000])
                f.write(body[:150000])
            else:
                f.write("(NO POLICY FOUND AFTER JS RENDER -- treat disclosure duties as Gap.)")
        log("%s -> %d policy pages (%d bytes)" % (host, len(uniq), os.path.getsize(path)))
    browser.close()
log("RENDER DONE")
