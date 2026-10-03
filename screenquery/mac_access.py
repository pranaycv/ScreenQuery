"""One-shot macOS privacy prompts.

CGDisplayCreateImage and CGWindowListCreateImage show the Screen Recording
dialog on every call when the grant is missing. CGRequest* shows it once, and
only if this process asks. Asking again on each capture is what kept the
dialog on screen. The asked-flag file stops a relaunch from asking again.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("screenquery")

LISTEN_DENIED = (
    "Turn on ScreenQuery under Privacy & Security → Input Monitoring, then open ScreenQuery again."
)


def prompt_decision(allowed: bool, already_asked: bool, user_retry: bool) -> str:
    """ready, ask, or blocked. A retry is the only way to ask a second time."""
    if allowed:
        return "ready"
    if user_retry or not already_asked:
        return "ask"
    return "blocked"


def asked_path(home: Path | None = None) -> Path:
    root = home or Path.home()
    return root / "Library" / "Application Support" / "ScreenQuery" / "tcc-asked.json"


def load_asked(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def mark_asked(path: Path, kind: str) -> None:
    data = load_asked(path)
    data[kind] = True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def consume_prompt(kind: str, allowed: bool, user_retry: bool, path: Path) -> str:
    """Record an ask before the system dialog, so a second capture cannot repeat it."""
    decision = prompt_decision(allowed, bool(load_asked(path).get(kind)), user_retry)
    if decision == "ask":
        mark_asked(path, kind)
    return decision


def request_screen_recording(user_retry: bool = False, path: Path | None = None, on_denied=None) -> bool:
    from screenquery.capture import screen_recording_allowed

    store = path or asked_path()
    if screen_recording_allowed():
        return True
    if consume_prompt("screen", False, user_retry, store) != "ask":
        return False
    try:
        import Quartz

        log.info("Asking once for Screen Recording")
        granted = bool(Quartz.CGRequestScreenCaptureAccess())
        if not granted and on_denied is not None:
            on_denied()
        return granted
    except Exception:
        log.exception("Screen Recording request failed")
        return False


def request_listen(user_retry: bool = False, path: Path | None = None, on_denied=None) -> bool:
    from screenquery.hotkey_listener import listen_allowed

    store = path or asked_path()
    if listen_allowed():
        return True
    if consume_prompt("listen", False, user_retry, store) != "ask":
        return False
    try:
        import Quartz

        if not hasattr(Quartz, "CGRequestListenEventAccess"):
            log.info("CGRequestListenEventAccess is missing")
            return False
        from Foundation import NSThread

        log.info("Asking once for Input Monitoring on main=%s", bool(NSThread.isMainThread()))
        result = Quartz.CGRequestListenEventAccess()
        log.info("Input Monitoring request returned %r", result)
        granted = bool(result)
        if not granted and on_denied is not None:
            on_denied()
        return granted
    except Exception:
        log.exception("Input Monitoring request failed")
        return False
