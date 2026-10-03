import unittest

from screenquery.ribbon import panel_height, plain_block, ribbon_is_error, ribbon_lines, wrapped_rows
from screenquery.status import Status


class RibbonTextTests(unittest.TestCase):
    def test_two_still_lines_path_then_answer(self):
        path_line, response_line = ribbon_lines(
            Status(
                answer="A compiler error on line 4.",
                clipboard_copied=True,
                save_display="~/ScreenQuery/a.png",
            )
        )
        self.assertEqual(path_line, "~/ScreenQuery/a.png")
        self.assertEqual(response_line, "A compiler error on line 4.")
        self.assertNotIn("clipboard", response_line)
        self.assertNotIn("clipboard", path_line)

    def test_error_is_the_response_line(self):
        status = Status(llm_error="Your API key has been invalidated. (HTTP 401)", clipboard_copied=True)
        path_line, response_line = ribbon_lines(status)
        self.assertEqual(path_line, "Not saved")
        self.assertIn("invalidated", response_line)
        self.assertTrue(ribbon_is_error(status))

    def test_waiting_line_stays_put(self):
        path_line, response_line = ribbon_lines(Status(llm_working=True, save_display="~/a.png"))
        self.assertEqual(path_line, "~/a.png")
        self.assertEqual(response_line, "Asking OpenAI…")

    def test_answer_keeps_each_sentence_on_its_own_line(self):
        answer = "This is a button.\nIt saves your work.\nClick it when you are done."
        _path, response = ribbon_lines(Status(answer=answer, save_display="~/a.png"))
        self.assertEqual(response, answer)
        self.assertEqual(plain_block("  Hello   there. \n\n Next line.  "), "Hello there.\n\nNext line.")
        self.assertGreater(wrapped_rows(answer, 240), 1)
        self.assertGreater(panel_height(answer, 240), panel_height("Asking OpenAI…", 240))
        self.assertEqual(wrapped_rows(answer, 240), 3)


class RibbonShapeTests(unittest.TestCase):
    def test_popup_corners_are_clear_and_the_face_is_light_blue(self):
        from AppKit import (
            NSBitmapImageRep,
            NSCalibratedRGBColorSpace,
            NSGraphicsContext,
            NSMakeRect,
        )

        from screenquery.ribbon import CORNER_RADIUS, _ribbon_content_class

        width, height = 220, 80
        self.assertGreaterEqual(CORNER_RADIUS, 16)
        view = _ribbon_content_class().alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
        bitmap = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
            None,
            width,
            height,
            8,
            4,
            True,
            False,
            NSCalibratedRGBColorSpace,
            0,
            0,
        )
        context = NSGraphicsContext.graphicsContextWithBitmapImageRep_(bitmap)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.setCurrentContext_(context)
        try:
            view.drawRect_(view.bounds())
        finally:
            NSGraphicsContext.restoreGraphicsState()

        def sample(x, y):
            color = bitmap.colorAtX_y_(x, y).colorUsingColorSpaceName_(NSCalibratedRGBColorSpace)
            return (
                float(color.redComponent()),
                float(color.greenComponent()),
                float(color.blueComponent()),
                float(color.alphaComponent()),
            )

        for point in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
            self.assertLess(sample(*point)[3], 0.05, point)
        red, _green, blue, alpha = sample(width // 2, height // 2)
        self.assertGreater(alpha, 0.7)
        self.assertGreater(blue, red)
        self.assertGreater(blue, 0.7)


if __name__ == "__main__":
    unittest.main()
