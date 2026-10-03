"""Wires the hotkey, screenshot, OpenAI call, tray, and React windows."""

from __future__ import annotations

import logging
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

from screenquery.capture import (
    SCREEN_RECORDING_DENIED,
    grab_active_window,
    grab_region,
    screen_recording_allowed,
)
from screenquery.region import cancel_region_select, select_region
from screenquery.clipboard import copy_image
from screenquery.desktop import Desktop
from screenquery.hotkey_listener import HotkeyListener, listen_allowed
from screenquery.mac_access import LISTEN_DENIED, request_listen, request_screen_recording
from screenquery.images import prepared_jpeg, save_png
from screenquery.keystore import Keystore
from screenquery.openai_api import explain as openai_explain
from screenquery.permissions_text import MAC_SETTINGS_URLS
from screenquery.service import NOTHING_ENABLED, SENDING_OFF, perform_capture
from screenquery.settings_store import SettingsStore
from screenquery.status import Status
from screenquery.tray import Tray
from screenquery.ui_server import UiServer

log = logging.getLogger("screenquery")


class ScreenQueryApp:
    def __init__(self) -> None:
        self.settings_store = SettingsStore()
        self.keystore = Keystore()
        self.ui = UiServer(self)
        self.desktop: Desktop | None = None
        self.tray = Tray(self)
        self.hotkey = HotkeyListener(self._on_hotkey)
        self.generation = 0
        self._quitting = False

    @property
    def tray_running(self) -> bool:
        return self.tray.running

    def start(self) -> None:
        self.ui.start()
        # Ask once on this thread. It is the process main thread, before the
        # UI run loop. The system call is synchronous when it shows a dialog.
        try:
            if sys.platform == "darwin":
                log.info(
                    "Permissions at launch: screen=%s listen=%s",
                    screen_recording_allowed(),
                    listen_allowed(),
                )
                # One request so this binary gets its own row. A switch that is
                # already on can still belong to an older signature.
                if not screen_recording_allowed():
                    request_screen_recording(user_retry=False, on_denied=lambda: _open_privacy("screen"))
                self._arm_hotkey(user_retry=False)
            else:
                self.hotkey.start()
        except Exception:
            log.exception("Global hotkey did not start")
        first_run = not self.settings_store.path.exists()
        if first_run:
            try:
                self.settings_store.save(self.settings_store.load())
            except Exception:
                log.exception("Could not write default settings")
        self.tray.start()
        self.desktop = Desktop(self, self.ui.base_url)
        self.ui.on_hide = self.desktop.hide_overlay
        # Settings opens from the menu. Auto-open only when no settings file
        # existed at startup. A later launch must not pop the window again,
        # including when the menu icon is installed a moment later.
        log.info("ScreenQuery UI at %s", self.ui.base_url)
        self.desktop.start(open_settings=first_run)

    def show_settings(self) -> None:
        if self.desktop is not None:
            self.desktop.show_settings()

    def on_ui_ready(self) -> None:
        """Main thread, after the menu bar can be installed."""
        self.tray.install()

    def enable_hotkey(self) -> None:
        _on_main(lambda: self._arm_hotkey(user_retry=True))

    def allow_screen_recording(self) -> None:
        _on_main(self._ask_screen_from_menu)

    def _on_hotkey(self, kind: str) -> None:
        if kind == "region":
            self.capture_region()
            return
        self.capture()

    def capture(self) -> None:
        cancel_region_select()
        self.generation += 1
        generation = self.generation
        if self.desktop is not None:
            self.desktop.hide_overlay()
        if sys.platform == "darwin" and not screen_recording_allowed():
            # Leave the menu tracking loop before the system dialog.
            _on_main(lambda: self._capture_after_access(generation))
            return
        self._start_worker(generation, grab_active_window, "window")

    def capture_region(self) -> None:
        """Shift+S+O. The user draws a rectangle; that patch uses the same options."""
        cancel_region_select()
        self.generation += 1
        generation = self.generation
        if self.desktop is not None:
            self.desktop.hide_overlay()
        if sys.platform != "darwin":
            self._present(
                generation,
                Status(banner="Drag a rectangle to crop on macOS.", banner_is_error=True),
            )
            return
        if not screen_recording_allowed():
            _on_main(lambda: self._region_after_access(generation))
            return
        _on_main(lambda: self._open_region(generation))

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        cancel_region_select()
        try:
            self.hotkey.stop()
        except Exception:
            log.exception("Stopping the hotkey failed")
        self.tray.stop()
        self.ui.stop()
        if self.desktop is not None:
            self.desktop.destroy()

    def _arm_hotkey(self, user_retry: bool) -> None:
        if sys.platform == "darwin" and not listen_allowed():
            granted = request_listen(user_retry=user_retry, on_denied=lambda: _open_privacy("input"))
            if not granted:
                log.info("Shift+S+P left off; Input Monitoring is not granted")
                if user_retry:
                    self.generation += 1
                    self._present(self.generation, Status(banner=LISTEN_DENIED, banner_is_error=True))
                return
        try:
            self.hotkey.start()
        except Exception:
            log.exception("Global hotkey did not start")
            return
        if sys.platform == "darwin" and not self.hotkey.running:
            log.info("Input Monitoring did not start the Shift+S+P tap")
            self.generation += 1
            self._present(self.generation, Status(banner=LISTEN_DENIED, banner_is_error=True))

    def _ask_screen_from_menu(self) -> None:
        if request_screen_recording(user_retry=True, on_denied=lambda: _open_privacy("screen")):
            return
        self.generation += 1
        log.info("Screen Recording is still not granted")
        self._present(self.generation, Status(banner=SCREEN_RECORDING_DENIED, banner_is_error=True))

    def _capture_after_access(self, generation: int) -> None:
        if generation != self.generation:
            return
        if not request_screen_recording(user_retry=False, on_denied=lambda: _open_privacy("screen")):
            log.info("Capture skipped; Screen Recording is not granted")
            self._present(generation, Status(banner=SCREEN_RECORDING_DENIED, banner_is_error=True))
            return
        self._start_worker(generation, grab_active_window, "window")

    def _region_after_access(self, generation: int) -> None:
        if generation != self.generation:
            return
        if not request_screen_recording(user_retry=False, on_denied=lambda: _open_privacy("screen")):
            log.info("Crop skipped; Screen Recording is not granted")
            self._present(generation, Status(banner=SCREEN_RECORDING_DENIED, banner_is_error=True))
            return
        self._open_region(generation)

    def _open_region(self, generation: int) -> None:
        if generation != self.generation:
            return

        def chosen(bounds) -> None:
            if generation != self.generation:
                return
            if bounds is None:
                return
            if isinstance(bounds, str):
                self._present(generation, Status(banner=bounds, banner_is_error=True))
                return
            log.info("Crop selected x=%s y=%s w=%s h=%s", bounds.get("X"), bounds.get("Y"), bounds.get("Width"), bounds.get("Height"))
            self._start_worker(generation, lambda: grab_region(bounds), "region")

        try:
            select_region(chosen)
        except Exception:
            log.exception("Could not open the crop layer")
            self._present(
                generation,
                Status(banner="Could not start the crop tool. Try Shift+S+O again.", banner_is_error=True),
            )

    def _start_worker(self, generation: int, grab, kind: str) -> None:
        threading.Thread(target=self._run, args=(generation, grab, kind), daemon=True).start()

    def _run(self, generation: int, grab, kind: str) -> None:
        # Let the crop layer leave the screen, and let the hotkey keys come up.
        time.sleep(0.35 if kind == "region" else 0.25)
        if generation != self.generation:
            return
        settings = self.settings_store.load()
        home = Path.home()
        if not settings.save_enabled and not settings.llm_enabled and not settings.clipboard_enabled:
            self._present(generation, Status(banner=NOTHING_ENABLED, banner_is_error=True))
            return
        try:
            image = grab()
        except Exception as exc:
            log.exception("Capture failed")
            self._present(generation, Status(banner=str(exc), banner_is_error=True))
            return
        if generation != self.generation:
            return

        def explain(image, api_key: str, base_url: str, model: str) -> str:
            return _explain(image, api_key, base_url, model, kind)

        saved = perform_capture(
            replace(settings, llm_enabled=False),
            image,
            save_png,
            explain,
            self.keystore.load,
            home,
            copy_png=copy_image,
        )
        status = saved
        if settings.llm_enabled:
            status.llm_working = True
            self._present(generation, status)
            if generation != self.generation:
                return
            answered = perform_capture(
                replace(settings, save_enabled=False, clipboard_enabled=False),
                image,
                save_png,
                explain,
                self.keystore.load,
                home,
            )
            status.llm_working = False
            status.answer = answered.answer
            status.llm_error = answered.llm_error
        elif self._key_is_stored():
            status.banner = SENDING_OFF
        self._present(generation, status)

    def _key_is_stored(self) -> bool:
        try:
            return bool((self.keystore.load() or "").strip())
        except Exception:
            log.exception("Could not read the OpenAI key from the keychain")
            return False

    def _present(self, generation: int, status: Status) -> None:
        if generation != self.generation:
            return
        self.ui.publish(status)
        if self.desktop is not None:
            self.desktop.present_overlay(status)


def _open_privacy(kind: str) -> None:
    import subprocess

    for url in MAC_SETTINGS_URLS.get(kind) or ():
        if subprocess.run(["open", url], check=False).returncode == 0:
            return


def _on_main(fn) -> None:
    try:
        from PyObjCTools import AppHelper

        AppHelper.callAfter(fn)
    except Exception:
        log.exception("Could not schedule on the main thread")
        fn()


def _explain(image, api_key: str, base_url: str, model: str, kind: str = "window") -> str:
    jpeg = prepared_jpeg(image)
    return openai_explain(jpeg, "image/jpeg", api_key, base_url, model, kind=kind)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.screenquery.ScreenQuery")
        except Exception:
            log.exception("Could not set the Windows AppUserModelID")
    ScreenQueryApp().start()
