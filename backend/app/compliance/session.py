"""
session.py -- acquire an authorized authenticated session via a LOCAL HEADED login.

The operator signs in to the target in a real, visible browser and clears any CAPTCHA / OTP / 2FA
themselves; this module then captures the resulting session (Playwright storage_state) so a
read-only authenticated scan (auth.crawl_authenticated) can assess the logged-in area. The operator
solves every challenge -- we never solve or bypass anti-bot.

Credential handling: this module never receives, sees, types or stores the operator's username,
password or OTP. The operator enters them directly into the real browser. Only the POST-LOGIN
session state (cookies + localStorage) is captured, held in memory for the scan, and discarded.

Lifecycle: Playwright's sync API is thread-bound, so each login session runs in its own worker
thread that owns the playwright/browser/context for its whole life. The thread opens the headed
browser at the login URL and blocks on an Event until the operator signals "I'm in"; it then
captures storage_state and shuts the browser down. A registry maps an opaque token to the handle.

This headed path targets a server running ON the operator's machine (the demo laptop): the window
appears locally. A hosted deployment feeds the same storage_state via a CDP-screencast front-end or
a "bring your own session" upload instead (a headless server has no display for a headed window).
"""
from __future__ import annotations
import secrets
import threading
import time

from .crawler import _UA_STRING

_SESSIONS: dict[str, "SessionHandle"] = {}
_LOCK = threading.Lock()
_MAX_LOGIN_WAIT = 600          # operator has up to 10 minutes to finish logging in
_TTL = 1800                    # stale handles are reaped after 30 minutes


class SessionHandle:
    def __init__(self, login_url: str, headed: bool = True):
        self.token = secrets.token_urlsafe(16)
        self.login_url = login_url
        self.headed = headed
        self.proceed_event = threading.Event()     # set by capture(): operator says "I'm logged in"
        self.done_event = threading.Event()         # set by the worker when capture/teardown finishes
        self.ready_event = threading.Event()        # set once the login page is open
        self.storage_state: dict | None = None
        self.error: str | None = None
        self.created = time.time()
        self.thread: threading.Thread | None = None


def _worker(h: SessionHandle):
    """Owns Playwright for this login session's whole life (sync API is thread-bound)."""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not h.headed,
                                        args=["--disable-blink-features=AutomationControlled"])
            ctx = browser.new_context(user_agent=_UA_STRING, locale="en-US",
                                      timezone_id="Asia/Kolkata",
                                      viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            try:
                page.goto(h.login_url, wait_until="commit", timeout=60000)
            except Exception:
                pass
            h.ready_event.set()
            # Block here while the operator signs in and clears CAPTCHA/OTP in the real window.
            # The Chromium process runs independently, so manual interaction works while we wait.
            proceeded = h.proceed_event.wait(timeout=_MAX_LOGIN_WAIT)
            if proceeded:
                try:
                    h.storage_state = ctx.storage_state()
                except Exception as e:
                    h.error = "could not capture session: " + str(e)
            else:
                h.error = "login window timed out before the operator confirmed sign-in"
            try:
                browser.close()
            except Exception:
                pass
    except Exception as e:
        h.error = "login browser failed to start: " + str(e)
    finally:
        h.done_event.set()


def _reap():
    now = time.time()
    with _LOCK:
        for tok in [t for t, h in _SESSIONS.items() if now - h.created > _TTL]:
            _SESSIONS.pop(tok, None)


def start_login(login_url: str, headed: bool = True) -> dict:
    """Open a headed browser at the login URL and return a token. The operator then signs in."""
    _reap()
    h = SessionHandle(login_url, headed=headed)
    h.thread = threading.Thread(target=_worker, args=(h,), daemon=True)
    h.thread.start()
    with _LOCK:
        _SESSIONS[h.token] = h
    h.ready_event.wait(timeout=20)                  # let the window open before returning
    return {"token": h.token, "login_url": login_url, "ready": h.ready_event.is_set()}


def capture(token: str, timeout: float = 120.0) -> dict:
    """Signal that the operator has finished logging in; capture and return the session state.
    Raises if the token is unknown or capture failed. The handle is removed afterwards."""
    with _LOCK:
        h = _SESSIONS.get(token)
    if h is None:
        raise KeyError("unknown or expired session token")
    h.proceed_event.set()
    if not h.done_event.wait(timeout=timeout):
        raise TimeoutError("timed out waiting for the login session to capture")
    with _LOCK:
        _SESSIONS.pop(token, None)
    if h.error or not h.storage_state:
        raise RuntimeError(h.error or "no session captured")
    return h.storage_state


def cancel(token: str) -> bool:
    """Abort a pending login (operator closed the flow). Tears the worker down."""
    with _LOCK:
        h = _SESSIONS.pop(token, None)
    if h is None:
        return False
    h.proceed_event.set()                           # unblock the worker so it tears down
    h.done_event.wait(timeout=10)
    return True
