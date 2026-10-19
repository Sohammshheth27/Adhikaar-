"""
stream.py -- hosted authenticated login via a CDP-screencast remote browser.

The server runs a HEADLESS Chromium (async Playwright) and streams its screen to the operator's web
page over a WebSocket: CDP Page.startScreencast emits JPEG frames, which we relay; the operator
drives the remote browser from their page (typing credentials, solving CAPTCHA, entering OTP) via
input events forwarded back and injected with CDP Input.*. On "capture" the server grabs the
authenticated storage_state, stops the stream, and hands it to the read-only authenticated crawl.

Headless compositor capture means NO virtual display (Xvfb) is needed; the same code runs on Windows
and Linux. The screen is streamed, not a window.

Trust model: credentials are typed into the server-rendered browser (as with any hosted
remote-browser / cloud DAST), carried over the WebSocket, never logged and never persisted; the
browser and the captured session are torn down after use. An authorization attestation is required
to start (enforced at the API layer, same as the headed-local flow).
"""
from __future__ import annotations
import asyncio
import base64
import secrets
import time

from .crawler import _UA_STRING

VIEWPORT = {"width": 1280, "height": 800}
_FRAME_INTERVAL = 0.12          # ~8 fps to the client; capture rate is decoupled
_JPEG_QUALITY = 40
_MAX_W, _MAX_H = 1024, 640      # cap streamed frame size (scaled down from the 1280x800 viewport)
_MAX_SESSION = 900              # a streaming login may stay open up to 15 minutes

# token -> {"login_url", "created", "authorized"}: created by /auth/stream_start, consumed by the WS.
_PENDING: dict[str, dict] = {}
# token -> storage_state: a captured session awaiting its scan (consumed by /auth/stream_scan).
_CAPTURED: dict[str, dict] = {}

# special (non-text) keys -> CDP key params
_SPECIAL = {
    "Enter": ("Enter", 13, "\r"), "Backspace": ("Backspace", 8, ""), "Tab": ("Tab", 9, ""),
    "Delete": ("Delete", 46, ""), "Escape": ("Escape", 27, ""),
    "ArrowLeft": ("ArrowLeft", 37, ""), "ArrowUp": ("ArrowUp", 38, ""),
    "ArrowRight": ("ArrowRight", 39, ""), "ArrowDown": ("ArrowDown", 40, ""),
    "Home": ("Home", 36, ""), "End": ("End", 35, ""),
}
_BUTTON = {0: "left", 1: "middle", 2: "right"}


def _reap():
    now = time.time()
    for d in (_PENDING, _CAPTURED):
        for t in [t for t, v in d.items() if now - (v.get("created", now) if isinstance(v, dict) else now) > _MAX_SESSION]:
            d.pop(t, None)


def start(login_url: str, creds: dict | None = None) -> str:
    """Register a streaming login and return its token (the WS then opens the browser).
    `creds` (optional) holds operator-supplied {username, password, totp_secret} for assisted
    auto-login; held in memory only, never stored or logged."""
    _reap()
    tok = secrets.token_urlsafe(16)
    _PENDING[tok] = {"login_url": login_url, "created": time.time(), "creds": creds or {}}
    return tok


def pop_captured(token: str) -> dict | None:
    v = _CAPTURED.pop(token, None)
    return v["ss"] if v else None


async def _dispatch_input(cdp, msg: dict):
    """Inject one operator input event into the remote browser via CDP."""
    t = msg.get("type")
    if t == "move":
        await cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved",
                       "x": msg["x"], "y": msg["y"]})
    elif t in ("down", "up"):
        await cdp.send("Input.dispatchMouseEvent", {
            "type": "mousePressed" if t == "down" else "mouseReleased",
            "x": msg["x"], "y": msg["y"], "button": _BUTTON.get(msg.get("button", 0), "left"),
            "clickCount": 1})
    elif t == "wheel":
        await cdp.send("Input.dispatchMouseEvent", {"type": "mouseWheel",
                       "x": msg["x"], "y": msg["y"],
                       "deltaX": msg.get("dx", 0), "deltaY": msg.get("dy", 0)})
    elif t == "char":                                   # a printable character typed by the operator
        await cdp.send("Input.insertText", {"text": msg.get("text", "")})
    elif t == "key":                                    # a special key (Enter, Backspace, arrows, ...)
        spec = _SPECIAL.get(msg.get("k", ""))
        if spec:
            code, vk, text = spec
            for et in ("keyDown", "keyUp"):
                params = {"type": et, "key": msg["k"], "code": code, "windowsVirtualKeyCode": vk}
                if text and et == "keyDown":
                    params["text"] = text
                await cdp.send("Input.dispatchKeyEvent", params)


# ---- assisted auto-login ----------------------------------------------------------------------
# We AUTO-FILL the operator-supplied credentials and AUTO-GENERATE the TOTP code (RFC-6238 math on a
# secret the operator owns). We DO NOT bypass CAPTCHA or SMS/email OTP -- those stay human: if one
# appears, we stop and the operator clears it in the streamed view. Credentials are used in memory
# only, never stored or logged.
_USER_SELECTORS = ['input[autocomplete="username"]', 'input[type="email"]', 'input[name*="email" i]',
                   'input[id*="email" i]', 'input[name*="user" i]', 'input[id*="user" i]',
                   'input[name*="login" i]', 'input[id*="login" i]', 'input[type="tel"]']
_PASS_SELECTORS = ['input[type="password"]', 'input[autocomplete="current-password"]']
_OTP_SELECTORS = ['input[autocomplete="one-time-code"]', 'input[name*="otp" i]', 'input[id*="otp" i]',
                  'input[name*="totp" i]', 'input[id*="totp" i]', 'input[name*="code" i]',
                  'input[id*="code" i]', 'input[name*="pin" i]']
_SUBMIT_SELECTORS = ['#continue', '#signInSubmit', 'button[type="submit"]', 'input[type="submit"]',
                     'button[name*="sign" i]', 'button[id*="sign" i]', 'button[id*="login" i]',
                     'button[id*="continue" i]']
_SUBMIT_TEXT = ("sign in", "log in", "login", "continue", "next", "submit")
_CAPTCHA_MARKERS = ("recaptcha", "g-recaptcha", "hcaptcha", "h-captcha", "captcha",
                    "are you a robot", "enter the characters", "funcaptcha", "arkose")


async def _fill_first(page, selectors, value) -> bool:
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.fill(value)
                return True
        except Exception:
            continue
    return False


async def _click_submit(page) -> bool:
    for sel in _SUBMIT_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click(timeout=4000)
                return True
        except Exception:
            continue
    try:                                                   # fall back to a button by its text
        for b in await page.query_selector_all("button, a[role=button], input[type=button]"):
            try:
                txt = ((await b.inner_text()) or (await b.get_attribute("value")) or "").strip().lower()
                if txt and any(t in txt for t in _SUBMIT_TEXT) and await b.is_visible():
                    await b.click(timeout=4000)
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


async def _captcha_present(page) -> bool:
    try:
        html = (await page.content()).lower()
    except Exception:
        return False
    return any(k in html for k in _CAPTCHA_MARKERS)


async def _otp_field_present(page) -> bool:
    for sel in _OTP_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                return True
        except Exception:
            continue
    return False


async def _auto_login(page, creds: dict, ws) -> None:
    """Fill operator-supplied credentials and the TOTP code; stop for human CAPTCHA/SMS-OTP."""
    username = (creds or {}).get("username")
    password = (creds or {}).get("password")
    totp_secret = (creds or {}).get("totp_secret")
    if not (username or password):
        return                                             # pure human login; nothing to auto-fill

    async def note(msg):
        try:
            await ws.send_json({"type": "status", "detail": msg})   # never includes credentials
        except Exception:
            pass

    await note("Attempting assisted sign-in…")
    try:                                                   # wait for the login form to actually render
        await page.wait_for_selector(
            "input[type=password], input[type=email], input[name*=user i], input[name*=login i]",
            timeout=12000)
    except Exception:
        await note("Could not find a login form. Please sign in manually in the view.")
        return

    try:
        if username and await _fill_first(page, _USER_SELECTORS, username):
            await note("Entered username")
            if not await _fill_first(page, _PASS_SELECTORS, password or ""):
                await _click_submit(page)                  # multi-step login (email -> continue)
                await page.wait_for_timeout(1800)
        if password and await _fill_first(page, _PASS_SELECTORS, password):
            await note("Entered password")
        if await _captcha_present(page):
            await note("CAPTCHA detected. Please solve it in the view, then continue.")
            return                                         # never auto-solve a CAPTCHA
        await _click_submit(page)
        await page.wait_for_timeout(2200)
        if await _captcha_present(page):
            await note("CAPTCHA detected. Please solve it in the view, then continue.")
            return
        if await _otp_field_present(page):
            if totp_secret:
                try:
                    import pyotp
                    code = pyotp.TOTP(totp_secret.replace(" ", "")).now()
                    if await _fill_first(page, _OTP_SELECTORS, code):
                        await note("Entered 2FA code")
                        await _click_submit(page)
                        await page.wait_for_timeout(1500)
                except Exception:
                    await note("Could not generate the 2FA code. Please enter it in the view.")
            else:
                await note("A one-time code is required. Please enter it in the view.")
    except Exception:
        await note("Auto-login could not complete. Please finish signing in manually in the view.")


async def run_stream(ws, token: str):
    """WebSocket body: open the remote browser at the login page, stream it, forward input, and
    capture the session on request. `ws` is a Starlette/FastAPI WebSocket (already accepted)."""
    pend = _PENDING.pop(token, None)
    if pend is None:
        await ws.send_json({"type": "error", "detail": "unknown or expired session token"})
        return
    login_url = pend["login_url"]

    from playwright.async_api import async_playwright
    latest = {"data": None, "seq": 0}
    stop = asyncio.Event()
    captured = {"ok": False, "err": None}

    # Explicit start/stop (not `async with`) so we can FULLY tear the streaming browser down before
    # telling the client the session is captured. The client launches the read-only crawl on that
    # signal, and that crawl uses the SYNC Playwright API -- running it while this async browser is
    # still closing conflicts on Windows. Serialising here is what makes the handoff reliable.
    p = await async_playwright().start()
    browser = None
    cdp = None
    try:
        browser = await p.chromium.launch(headless=True,
                                           args=["--disable-blink-features=AutomationControlled",
                                                 "--disable-dev-shm-usage"])
        ctx = await browser.new_context(user_agent=_UA_STRING, locale="en-US",
                                        timezone_id="Asia/Kolkata", viewport=VIEWPORT)
        page = await ctx.new_page()
        cdp = await ctx.new_cdp_session(page)

        def on_frame(ev):
            latest["data"] = ev["data"]
            latest["seq"] += 1
            asyncio.create_task(cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]}))
        cdp.on("Page.screencastFrame", on_frame)

        try:
            await page.goto(login_url, wait_until="commit", timeout=60000)
        except Exception:
            pass
        await cdp.send("Page.startScreencast",
                       {"format": "jpeg", "quality": _JPEG_QUALITY,
                        "maxWidth": _MAX_W, "maxHeight": _MAX_H, "everyNthFrame": 1})
        await ws.send_json({"type": "ready", "w": VIEWPORT["width"], "h": VIEWPORT["height"]})

        # Assisted auto-login (if the operator supplied credentials) runs as a background task so the
        # stream keeps flowing and the operator watches it happen / takes over for CAPTCHA/OTP.
        asyncio.create_task(_auto_login(page, pend.get("creds"), ws))

        async def sender():
            last = -1
            start_t = time.time()
            while not stop.is_set():
                if latest["seq"] != last and latest["data"]:
                    last = latest["seq"]
                    try:
                        await ws.send_json({"type": "frame", "data": latest["data"]})
                    except Exception:
                        stop.set(); break
                if time.time() - start_t > _MAX_SESSION:
                    try:
                        await ws.send_json({"type": "timeout"})
                    except Exception:
                        pass
                    stop.set(); break
                await asyncio.sleep(_FRAME_INTERVAL)

        async def receiver():
            while not stop.is_set():
                try:
                    msg = await ws.receive_json()
                except Exception:
                    stop.set(); break
                mt = msg.get("type")
                if mt == "capture":
                    try:
                        ss = await ctx.storage_state()
                        _CAPTURED[token] = {"ss": ss, "created": time.time()}
                        captured["ok"] = True
                    except Exception as e:
                        captured["err"] = str(e)
                    stop.set(); break
                elif mt == "cancel":
                    stop.set(); break
                else:
                    try:
                        await _dispatch_input(cdp, msg)
                    except Exception:
                        pass

        await asyncio.gather(sender(), receiver())
    finally:
        try:
            if cdp is not None:
                await cdp.send("Page.stopScreencast")
        except Exception:
            pass
        try:
            if browser is not None:
                await browser.close()
        except Exception:
            pass
        try:
            await p.stop()                               # fully release Playwright before the crawl
        except Exception:
            pass

    # Teardown complete -> now it is safe for the client to start the (sync-Playwright) crawl.
    try:
        if captured["ok"]:
            await ws.send_json({"type": "captured"})
        elif captured["err"]:
            await ws.send_json({"type": "error", "detail": "capture failed: " + captured["err"]})
    except Exception:
        pass
