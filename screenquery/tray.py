"""Menu bar on macOS, system tray on Windows and Linux."""

from __future__ import annotations

import sys
import threading


class Tray:
    def __init__(self, app) -> None:
        self.app = app
        self.running = False
        self._icon = None
        self._status = None
        self._mac_refs = []

    def start(self) -> bool:
        if sys.platform == "darwin" and self._mac_available():
            # Installed from the AppKit startup path, after the activation
            # policy has settled. Creating it earlier gets thrown away.
            return True
        return self._start_pystray()

    def install(self) -> bool:
        """Put the menu-bar mark up. Safe to call again; does not replace a live item."""
        if sys.platform != "darwin":
            return self.running
        if self._status is not None:
            self.running = True
            return True
        return self._install_mac()

    def stop(self) -> None:
        icon = self._icon
        self._icon = None
        status = self._status
        self._status = None
        self._mac_refs = []
        self.running = False
        if status is not None:
            try:
                from AppKit import NSStatusBar

                NSStatusBar.systemStatusBar().removeStatusItem_(status)
            except Exception:
                pass
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    def _start_pystray(self) -> bool:
        try:
            import pystray
            from pystray import Menu, MenuItem
        except Exception:
            return False
        try:
            from screenquery.icon_art import draw_icon

            image = draw_icon(64)
        except Exception:
            return False
        menu = Menu(
            MenuItem("Capture Now", lambda _icon, _item: self.app.capture()),
            MenuItem("Crop Area", lambda _icon, _item: self.app.capture_region()),
            MenuItem("Settings…", lambda _icon, _item: self.app.show_settings()),
            MenuItem("Quit", lambda _icon, _item: self.app.quit()),
        )
        icon = pystray.Icon("ScreenQuery", image, "ScreenQuery", menu)
        self._icon = icon
        if hasattr(icon, "run_detached"):
            icon.run_detached()
        else:
            threading.Thread(target=icon.run, name="screenquery-tray", daemon=True).start()
        self.running = True
        return True

    def _mac_available(self) -> bool:
        try:
            import AppKit  # noqa: F401
            import Foundation  # noqa: F401
            import objc  # noqa: F401
        except Exception:
            return False
        return True

    def _install_mac(self) -> bool:
        try:
            from AppKit import (
                NSImage,
                NSMenu,
                NSMenuItem,
                NSSquareStatusItemLength,
                NSStatusBar,
            )
            from Foundation import NSData, NSObject
            import objc
        except Exception:
            return False

        status = NSStatusBar.systemStatusBar().statusItemWithLength_(NSSquareStatusItemLength)
        button = status.button()
        image = self._menu_image(NSImage, NSData)
        if button is not None:
            button.setToolTip_("ScreenQuery")
            button.setAccessibilityLabel_("ScreenQuery")
            if image is not None:
                button.setImage_(image)
                button.setTitle_("")
            else:
                button.setTitle_("SQ")

        class _MenuTarget(NSObject):
            # Always go through app.defer/show/capture so Tk is not entered
            # reentrantly from this AppKit menu action (avoids SIGABRT in
            # PyEval_RestoreThread when opening Settings).
            def capture_(self, _sender):
                self.app.capture()

            def crop_(self, _sender):
                self.app.capture_region()

            def settings_(self, _sender):
                self.app.show_settings()

            def quit_(self, _sender):
                self.app.quit()

            def hotkey_(self, _sender):
                self.app.enable_hotkey()

            def screen_(self, _sender):
                self.app.allow_screen_recording()

        target = _MenuTarget.alloc().init()
        target.app = self.app
        menu = NSMenu.alloc().init()
        for title, action in (
            ("Capture Now", "capture:"),
            ("Crop Area", "crop:"),
            ("Settings…", "settings:"),
            ("Quit ScreenQuery", "quit:"),
        ):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
            item.setTarget_(target)
            menu.addItem_(item)
        hotkey_on = bool(getattr(self.app.hotkey, "running", False))
        if hotkey_on:
            hotkey = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Shift+S+P", None, "")
            hotkey.setEnabled_(False)
        else:
            hotkey = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Enable Shift+S+P",
                "hotkey:",
                "",
            )
            hotkey.setTarget_(target)
        menu.insertItem_atIndex_(hotkey, 2)
        try:
            from screenquery.capture import screen_recording_allowed

            screen_on = screen_recording_allowed()
        except Exception:
            screen_on = True
        if not screen_on:
            allow = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Allow Screen Recording",
                "screen:",
                "",
            )
            allow.setTarget_(target)
            menu.insertItem_atIndex_(allow, 3)
        status.setMenu_(menu)
        self._status = status
        self._mac_refs.extend([status, target, menu, image])
        self.running = True
        # Silence unused import if a future edit drops objc.
        _ = objc
        return True

    def _menu_image(self, NSImage, NSData):
        import io

        from screenquery.icon_art import draw_icon

        rendered = draw_icon(64)
        buffer = io.BytesIO()
        rendered.save(buffer, format="PNG")
        raw = buffer.getvalue()
        data = NSData.dataWithBytes_length_(raw, len(raw))
        image = NSImage.alloc().initWithData_(data)
        if image is None:
            return None
        image.setSize_((18, 18))
        image.setTemplate_(False)
        self._mac_refs.append(data)
        return image
