import unittest

from screenquery.capture import NO_WINDOW, Display, choose_window, crop_box, display_containing, resolve_capture


def _win(pid, name, number, width=800, height=600, layer=0, alpha=1):
    return {
        "kCGWindowOwnerPID": pid,
        "kCGWindowOwnerName": name,
        "kCGWindowNumber": number,
        "kCGWindowLayer": layer,
        "kCGWindowAlpha": alpha,
        "kCGWindowBounds": {"Width": width, "Height": height},
    }


class ChooseWindowTests(unittest.TestCase):
    def test_skips_screenquery_and_picks_the_front_app(self):
        windows = [
            _win(10, "ScreenQuery", 1),
            _win(20, "Notes", 2, width=40, height=40),
            _win(20, "Notes", 3),
            _win(30, "Safari", 4),
        ]
        chosen = choose_window(windows, my_pid=10, front_pid=20)
        self.assertEqual(chosen["kCGWindowNumber"], 3)

    def test_skips_our_process_even_if_it_is_frontmost(self):
        windows = [
            _win(10, "Python", 1),
            _win(30, "Safari", 4),
        ]
        chosen = choose_window(windows, my_pid=10, front_pid=10)
        self.assertEqual(chosen["kCGWindowNumber"], 4)

    def test_none_when_nothing_usable(self):
        windows = [_win(10, "ScreenQuery", 1), _win(11, "Dock", 2)]
        self.assertIsNone(choose_window(windows, my_pid=99, front_pid=None))
        self.assertIn("Focus the window", NO_WINDOW)

    def test_skips_screen_recording_prompt_for_the_front_app(self):
        windows = [
            _win(1, "universalAccessAuthWarn", 9, width=461, height=181),
            _win(20, "Safari", 3),
            _win(30, "Notes", 4),
        ]
        chosen = choose_window(windows, my_pid=10, front_pid=20)
        self.assertEqual(chosen["kCGWindowNumber"], 3)

    def test_prompt_as_front_process_still_picks_a_real_window(self):
        windows = [
            _win(1, "universalAccessAuthWarn", 9, width=461, height=181),
            _win(20, "Safari", 3),
        ]
        chosen = choose_window(windows, my_pid=10, front_pid=1)
        self.assertEqual(chosen["kCGWindowNumber"], 3)

    def test_fullscreen_when_the_window_shot_fails(self):
        windows = [_win(20, "Safari", 3), _win(30, "Notes", 4)]

        def capture_window(win):
            raise RuntimeError("unreadable")

        image = resolve_capture(windows, 10, 20, capture_window, lambda: "SCREEN")
        self.assertEqual(image, "SCREEN")

    def test_extended_display_window_is_not_cropped_from_the_laptop(self):
        # Laptop is the main display at 2x. The front window sits on the
        # extended 1x display to its left (negative CoreGraphics X).
        window = {"X": -1820.0, "Y": 18.0, "Width": 1702.0, "Height": 965.0}
        laptop = Display(0, 0, 1792, 1120)
        extended = Display(-1920, -35, 1920, 1080)
        self.assertIs(display_containing(window, [laptop, extended]), extended)
        box = crop_box(window, extended, 1920, 1080)
        self.assertEqual(box, (100, 53, 1802, 1018))
        # The Retina laptop buffer is not this display, so it must be refused.
        self.assertIsNone(crop_box(window, extended, 3584, 2240))

    def test_retina_laptop_window_scales_points_to_pixels(self):
        window = {"X": 100.0, "Y": 80.0, "Width": 800.0, "Height": 600.0}
        laptop = Display(0, 0, 1792, 1120)
        self.assertIs(display_containing(window, [laptop]), laptop)
        self.assertEqual(crop_box(window, laptop, 3584, 2240), (200, 160, 1800, 1360))

    def test_fullscreen_when_no_usable_window(self):
        windows = [_win(1, "universalAccessAuthWarn", 9), _win(10, "ScreenQuery", 1)]
        image = resolve_capture(windows, 10, 1, lambda win: "WIN", lambda: "SCREEN")
        self.assertEqual(image, "SCREEN")


if __name__ == "__main__":
    unittest.main()
