"""Global Shift+S+P and Shift+S+O listener. Keys are observed, not swallowed."""

from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Callable

from screenquery.chord import ANSI_O, ANSI_P, ANSI_S, ChordKey, ChordState, Flags, KeyDown, KeyUp

log = logging.getLogger("screenquery")

_SHIFT_CODES = (0x38, 0x3C)  # left and right Shift
_ESCAPE = 53
_LOGGED_MISSING = False
_escape_handler = None
_escape_lock = threading.Lock()


def set_escape_handler(handler) -> None:
    """While a crop is open, Esc on the existing hotkey tap cancels it."""
    global _escape_handler
    with _escape_lock:
        _escape_handler = handler


def current_escape_handler():
    with _escape_lock:
        return _escape_handler


class HotkeyListener:
    def __init__(self, on_trigger: Callable[[str], None]) -> None:
        self._on_trigger = on_trigger
        self._state = ChordState()
        self._listener = None
        self._thread: threading.Thread | None = None
        self._loop = None
        self._last_fire = 0.0
        self.running = False
        self._started = threading.Event()

    def start(self) -> None:
        self.stop()
        self._state = ChordState()
        if sys.platform == "darwin":
            self._start_mac()
            return
        self._start_pynput()
        self.running = self._listener is not None

    def stop(self) -> None:
        self.running = False
        loop = self._loop
        self._loop = None
        if loop is not None:
            try:
                from CoreFoundation import CFRunLoopStop

                CFRunLoopStop(loop)
            except Exception:
                log.exception("Could not stop the hotkey run loop")
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        listener = self._listener
        self._listener = None
        if listener is not None:
            listener.stop()

    def _start_mac(self) -> None:
        if not listen_allowed():
            _log_missing_once()
            return
        self._started.clear()
        self._thread = threading.Thread(target=self._run_tap, name="screenquery-hotkey", daemon=True)
        self._thread.start()
        self._started.wait(timeout=2.0)

    def _run_tap(self) -> None:
        import Quartz
        from CoreFoundation import (
            CFMachPortCreateRunLoopSource,
            CFRunLoopAddSource,
            CFRunLoopGetCurrent,
            CFRunLoopRun,
            kCFRunLoopCommonModes,
        )

        mask = (
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
            | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
            | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
        )
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            mask,
            self._tap,
            None,
        )
        if tap is None:
            self.running = False
            self._started.set()
            _log_missing_once()
            return
        source = CFMachPortCreateRunLoopSource(None, tap, 0)
        loop = CFRunLoopGetCurrent()
        self._loop = loop
        CFRunLoopAddSource(loop, source, kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        self.running = True
        self._started.set()
        CFRunLoopRun()
        # stop() clears _loop before joining. A newer tap may already be running.
        if self._loop is loop:
            self.running = False
            self._loop = None

    def _tap(self, _proxy, event_type, event, _refcon):
        try:
            self._handle_mac(event_type, event)
        except Exception:
            log.exception("Hotkey event failed")
        return event

    def _handle_mac(self, event_type, event) -> None:
        import Quartz

        keycode = int(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode))
        if event_type == Quartz.kCGEventKeyDown and keycode == _ESCAPE:
            handler = current_escape_handler()
            if handler is not None:
                try:
                    handler()
                except Exception:
                    log.exception("Crop cancel failed")
                return
        shift = bool(Quartz.CGEventGetFlags(event) & Quartz.kCGEventFlagMaskShift)
        if event_type == Quartz.kCGEventFlagsChanged:
            if keycode in _SHIFT_CODES:
                self._state.handle(Flags(shift))
            return
        if keycode == ANSI_S:
            letter = ChordKey.S
        elif keycode == ANSI_P:
            letter = ChordKey.P
        elif keycode == ANSI_O:
            letter = ChordKey.O
        else:
            return
        if event_type == Quartz.kCGEventKeyUp:
            self._state.handle(KeyUp(letter))
            return
        if event_type != Quartz.kCGEventKeyDown:
            return
        repeat = bool(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat))
        # Shift must be held on this event. Do not ask a second API that still
        # reports the key as up inside the tap.
        fired = self._state.handle(KeyDown(letter, shift=shift, is_repeat=repeat or _already_down(self._state, letter)))
        if fired:
            self._fire(fired)

    def _start_pynput(self) -> None:
        from pynput import keyboard

        self._listener = keyboard.Listener(on_press=self._press, on_release=self._release)
        self._listener.start()

    def _press(self, key) -> None:
        if _is_shift(key):
            self._state.handle(Flags(True))
            return
        mapped = _map(key)
        shift_down = self._state.shift_down
        fired = self._state.handle(KeyDown(mapped, shift=shift_down, is_repeat=_already_down(self._state, mapped)))
        if fired:
            self._fire(fired)

    def _release(self, key) -> None:
        if _is_shift(key):
            self._state.handle(Flags(False))
            return
        self._state.handle(KeyUp(_map(key)))

    def _fire(self, kind: str) -> None:
        now = time.monotonic()
        if now - self._last_fire < 0.75:
            return
        self._last_fire = now
        self._on_trigger(kind)


def listen_allowed() -> bool:
    try:
        import Quartz

        if hasattr(Quartz, "CGPreflightListenEventAccess"):
            return bool(Quartz.CGPreflightListenEventAccess())
    except Exception:
        log.exception("Could not check Input Monitoring")
    return False


def _log_missing_once() -> None:
    global _LOGGED_MISSING
    if _LOGGED_MISSING:
        return
    _LOGGED_MISSING = True
    log.warning(
        "Shift+S+P and Shift+S+O are off until ScreenQuery is allowed under "
        "Privacy & Security → Input Monitoring. Capture Now still works."
    )


def _is_shift(key) -> bool:
    from pynput import keyboard

    return key in {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r}


def _already_down(state, key) -> bool:
    if key is ChordKey.S:
        return state.s_down
    if key is ChordKey.P:
        return state.p_down
    if key is ChordKey.O:
        return state.o_down
    return False


def _map(key):
    from screenquery.chord import chord_key

    characters = getattr(key, "char", None)
    key_code = getattr(key, "vk", None)
    return chord_key(key_code, characters)
