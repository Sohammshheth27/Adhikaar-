import os, re, sys, time, asyncio
sys.path.insert(0, r"D:\Adhikaar\backend")
import httpx
from app.compliance import crawler

OUT = r"D:\Adhikaar\gold_set"
LOG = os.path.join(OUT, "_supplement.log")

def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S") + " " + m + "\n")
    print(m, flush=True)

# sites that came back with 0 / thin policy text
THIN = [
    ("sme", "childrightsandyou.org", "https://www.childrightsandyou.org"),
    ("sme", "robu.in", "https://robu.in"),
    ("sme", "veefin.com", "https://www.veefin.com"),
    ("sme", "sudarshanpharma.com", "https://www.sudarshanpharma.com"),
    ("sme", "glen-india.com", "https://www.glen-india.com"),
]
# fix sector label: childrightsandyou is ngo
SECTOR = {"childrightsandyou.org": "ngo"}

CANDIDATE_PATHS = [
    "/privacy-policy", "/privacy-policy/", "/privacy", "/privacy/",
    "/privacy-notice", "/data-protection", "/legal/privacy", "/policies/privacy",
    "/terms", "/terms-and-conditions", "/terms-of-use", "/legal",
    "/privacy-policy.html", "/privacypolicy", "/about/privacy",
]

open(LOG, "w").close()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

def extract_text(html):
    # crude text extraction mirroring the crawler's cleanup
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;|&amp;|&#\d+;", " ", html)
    html = re.sub(r"\s+", " ", html)
    return html.strip()

def probe_static(base):
    found = []
    with httpx.Client(follow_redirects=True, timeout=15.0, headers=H, verify=False) as c:
        for p in CANDIDATE_PATHS:
            url = base.rstrip("/") + p
            try:
                r = c.get(url)
                if r.status_code == 200 and len(r.text) > 1500:
                    txt = extract_text(r.text)
                    if crawler._POLICY_TERMS.search(txt) and len(txt) > 600:
                        found.append((str(r.url), txt))
            except Exception:
                pass
    # dedupe by final url
    seen, uniq = set(), []
    for u, t in found:
        if u not in seen:
            seen.add(u); uniq.append((u, t))
    return uniq

for sec, host, base in THIN:
    sec = SECTOR.get(host, sec)
    pol = probe_static(base)
    # JS fallback if static found nothing
    if not pol:
        try:
            beh = crawler.site_behaviour(base, deadline=30.0)
            html = beh.get("rendered_html") or ""
            if html:
                txt = extract_text(html)
                if crawler._POLICY_TERMS.search(txt):
                    pol = [(base + " (rendered homepage)", txt)]
        except Exception as e:
            log("  JS fallback failed %s :: %s" % (host, str(e)[:90]))
    fn = "policy_%s_%s.txt" % (sec, re.sub(r"[^a-z0-9]+", "_", host.lower()))
    path = os.path.join(OUT, fn)
    with open(path, "w", encoding="utf-8") as f:
        f.write("SITE: %s  SECTOR: %s\nPOLICY PAGES FOUND: %s\n\n" % (host, sec, [u for u, _ in pol]))
        if pol:
            body = ""
            for u, t in pol:
                body += "\n===== PAGE: %s =====\n\n%s\n" % (u, t[:60000])
            f.write(body[:150000])
        else:
            f.write("(NO POLICY FOUND AFTER COMMON-PATH + JS PROBE -- treat disclosure duties as Gap.)")
    log("%s -> %d policy pages (%d bytes)" % (host, len(pol), os.path.getsize(path)))

log("SUPPLEMENT DONE")
