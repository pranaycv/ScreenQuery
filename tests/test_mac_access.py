import json
import unittest
from pathlib import Path

from screenquery.mac_access import consume_prompt, load_asked, prompt_decision


class PromptDecisionTests(unittest.TestCase):
    def test_granted_access_does_not_ask(self):
        self.assertEqual(prompt_decision(True, False, False), "ready")
        self.assertEqual(prompt_decision(True, True, True), "ready")

    def test_first_denial_asks_once(self):
        self.assertEqual(prompt_decision(False, False, False), "ask")
        self.assertEqual(prompt_decision(False, True, False), "blocked")

    def test_menu_retry_asks_again(self):
        self.assertEqual(prompt_decision(False, True, True), "ask")


class AskedFlagTests(unittest.TestCase):
    def test_consume_records_the_ask_and_blocks_the_next_one(self):
        path = self._path()
        self.assertEqual(consume_prompt("screen", False, False, path), "ask")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["screen"], True)
        self.assertEqual(consume_prompt("screen", False, False, path), "blocked")
        self.assertEqual(consume_prompt("listen", False, False, path), "ask")
        self.assertTrue(load_asked(path)["listen"])

    def test_retry_asks_even_after_the_flag_is_set(self):
        path = self._path()
        consume_prompt("screen", False, False, path)
        self.assertEqual(consume_prompt("screen", False, True, path), "ask")

    def test_corrupt_file_is_treated_as_not_asked(self):
        path = self._path()
        path.write_text("{", encoding="utf-8")
        self.assertEqual(load_asked(path), {})
        self.assertEqual(consume_prompt("screen", False, False, path), "ask")

    def _path(self) -> Path:
        import tempfile

        directory = Path(tempfile.mkdtemp(prefix="screenquery-access-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        return directory / "tcc-asked.json"


if __name__ == "__main__":
    unittest.main()
