"""Wires the hotkey, screenshot, OpenAI call, tray, and status window."""

from __future__ import annotations

import logging
import queue
import sys
import threading
import time
import tkinter as tk
from dataclasses import replace

from screenquery.capture import grab_fullscreen
from screenquery.hotkey_listener import HotkeyListener
from screenquery.images import prepared_jpeg, save_png
from screenquery.keystore import Keystore
from screenquery.openai_api import explain as openai_explain
from screenquery.overlay import StatusOverlay
from screenquery.service import NOTHING_ENABLED, perform_capture
from screenquery.settings_store import SettingsStore
from screenquery.settings_ui import SettingsWindow
from screenquery.status import Status
from screenquery.tray import Tray

log = logging.getLogger("screenquery")


class UiPump:
    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self._queue: queue.Queue = queue.Queue()

    def call(self, fn) -> None:
        self._queue.put(fn)

    def poll(self) -> None:
        try:
            while True:
                fn = self._queue.get_nowait()
                try:
                    fn()
                except Exception:
                    log.exception("UI task failed")
        except queue.Empty:
            pass
        self.root.after(50, self.poll)


class ScreenQueryApp:
    def __init__(self) -> None:
        self.settings_store = SettingsStore()
        self.keystore = Keystore()
        self.root = tk.Tk()
        self.root.withdraw()
        self.pump = UiPump(self.root)
        self.overlay = StatusOverlay(self.root)
        self.settings_window = SettingsWindow(self.root, self)
        self.tray = Tray(self)
        self.hotkey = HotkeyListener(self.capture)
        self.generation = 0
        self._quitting = False

    @property
    def tray_running(self) -> bool:
        return self.tray.running

    def start(self) -> None:
        try:
            self.hotkey.start()
        except Exception:
            log.exception("Global hotkey did not start")
        first_run = not self.settings_store.path.exists()
        if first_run:
            try:
                self.settings_store.save(self.settings_store.load())
            except Exception:
                log.exception("Could not write default settings")
        if not self.tray.start() or first_run:
            self.show_settings()
        self.root.after(50, self.pump.poll)
        self.root.mainloop()

    def show_settings(self) -> None:
        if threading.current_thread() is threading.main_thread():
            self.settings_window.show()
        else:
            self.pump.call(self.settings_window.show)

    def capture(self) -> None:
        self.generation += 1
        generation = self.generation

        def start() -> None:
            self.overlay.hide()
            try:
                self.root.update_idletasks()
            except tk.TclError:
                pass
            threading.Thread(target=self._run, args=(generation,), daemon=True).start()

        self.pump.call(start)

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True

        def _quit() -> None:
            try:
                self.hotkey.stop()
            except Exception:
                log.exception("Stopping the hotkey failed")
            self.tray.stop()
            self.root.quit()
            try:
                self.root.destroy()
            except tk.TclError:
                pass

        if threading.current_thread() is threading.main_thread():
            _quit()
        else:
            self.pump.call(_quit)

    def _run(self, generation: int) -> None:
        time.sleep(0.08)
        if generation != self.generation:
            return
        settings = self.settings_store.load()
        home = _home()
        if not settings.save_enabled and not settings.llm_enabled:
            self._present(generation, Status(banner=NOTHING_ENABLED, banner_is_error=True))
            return
        try:
            image = grab_fullscreen()
        except Exception as exc:
            log.exception("Capture failed")
            self._present(generation, Status(banner=str(exc), banner_is_error=True))
            return
        if generation != self.generation:
            return

        status = Status()
        if settings.save_enabled:
            saved = perform_capture(
                replace(settings, llm_enabled=False),
                image,
                save_png,
                _explain,
                self.keystore.load,
                home,
            )
            status.save_display = saved.save_display
            status.save_full = saved.save_full
            status.save_error = saved.save_error
        if settings.llm_enabled:
            status.llm_working = True
            self._present(generation, status)
            if generation != self.generation:
                return
            answered = perform_capture(
                replace(settings, save_enabled=False),
                image,
                save_png,
                _explain,
                self.keystore.load,
                home,
            )
            status.llm_working = False
            status.answer = answered.answer
            status.llm_error = answered.llm_error
        self._present(generation, status)

    def _present(self, generation: int, status: Status) -> None:
        if generation != self.generation:
            return
        self.pump.call(lambda: self.overlay.present(status))


def _explain(image, api_key: str, base_url: str, model: str) -> str:
    jpeg = prepared_jpeg(image)
    return openai_explain(jpeg, "image/jpeg", api_key, base_url, model)


def _home():
    from pathlib import Path

    return Path.home()


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.screenquery.ScreenQuery")
        except Exception:
            log.exception("Could not set the Windows AppUserModelID")
    ScreenQueryApp().start()
