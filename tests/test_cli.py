import subprocess
import sys
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


if __name__ == "__main__":
    unittest.main()
