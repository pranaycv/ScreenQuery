import unittest

from screenquery.chord import (
    ANSI_P,
    ANSI_S,
    WIN_P,
    WIN_S,
    ChordKey,
    ChordState,
    Flags,
    KeyDown,
    KeyUp,
    chord_key,
)


class ChordStateTests(unittest.TestCase):
    def test_shift_then_s_then_p_fires_once(self):
        state = ChordState()
        self.assertFalse(state.handle(Flags(True)))
        self.assertFalse(state.handle(KeyDown(ChordKey.S, shift=True)))
        self.assertTrue(state.handle(KeyDown(ChordKey.P, shift=True)))
        self.assertFalse(state.handle(KeyDown(ChordKey.P, shift=True, is_repeat=True)))
        self.assertFalse(state.handle(KeyDown(ChordKey.S, shift=True, is_repeat=True)))

    def test_p_then_s_while_shift_held_fires(self):
        state = ChordState()
        state.handle(Flags(True))
        self.assertFalse(state.handle(KeyDown(ChordKey.P, shift=True)))
        self.assertTrue(state.handle(KeyDown(ChordKey.S, shift=True)))

    def test_letters_without_shift_do_not_fire(self):
        state = ChordState()
        self.assertFalse(state.handle(KeyDown(ChordKey.S, shift=False)))
        self.assertFalse(state.handle(KeyDown(ChordKey.P, shift=False)))
        self.assertFalse(state.s_down)
        self.assertFalse(state.p_down)

    def test_shift_after_letters_does_not_count_earlier_presses(self):
        state = ChordState()
        state.handle(KeyDown(ChordKey.S, shift=False))
        state.handle(Flags(True))
        self.assertFalse(state.handle(KeyDown(ChordKey.P, shift=True)))
        self.assertFalse(state.s_down)
        self.assertTrue(state.p_down)

    def test_release_and_press_again_fires_again(self):
        state = ChordState()
        state.handle(Flags(True))
        state.handle(KeyDown(ChordKey.S, shift=True))
        self.assertTrue(state.handle(KeyDown(ChordKey.P, shift=True)))
        state.handle(KeyUp(ChordKey.P))
        self.assertTrue(state.handle(KeyDown(ChordKey.P, shift=True)))

    def test_releasing_shift_cancels_partial_chord(self):
        state = ChordState()
        state.handle(Flags(True))
        state.handle(KeyDown(ChordKey.S, shift=True))
        state.handle(KeyDown(ChordKey.P, shift=True))
        state.handle(Flags(False))
        self.assertFalse(state.s_down)
        self.assertFalse(state.p_down)
        self.assertFalse(state.handle(Flags(True)))
        self.assertFalse(state.s_down)
        self.assertFalse(state.p_down)

    def test_other_keys_do_not_complete_the_chord(self):
        state = ChordState()
        state.handle(Flags(True))
        state.handle(KeyDown(ChordKey.S, shift=True))
        self.assertFalse(state.handle(KeyDown(ChordKey.OTHER, shift=True)))
        self.assertTrue(state.s_down)

    def test_key_mapping_prefers_characters(self):
        self.assertEqual(chord_key(0, "S"), ChordKey.S)
        self.assertEqual(chord_key(0, "p"), ChordKey.P)
        self.assertEqual(chord_key(ANSI_S, "d"), ChordKey.OTHER)
        self.assertEqual(chord_key(ANSI_S, None), ChordKey.S)
        self.assertEqual(chord_key(ANSI_P, ""), ChordKey.P)
        self.assertEqual(chord_key(WIN_S, None), ChordKey.S)
        self.assertEqual(chord_key(WIN_P, None), ChordKey.P)
        self.assertEqual(chord_key(9, None), ChordKey.OTHER)


if __name__ == "__main__":
    unittest.main()
