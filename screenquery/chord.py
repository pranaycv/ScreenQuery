"""Shift+S+P chord.

Shift must already be held when S and P go down (either order). The chord fires
once until S or P is released. Releasing Shift cancels a partial chord.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ChordKey(Enum):
    S = "s"
    P = "p"
    OTHER = "other"


@dataclass(frozen=True)
class Flags:
    shift: bool


@dataclass(frozen=True)
class KeyDown:
    key: ChordKey
    shift: bool
    is_repeat: bool = False


@dataclass(frozen=True)
class KeyUp:
    key: ChordKey


ChordEvent = Flags | KeyDown | KeyUp

# Virtual key codes used when the listener does not supply a character.
ANSI_S = 0x01
ANSI_P = 0x23
WIN_S = 0x53
WIN_P = 0x50


class ChordState:
    def __init__(self) -> None:
        self.shift_down = False
        self.s_down = False
        self.p_down = False
        self._latched = False

    def handle(self, event: ChordEvent) -> bool:
        if isinstance(event, Flags):
            self.shift_down = event.shift
            if not event.shift:
                self._clear_letters()
            return False
        if isinstance(event, KeyDown):
            self.shift_down = event.shift
            if not event.shift:
                self._clear_letters()
                return False
            if event.is_repeat:
                return False
            if event.key is ChordKey.S:
                self.s_down = True
            elif event.key is ChordKey.P:
                self.p_down = True
            return self._fire_if_ready()
        if event.key is ChordKey.S:
            self.s_down = False
        elif event.key is ChordKey.P:
            self.p_down = False
        if not self.s_down or not self.p_down:
            self._latched = False
        return False

    def _fire_if_ready(self) -> bool:
        if not (self.shift_down and self.s_down and self.p_down) or self._latched:
            return False
        self._latched = True
        return True

    def _clear_letters(self) -> None:
        self.s_down = False
        self.p_down = False
        self._latched = False


def chord_key(key_code: int | None, characters: str | None) -> ChordKey:
    """Prefer the character the layout produced, then known virtual key codes."""
    if characters:
        trimmed = characters.strip().lower()
        if trimmed == "s":
            return ChordKey.S
        if trimmed == "p":
            return ChordKey.P
        if trimmed:
            return ChordKey.OTHER
    if key_code in (ANSI_S, WIN_S):
        return ChordKey.S
    if key_code in (ANSI_P, WIN_P):
        return ChordKey.P
    return ChordKey.OTHER
