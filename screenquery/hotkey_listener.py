"""Global Shift+S+P listener. Keys are observed, not swallowed."""

from __future__ import annotations

import time
from typing import Callable

from screenquery.chord import ChordState, Flags, KeyDown, KeyUp, chord_key


class HotkeyListener:
    def __init__(self, on_trigger: Callable[[], None]) -> None:
        self._on_trigger = on_trigger
        self._state = ChordState()
        self._listener = None
        self._last_fire = 0.0

    def start(self) -> None:
        self.stop()
        self._state = ChordState()
        from pynput import keyboard

        self._listener = keyboard.Listener(on_press=self._press, on_release=self._release)
        self._listener.start()

    def stop(self) -> None:
        listener = self._listener
        self._listener = None
        if listener is not None:
            listener.stop()

    def _press(self, key) -> None:
        if _is_shift(key):
            self._state.handle(Flags(True))
            return
        # Case is not used as a stand-in for Shift. Caps Lock produces S and P
        # without the modifier, and that must not capture the screen.
        mapped = _map(key)
        if self._state.handle(KeyDown(mapped, shift=self._state.shift_down)):
            self._fire()

    def _release(self, key) -> None:
        if _is_shift(key):
            self._state.handle(Flags(False))
            return
        self._state.handle(KeyUp(_map(key)))

    def _fire(self) -> None:
        now = time.monotonic()
        if now - self._last_fire < 0.75:
            return
        self._last_fire = now
        self._on_trigger()


def _is_shift(key) -> bool:
    from pynput import keyboard

    return key in {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r}


def _map(key):
    characters = getattr(key, "char", None)
    key_code = getattr(key, "vk", None)
    return chord_key(key_code, characters)
