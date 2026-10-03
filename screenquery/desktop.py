"""pywebview shell for the React settings window and status overlay.

EyesRhythm loads its React app the same way: a localhost page inside a
native window, with the menu-bar process staying up after the window hides.
"""

from __future__ import annotations

import logging
import sys

from screenquery.ribbon import RibbonPanel
from screenquery.status import dismiss_seconds

log = logging.getLogger("screenquery")


class Desktop:
    def __init__(self, app, base_url: str) -> None:
        self.app = app
        self.base_url = base_url.rstrip("/")
        self.settings_window = None
        self.overlay_window = None
        self.ribbon = RibbonPanel()

    def start(self, *, open_settings: bool = False) -> None:
        import webview

        self.settings_window = webview.create_window(
            "ScreenQuery Settings",
            f"{self.base_url}/",
            width=720,
            height=840,
            min_size=(560, 640),
            background_color="#e8eef6",
            hidden=True,
        )
        try:
            self.settings_window.events.closing += self._hide_settings
        except Exception:
            log.exception("Could not hook the settings window")

        def _ready() -> None:
            # webview starts this on a worker thread, and its Cocoa backend has
            # already forced the regular activation policy. Status items only
            # survive if they are created on the main thread after that, and
            # the policy is not changed again.
            def go() -> None:
                _set_accessory(True)
                self.app.on_ui_ready()
                if open_settings:
                    self.show_settings()

            if sys.platform == "darwin":
                from PyObjCTools import AppHelper

                AppHelper.callAfter(go)
            else:
                self.app.on_ui_ready()
                if open_settings:
                    self.show_settings()

        start_kwargs = {"debug": False}
        if sys.platform == "win32":
            start_kwargs["gui"] = "edgechromium"
        webview.start(_ready, **start_kwargs)

    def show_settings(self) -> None:
        window = self.settings_window
        if window is None:
            return
        # Stay an accessory app. Switching to the regular policy removes the
        # menu-bar item, and switching back does not put it back.
        try:
            window.show()
        except Exception:
            log.exception("Could not show Settings")
            return
        _activate()

    def present_overlay(self, status) -> None:
        try:
            self.ribbon.show(status, dismiss_seconds(status))
        except Exception:
            log.exception("Could not show the status ribbon")

    def hide_overlay(self) -> None:
        try:
            self.ribbon.hide()
        except Exception:
            log.exception("Could not hide the status ribbon")

    def _hide_settings(self) -> bool:
        # False cancels the close. The app keeps running; Quit is the menu item.
        if getattr(self.app, "_quitting", False):
            return True
        window = self.settings_window
        if window is not None:
            try:
                window.hide()
            except Exception:
                log.exception("Could not hide Settings")
        return False

    def destroy(self) -> None:
        for window in (self.settings_window,):
            if window is None:
                continue
            try:
                window.destroy()
            except Exception:
                pass


def _set_accessory(accessory: bool) -> None:
    if sys.platform != "darwin":
        return
    try:
        from AppKit import (
            NSApplication,
            NSApplicationActivationPolicyAccessory,
            NSApplicationActivationPolicyRegular,
        )

        policy = NSApplicationActivationPolicyAccessory if accessory else NSApplicationActivationPolicyRegular
        NSApplication.sharedApplication().setActivationPolicy_(policy)
    except Exception:
        log.exception("Could not set the activation policy")


def _activate() -> None:
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        log.exception("Could not activate ScreenQuery")
