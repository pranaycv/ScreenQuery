import unittest
from datetime import datetime, timezone
from pathlib import Path

from screenquery.paths import abbreviate, filename, resolve_directory, unique_filename


class DestinationPathTests(unittest.TestCase):
    def setUp(self):
        self.home = Path("/Users/ada")
        self.when = datetime(2026, 10, 1, 22, 35, 7, 123000, tzinfo=timezone.utc)

    def test_default_directory_uses_home_and_date(self):
        path = resolve_directory(None, self.when, self.home)
        self.assertEqual(path, self.home / "ScreenQuery" / "2026-10-01")

    def test_empty_custom_folder_uses_default(self):
        path = resolve_directory("   ", self.when, self.home)
        self.assertEqual(path, self.home / "ScreenQuery" / "2026-10-01")

    def test_custom_folder_gets_a_date_subfolder(self):
        path = resolve_directory("/tmp/shots/", self.when, self.home)
        self.assertEqual(path, Path("/tmp/shots") / "2026-10-01")

    def test_tilde_custom_folder_expands_against_provided_home(self):
        path = resolve_directory("~/Pictures/Shots", self.when, self.home)
        self.assertEqual(path, Path("/Users/ada/Pictures/Shots") / "2026-10-01")

    def test_relative_custom_folder_is_under_home(self):
        path = resolve_directory("Shots", self.when, self.home)
        self.assertEqual(path, Path("/Users/ada/Shots") / "2026-10-01")

    def test_filename_is_time_only(self):
        self.assertEqual(filename(self.when), "ScreenQuery-223507-123.png")
        self.assertNotIn("2026", filename(self.when))
        self.assertNotIn("1001", filename(self.when))

    def test_unique_filename_appends_a_counter(self):
        preferred = "ScreenQuery-223507-123.png"
        self.assertEqual(unique_filename(preferred, set()), preferred)
        self.assertEqual(unique_filename(preferred, {preferred}), "ScreenQuery-223507-123-2.png")
        self.assertEqual(
            unique_filename(preferred, {preferred, "ScreenQuery-223507-123-2.png"}),
            "ScreenQuery-223507-123-3.png",
        )

    def test_path_abbreviation(self):
        home = Path("/Users/ada")
        shown = abbreviate(home / "ScreenQuery" / "2026-10-01" / "a.png", home)
        self.assertEqual(shown, "~/ScreenQuery/2026-10-01/a.png")
        self.assertEqual(abbreviate(Path("/tmp/a.png"), home), "/tmp/a.png")


if __name__ == "__main__":
    unittest.main()
