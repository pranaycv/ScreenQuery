import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from screenquery.images import save_png, scale_size
from screenquery.keystore import Keystore, MemoryKeyring
from screenquery.login_item import macos_plist, windows_run_value
from screenquery.permissions_text import permission_help
from screenquery.service import perform_capture
from screenquery.settings_store import Settings, SettingsStore
from screenquery.status import Status, dismiss_seconds


class FakeImage:
    def save(self, path, format=None):
        Path(path).write_bytes(b"png")


class SettingsAndServiceTests(unittest.TestCase):
    def test_settings_round_trip_never_writes_a_key(self):
        store = SettingsStore(Path(self._tmp("settings.json")))
        store.save(Settings(save_enabled=False, llm_enabled=True, custom_folder="/tmp/shots", model="gpt-4o-mini"))
        raw = json.loads(store.path.read_text(encoding="utf-8"))
        self.assertNotIn("api_key", raw)
        loaded = store.load()
        self.assertFalse(loaded.save_enabled)
        self.assertTrue(loaded.llm_enabled)
        self.assertEqual(loaded.custom_folder, "/tmp/shots")
        self.assertEqual(loaded.model, "gpt-4o-mini")

    def test_leaked_key_in_settings_file_is_removed(self):
        path = Path(self._tmp("leaked.json"))
        path.write_text(json.dumps({"save_enabled": True, "api_key": "sk-leak"}), encoding="utf-8")
        store = SettingsStore(path)
        loaded = store.load()
        self.assertTrue(loaded.save_enabled)
        rewritten = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("api_key", rewritten)
        self.assertNotIn("sk-leak", path.read_text(encoding="utf-8"))

    def test_keystore_round_trip(self):
        store = Keystore(MemoryKeyring())
        self.assertIsNone(store.load())
        store.save("  sk-test  ")
        self.assertEqual(store.load(), "sk-test")
        store.delete()
        self.assertIsNone(store.load())

    def test_save_only_and_missing_key_and_both(self):
        home = Path("/Users/ada")
        image = object()
        saved = {}

        def save(img, folder):
            self.assertIs(img, image)
            saved["folder"] = folder
            return home / "ScreenQuery" / "2026-10-01" / "a.png"

        def explain(img, key, base_url, model):
            self.assertEqual(key, "sk-test")
            self.assertEqual(base_url, "https://api.openai.com/v1")
            self.assertEqual(model, "gpt-4o")
            return "A window."

        keys = {"value": "sk-test"}
        save_only = perform_capture(
            Settings(save_enabled=True, llm_enabled=False),
            image,
            save,
            explain,
            lambda: keys["value"],
            home,
        )
        self.assertEqual(save_only.save_display, "~/ScreenQuery/2026-10-01/a.png")
        self.assertIsNone(save_only.answer)

        missing = perform_capture(
            Settings(save_enabled=False, llm_enabled=True),
            image,
            save,
            explain,
            lambda: None,
            home,
        )
        self.assertIn("keychain", missing.llm_error.lower())
        self.assertIsNone(missing.answer)

        both = perform_capture(
            Settings(save_enabled=True, llm_enabled=True, custom_folder="/tmp/shots"),
            image,
            save,
            explain,
            lambda: keys["value"],
            home,
        )
        self.assertEqual(saved["folder"], "/tmp/shots")
        self.assertEqual(both.answer, "A window.")
        self.assertIsNotNone(both.save_full)

        off = perform_capture(
            Settings(False, False, clipboard_enabled=False),
            image,
            save,
            explain,
            lambda: None,
            home,
        )
        self.assertTrue(off.banner_is_error)

    def test_clipboard_is_on_by_default_and_failure_still_saves(self):
        self.assertTrue(Settings().clipboard_enabled)
        loaded = Settings.from_dict({"save_enabled": True})
        self.assertTrue(loaded.clipboard_enabled)

        copied = []

        def copy(img):
            copied.append(img)

        home = Path("/Users/ada")
        image = object()
        only_clip = perform_capture(
            Settings(save_enabled=False, llm_enabled=False, clipboard_enabled=True),
            image,
            lambda *_args: home / "nope.png",
            lambda *_args: "no",
            lambda: None,
            home,
            copy_png=copy,
        )
        self.assertEqual(copied, [image])
        self.assertTrue(only_clip.clipboard_copied)
        self.assertIsNone(only_clip.save_full)
        self.assertEqual(only_clip.to_dict()["clipboard_note"], "Screenshot is on the clipboard.")

        def boom(_img):
            raise RuntimeError("pasteboard busy")

        failed = perform_capture(
            Settings(save_enabled=True, llm_enabled=False, clipboard_enabled=True),
            image,
            lambda _img, _folder: home / "ScreenQuery" / "a.png",
            lambda *_args: "no",
            lambda: None,
            home,
            copy_png=boom,
        )
        self.assertEqual(failed.clipboard_error, "pasteboard busy")
        self.assertEqual(failed.save_display, "~/ScreenQuery/a.png")

    def test_openai_error_is_kept_and_stale_popup_hide_is_ignored(self):
        def explain(*_args):
            raise RuntimeError("Your API key has been invalidated. (HTTP 401)")

        status = perform_capture(
            Settings(save_enabled=True, llm_enabled=True, clipboard_enabled=False),
            object(),
            lambda _img, _folder: Path("/Users/ada/ScreenQuery/a.png"),
            explain,
            lambda: "sk-test",
            Path("/Users/ada"),
        )
        self.assertIn("invalidated", status.llm_error)
        self.assertIsNone(status.answer)
        self.assertIsNotNone(status.save_display)

        from screenquery.ui_server import UiServer

        class _App:
            pass

        ui = UiServer(_App())
        first = ui.publish(Status(save_display="~/a.png"))
        second = ui.publish(Status(llm_error="Your API key has been invalidated. (HTTP 401)"))
        self.assertFalse(ui.hide_status(first))
        self.assertTrue(ui.snapshot()["visible"])
        self.assertIn("invalidated", ui.snapshot()["status"]["llm_error"])
        self.assertTrue(ui.hide_status(second))
        self.assertFalse(ui.snapshot()["visible"])

    def test_save_failure_still_reports_the_answer(self):
        def save(_img, _folder):
            raise RuntimeError("disk full")

        status = perform_capture(
            Settings(True, True),
            object(),
            save,
            lambda *_args: "still here",
            lambda: "sk-test",
            Path("/Users/ada"),
        )
        self.assertEqual(status.save_error, "disk full")
        self.assertEqual(status.answer, "still here")

    def test_png_filename_lands_in_the_date_folder(self):
        home = Path(self._tmp("home"))
        when = datetime(2026, 10, 1, 22, 35, 7, 123000, tzinfo=timezone.utc)
        path = save_png(FakeImage(), None, when=when, home=home)
        self.assertEqual(path.parent, home / "ScreenQuery" / "2026-10-01")
        self.assertEqual(path.name, "ScreenQuery-223507-123.png")
        self.assertTrue(path.is_file())
        again = save_png(FakeImage(), None, when=when, home=home)
        self.assertTrue(again.name.endswith("-2.png"))

    def test_scale_size(self):
        self.assertEqual(scale_size(4000, 2000, 2048), (2048, 1024))
        self.assertEqual(scale_size(800, 600, 2048), (800, 600))

    def test_dismiss_timing(self):
        self.assertIsNone(dismiss_seconds(Status(llm_working=True)))
        self.assertEqual(dismiss_seconds(Status(answer="hi")), 30)
        self.assertEqual(dismiss_seconds(Status(banner="nope", banner_is_error=True)), 12)
        self.assertEqual(dismiss_seconds(Status(save_display="~/a.png")), 8)

    def test_login_item_text_has_no_key(self):
        plist = macos_plist(["/Applications/ScreenQuery.app/Contents/MacOS/ScreenQuery"])
        self.assertIn("com.screenquery.ScreenQuery", plist)
        self.assertIn("/Applications/ScreenQuery.app/Contents/MacOS/ScreenQuery", plist)
        self.assertNotIn("sk-", plist)
        escaped = macos_plist("/tmp/Screen & Query")
        self.assertIn("Screen &amp; Query", escaped)
        self.assertEqual(windows_run_value(r"C:\Apps\ScreenQuery.exe"), r'"C:\Apps\ScreenQuery.exe"')
        self.assertEqual(
            windows_run_value([r"C:\Program Files\ScreenQuery.exe", "--minimized"]),
            r'"C:\Program Files\ScreenQuery.exe" "--minimized"',
        )

    def test_permission_copy_mentions_the_platform(self):
        self.assertIn("Screen & System Audio Recording", permission_help("darwin"))
        self.assertIn("Input Monitoring", permission_help("darwin"))
        self.assertIn("Windows", permission_help("win32"))

    def _tmp(self, name):
        import tempfile

        directory = tempfile.mkdtemp(prefix="screenquery-")
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        return str(Path(directory) / name)


if __name__ == "__main__":
    unittest.main()
