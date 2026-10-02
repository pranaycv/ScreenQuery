"""Menu bar on macOS, system tray on Windows and Linux."""

from __future__ import annotations

import sys
import threading


class Tray:
    def __init__(self, app) -> None:
        self.app = app
        self.running = False
        self._icon = None
        self._mac_refs = []

    def start(self) -> bool:
        if sys.platform == "darwin" and self._start_mac():
            self.running = True
            return True
        return self._start_pystray()

    def stop(self) -> None:
        icon = self._icon
        self._icon = None
        self.running = False
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
            MenuItem("Hotkey: Shift + S + P", lambda _icon, _item: None, enabled=False),
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

    def _start_mac(self) -> bool:
        try:
            from AppKit import (
                NSApplication,
                NSApplicationActivationPolicyAccessory,
                NSMenu,
                NSMenuItem,
                NSStatusBar,
                NSVariableStatusItemLength,
            )
            from Foundation import NSObject
            import objc
        except Exception:
            return False

        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        status = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        button = status.button()
        if button is not None:
            button.setTitle_("SQ")

        class _MenuTarget(NSObject):
            def capture_(self, _sender):
                self.app.capture()

            def settings_(self, _sender):
                self.app.show_settings()

            def quit_(self, _sender):
                self.app.quit()

        target = _MenuTarget.alloc().init()
        target.app = self.app
        menu = NSMenu.alloc().init()
        for title, action in (
            ("Capture Now", "capture:"),
            ("Settings…", "settings:"),
            ("Quit ScreenQuery", "quit:"),
        ):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
            item.setTarget_(target)
            menu.addItem_(item)
        hotkey = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Hotkey: Shift + S + P", "settings:", "")
        hotkey.setTarget_(None)
        hotkey.setEnabled_(False)
        menu.insertItem_atIndex_(hotkey, 1)
        status.setMenu_(menu)
        self._mac_refs.extend([status, target, menu])
        # Silence unused import if a future edit drops objc.
        _ = objc
        return True
