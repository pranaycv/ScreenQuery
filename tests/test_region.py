import unittest
from unittest import mock

from PIL import Image

from screenquery.capture import Display, clip_to_display, grab_region
from screenquery.region import (
    RegionSelector,
    ScreenGeom,
    appkit_point_to_cg,
    cg_point_to_appkit,
    normalize_rect,
)


class RegionGeometryTests(unittest.TestCase):
    def test_click_is_not_a_rectangle(self):
        self.assertIsNone(normalize_rect(10, 10, 12, 30))
        rect = normalize_rect(30, 80, 10, 40)
        self.assertEqual(rect, {"X": 10, "Y": 40, "Width": 20, "Height": 40})

    def test_appkit_point_on_a_display_above_the_primary_flips_per_screen(self):
        primary = ScreenGeom(ax=0, ay=0, width=1440, height=900, cx=0, cy=0)
        above = ScreenGeom(ax=0, ay=900, width=1920, height=1080, cx=0, cy=-1080)
        self.assertEqual(appkit_point_to_cg(100, 800, [primary, above]), (100, 100))
        self.assertEqual(cg_point_to_appkit(100, 100, [primary, above]), (100, 800))
        # Near the top of the upper display: AppKit Y is high, CoreGraphics Y is just below its top.
        self.assertEqual(appkit_point_to_cg(20, 1970, [primary, above]), (20, -1070))
        self.assertEqual(cg_point_to_appkit(20, -1070, [primary, above]), (20, 1970))
        self.assertIsNone(appkit_point_to_cg(-5, 10, [primary, above]))

    def test_word_on_the_extended_display_is_not_taken_from_the_laptop(self):
        laptop = Display(0, 0, 1792, 1120, display_id=1)
        extended = Display(-1920, -35, 1920, 1080, display_id=2)
        bounds = {"X": -1800.0, "Y": 45.0, "Width": 40.0, "Height": 16.0}
        self.assertIsNone(clip_to_display(bounds, laptop))
        clipped = clip_to_display(bounds, extended)
        self.assertEqual(clipped["X"], -1800)
        self.assertEqual(clipped["Width"], 40)

        external = Image.new("RGB", (1920, 1080), (9, 9, 9))
        external.putpixel((120, 80), (1, 2, 3))
        laptop_image = Image.new("RGB", (3584, 2240), (8, 8, 8))

        def fake_image(display_id):
            return external if display_id == 2 else laptop_image

        with mock.patch("screenquery.capture.screen_recording_allowed", return_value=True), mock.patch(
            "screenquery.capture._macos_displays", return_value=[laptop, extended]
        ), mock.patch("screenquery.capture._display_image", side_effect=fake_image):
            shot = grab_region(bounds)
        self.assertEqual(shot.size, (40, 16))
        self.assertEqual(shot.getpixel((0, 0)), (1, 2, 3))

    def test_a_rectangle_across_two_displays_keeps_both_sides(self):
        right = Display(0, 0, 100, 100, display_id=1)
        left = Display(-100, 0, 100, 100, display_id=2)

        def fake_image(display_id):
            color = (0, 0, 255) if display_id == 1 else (255, 0, 0)
            return Image.new("RGB", (100, 100), color)

        with mock.patch("screenquery.capture.screen_recording_allowed", return_value=True), mock.patch(
            "screenquery.capture._macos_displays", return_value=[right, left]
        ), mock.patch("screenquery.capture._display_image", side_effect=fake_image):
            shot = grab_region({"X": -10, "Y": 0, "Width": 20, "Height": 10})
        self.assertEqual(shot.size, (20, 10))
        self.assertEqual(shot.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(shot.getpixel((19, 0)), (0, 0, 255))

    def test_a_second_click_does_not_restart_the_drag(self):
        selector = RegionSelector(lambda _bounds: None)
        selector._begin_drag(10, 20)
        selector._begin_drag(80, 90)
        self.assertEqual(selector._points(), ((10, 20), (80, 90)))

    def test_crop_view_accepts_the_first_click_without_activating(self):
        from AppKit import NSBackingStoreBuffered, NSMakeRect, NSWindowStyleMaskBorderless

        from screenquery.region import _panel_class, _view_class

        view = _view_class().alloc().initWithFrame_(NSMakeRect(0, 0, 20, 20))
        self.assertTrue(view.acceptsFirstMouse_(None))
        panel = _panel_class().alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 20, 20),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        try:
            self.assertTrue(panel.canBecomeKeyWindow())
            self.assertFalse(panel.canBecomeMainWindow())
        finally:
            panel.close()

    def test_escape_cancels_a_crop_and_does_not_capture(self):
        import Quartz

        from screenquery.hotkey_listener import HotkeyListener, set_escape_handler

        fired = []
        listener = HotkeyListener(lambda kind: fired.append(kind))
        cancelled = []
        set_escape_handler(lambda: cancelled.append("cancel"))
        try:
            event = Quartz.CGEventCreateKeyboardEvent(None, 53, True)
            listener._handle_mac(Quartz.kCGEventKeyDown, event)
            letter = Quartz.CGEventCreateKeyboardEvent(None, 0x01, True)
            listener._handle_mac(Quartz.kCGEventKeyDown, letter)
        finally:
            set_escape_handler(None)
        self.assertEqual(cancelled, ["cancel"])
        self.assertEqual(fired, [])


if __name__ == "__main__":
    unittest.main()
