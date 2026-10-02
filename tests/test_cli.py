import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def test_check_prints_version_without_opening_a_window(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "screenquery", "--check"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("ScreenQuery 1.0.0", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_check_writes_a_marker_file_when_asked(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "check.txt"
            env = os.environ.copy()
            env["SCREENQUERY_CHECK_FILE"] = str(marker)
            subprocess.run(
                [sys.executable, "-m", "screenquery", "--check"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertIn("ScreenQuery 1.0.0", marker.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
