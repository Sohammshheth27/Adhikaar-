"""
demo_precache.py -- warm the scan cache before a demo so targets return INSTANTLY on stage.

Run this the night before (backend must already be running), against the SAME server the frontend
uses. Each URL is scanned once and cached; on stage the UI replays it with zero risk of a live hang.

    python demo_precache.py http://localhost:8000  https://siteA  https://siteB ...
"""
import sys
import json
import urllib.request


def scan(base, url):
    req = urllib.request.Request(
        base.rstrip("/") + "/scan",
        data=json.dumps({"url": url}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def main():
    if len(sys.argv) < 3:
        print("usage: python demo_precache.py <API_BASE> <url> [url ...]"); return
    base, urls = sys.argv[1], sys.argv[2:]
    for u in urls:
        try:
            d = scan(base, u)
            npass = sum(1 for c in d["checks"] if c["verdict"] == "PASS")
            print(f"[ok] {u}: cached ({npass}/{len(d['checks'])} pass, reached {len(d['coverage']['reached'])} pages)")
        except Exception as e:
            print(f"[FAIL] {u}: {type(e).__name__} {e} -- pick a site that crawls cleanly, not a bot-blocking SPA")
    print("\nDone. These URLs now return instantly from cache in the demo.")


if __name__ == "__main__":
    main()
