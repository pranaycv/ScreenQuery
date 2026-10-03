"""Shift chords.

Shift+S+P captures the front window. Shift+S+O starts a drag-to-crop.
Shift must already be held. Either letter order works. A chord fires once,
until one of its letters is released. Releasing Shift cancels a partial chord.
Shift+S alone does not fire.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Union


class ChordKey(Enum):
    S = "s"
    P = "p"
    O = "o"
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


ChordEvent = Union[Flags, KeyDown, KeyUp]

# Virtual key codes used when the listener does not supply a character.
ANSI_S = 0x01
ANSI_O = 0x1F
ANSI_P = 0x23
WIN_S = 0x53
WIN_O = 0x4F
WIN_P = 0x50


class ChordState:
    def __init__(self) -> None:
        self.shift_down = False
        self.s_down = False
        self.p_down = False
        self.o_down = False
        self._latched = False
        self._latch: str | None = None

    def handle(self, event: ChordEvent):
        if isinstance(event, Flags):
            # A new Shift press starts a fresh chord. A letter that was still
            # marked down from a missed key-up must not complete Shift+S.
            if event.shift and not self.shift_down:
                self._clear_letters()
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
            elif event.key is ChordKey.O:
                self.o_down = True
            return self._fire_if_ready()
        if event.key is ChordKey.S:
            self.s_down = False
        elif event.key is ChordKey.P:
            self.p_down = False
        elif event.key is ChordKey.O:
            self.o_down = False
        self._release_latch()
        return False

    def _fire_if_ready(self):
        """'window' for Shift+S+P, 'region' for Shift+S+O, otherwise False.

        If P and O are both down, the window chord wins.
        """
        if not self.shift_down or self._latched or not self.s_down:
            return False
        if self.p_down:
            self._latched = True
            self._latch = "window"
            return "window"
        if self.o_down:
            self._latched = True
            self._latch = "region"
            return "region"
        return False

    def _release_latch(self) -> None:
        if self._latch == "window" and not (self.s_down and self.p_down):
            self._latched = False
            self._latch = None
        elif self._latch == "region" and not (self.s_down and self.o_down):
            self._latched = False
            self._latch = None

    def reject_false_chord(self) -> None:
        """Hardware says the chord letters are not down, so the latch was wrong."""
        self._clear_letters()

    def _clear_letters(self) -> None:
        self.s_down = False
        self.p_down = False
        self.o_down = False
        self._latched = False
        self._latch = None


_BY_CODE = {
    ANSI_S: ChordKey.S,
    WIN_S: ChordKey.S,
    ANSI_P: ChordKey.P,
    WIN_P: ChordKey.P,
    ANSI_O: ChordKey.O,
    WIN_O: ChordKey.O,
}
_BY_CHAR = {"s": ChordKey.S, "p": ChordKey.P, "o": ChordKey.O}


def chord_key(key_code: int | None, characters: str | None) -> ChordKey:
    """S, P, and O only. Any other character does not count.

    If the glyph and the key code name different letters, the event is ignored
    so one key cannot satisfy two letters.
    """
    by_code = _BY_CODE.get(key_code, ChordKey.OTHER)
    trimmed = ""
    if characters:
        trimmed = characters.strip().lower()
    by_char = _BY_CHAR.get(trimmed, ChordKey.OTHER)
    if by_char is not ChordKey.OTHER:
        if by_code is not ChordKey.OTHER and by_code is not by_char:
            return ChordKey.OTHER
        return by_char
    if trimmed:
        return ChordKey.OTHER
    return by_code
