"""Settings window: save folder, toggles, OpenAI key, and permissions."""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from screenquery.login_item import is_enabled as login_enabled
from screenquery.login_item import launch_at_login_supported, set_enabled as set_login
from screenquery.openai_api import DEFAULT_BASE_URL, endpoint
from screenquery.paths import abbreviate, resolve_directory
from screenquery.permissions_text import MAC_SETTINGS_URLS, permission_help
from screenquery.settings_store import Settings


class SettingsWindow:
    def __init__(self, root: tk.Misc, app) -> None:
        self.root = root
        self.app = app
        self.win: tk.Toplevel | None = None

    def show(self) -> None:
        if self.win is not None and self.win.winfo_exists():
            self.win.deiconify()
            _bring_to_front(self.win)
            return
        win = tk.Toplevel(self.root)
        self.win = win
        win.title("ScreenQuery Settings")
        win.geometry("640x760")
        win.minsize(560, 640)
        win.protocol("WM_DELETE_WINDOW", self._close)
        # A canvas-hosted form stays blank on macOS Tk (the scrollbar shows, the
        # controls do not). Pack the form directly so it paints.
        style = ttk.Style(win)
        if sys.platform != "darwin" and "clam" in style.theme_names():
            style.theme_use("clam")
        frame = ttk.Frame(win, padding=16)
        frame.pack(fill="both", expand=True)

        settings = self.app.settings_store.load()
        self.save_var = tk.BooleanVar(value=settings.save_enabled)
        self.llm_var = tk.BooleanVar(value=settings.llm_enabled)
        self.base_var = tk.StringVar(value=settings.base_url)
        self.model_var = tk.StringVar(value=settings.model)
        self.folder_var = tk.StringVar(value=settings.custom_folder or "")
        stored_key, key_status = _stored_key(self.app)
        self.key_var = tk.StringVar(value=stored_key)
        self.key_status = tk.StringVar(value=key_status)
        self.login_var = tk.BooleanVar(value=_safe_login_enabled())

        ttk.Label(frame, text="ScreenQuery", font=_title_font()).grid(row=0, column=0, sticky="w")
        ttk.Label(
            frame,
            text="Hold Shift, then press S and P together.",
            wraplength=560,
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))

        actions = ttk.LabelFrame(frame, text="When the hotkey fires", padding=10)
        actions.grid(row=2, column=0, sticky="ew", pady=6)
        ttk.Checkbutton(
            actions,
            text="Save screenshot",
            variable=self.save_var,
            command=self._save_toggles,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            actions,
            text="Send to OpenAI",
            variable=self.llm_var,
            command=self._save_toggles,
        ).grid(row=1, column=0, sticky="w")
        ttk.Label(
            actions,
            text="Turn on either action, or both. The floating window reports the save path and the answer.",
            wraplength=540,
        ).grid(row=2, column=0, sticky="w", pady=(6, 0))

        folder = ttk.LabelFrame(frame, text="Save location", padding=10)
        folder.grid(row=3, column=0, sticky="ew", pady=6)
        self.dest_label = ttk.Label(folder, text=self._destination_text(), wraplength=540)
        self.dest_label.grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Button(folder, text="Choose Folder…", command=self._choose_folder).grid(row=1, column=0, sticky="w", pady=8)
        ttk.Button(folder, text="Use Default", command=self._use_default).grid(row=1, column=1, sticky="w", padx=8)
        ttk.Label(
            folder,
            text="Every capture goes in a date folder: <base>/<YYYY-MM-DD>/ScreenQuery-<time>.png. The default base is ~/ScreenQuery.",
            wraplength=540,
        ).grid(row=2, column=0, columnspan=3, sticky="w")

        openai = ttk.LabelFrame(frame, text="OpenAI", padding=10)
        openai.grid(row=4, column=0, sticky="ew", pady=6)
        ttk.Label(
            openai,
            text="Paste your own key. It is saved only in the system keychain (macOS Keychain or Windows Credential Manager).",
            wraplength=540,
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Entry(openai, textvariable=self.key_var, show="*", width=48).grid(row=1, column=0, columnspan=3, sticky="ew", pady=6)
        ttk.Button(openai, text="Save Key", command=self._save_key).grid(row=2, column=0, sticky="w")
        ttk.Button(openai, text="Remove Key", command=self._remove_key).grid(row=2, column=1, sticky="w", padx=8)
        ttk.Label(openai, textvariable=self.key_status, wraplength=540).grid(row=3, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Label(openai, text="Base URL").grid(row=4, column=0, sticky="w")
        ttk.Entry(openai, textvariable=self.base_var, width=48).grid(row=5, column=0, columnspan=3, sticky="ew")
        ttk.Label(openai, text="Model").grid(row=6, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(openai, textvariable=self.model_var, width=32).grid(row=7, column=0, sticky="w")
        shortcuts = ttk.Frame(openai)
        shortcuts.grid(row=8, column=0, columnspan=3, sticky="w", pady=6)
        for name in ("gpt-4o", "gpt-4o-mini", "gpt-4.1"):
            ttk.Button(shortcuts, text=name, command=lambda n=name: self.model_var.set(n)).pack(side="left", padx=(0, 6))
        ttk.Button(openai, text="Save OpenAI Settings", command=self._save_openai).grid(row=9, column=0, sticky="w")
        ttk.Label(
            openai,
            text=f"Default {DEFAULT_BASE_URL}. ScreenQuery calls the Chat Completions vision API. No key is built in.",
            wraplength=540,
        ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(6, 0))

        perms = ttk.LabelFrame(frame, text="Permissions", padding=10)
        perms.grid(row=5, column=0, sticky="ew", pady=6)
        ttk.Label(perms, text=permission_help(sys.platform), wraplength=540).grid(row=0, column=0, sticky="w")
        if sys.platform == "darwin":
            buttons = ttk.Frame(perms)
            buttons.grid(row=1, column=0, sticky="w", pady=8)
            ttk.Button(buttons, text="Screen Recording", command=lambda: _open_mac("screen")).pack(side="left", padx=(0, 6))
            ttk.Button(buttons, text="Input Monitoring", command=lambda: _open_mac("input")).pack(side="left", padx=(0, 6))
            ttk.Button(buttons, text="Accessibility", command=lambda: _open_mac("accessibility")).pack(side="left")
            self._request_row(perms)

        general = ttk.LabelFrame(frame, text="General", padding=10)
        general.grid(row=6, column=0, sticky="ew", pady=6)
        if launch_at_login_supported():
            ttk.Checkbutton(
                general,
                text="Launch at login",
                variable=self.login_var,
                command=self._toggle_login,
            ).grid(row=0, column=0, sticky="w")
        ttk.Label(general, text="ScreenQuery 1.0 · menu-bar utility").grid(row=1, column=0, sticky="w", pady=(6, 0))

        controls = ttk.Frame(frame)
        controls.grid(row=7, column=0, sticky="w", pady=12)
        ttk.Button(controls, text="Capture Now", command=self.app.capture).pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="Quit", command=self.app.quit).pack(side="left")
        frame.columnconfigure(0, weight=1)
        _bring_to_front(win)

    def _close(self) -> None:
        if self.app.tray_running:
            if self.win is not None:
                self.win.withdraw()
            _return_to_menu_bar()
        else:
            self.app.quit()

    def _save_toggles(self) -> None:
        settings = self._current()
        self.app.settings_store.save(settings)

    def _current(self) -> Settings:
        folder = self.folder_var.get().strip() or None
        return Settings(
            save_enabled=self.save_var.get(),
            llm_enabled=self.llm_var.get(),
            custom_folder=folder,
            base_url=self.base_var.get().strip() or DEFAULT_BASE_URL,
            model=self.model_var.get().strip() or "gpt-4o",
        )

    def _save_openai(self) -> None:
        try:
            endpoint(self.base_var.get())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("ScreenQuery", str(exc), parent=self.win)
            return
        self.app.settings_store.save(self._current())
        messagebox.showinfo("ScreenQuery", "OpenAI settings saved. The key itself is only stored if you click Save Key.", parent=self.win)

    def _save_key(self) -> None:
        secret = self.key_var.get().strip()
        if not secret:
            self.key_status.set("Paste a key first.")
            return
        try:
            self.app.keystore.save(secret)
        except Exception as exc:  # noqa: BLE001
            self.key_status.set(str(exc))
            return
        self.key_status.set("Saved to the system keychain.")

    def _remove_key(self) -> None:
        try:
            self.app.keystore.delete()
        except Exception as exc:  # noqa: BLE001
            self.key_status.set(str(exc))
            return
        self.key_var.set("")
        self.key_status.set("Key removed from the system keychain.")

    def _choose_folder(self) -> None:
        chosen = filedialog.askdirectory(parent=self.win, title="Choose screenshot folder")
        if not chosen:
            return
        self.folder_var.set(chosen)
        self.app.settings_store.save(self._current())
        self.dest_label.configure(text=self._destination_text())

    def _use_default(self) -> None:
        self.folder_var.set("")
        self.app.settings_store.save(self._current())
        self.dest_label.configure(text=self._destination_text())

    def _destination_text(self) -> str:
        folder = self.folder_var.get().strip() or None
        path = resolve_directory(folder, datetime.now().astimezone(), Path.home())
        shown = abbreviate(path, Path.home())
        return f"Saves to {shown}"

    def _toggle_login(self) -> None:
        try:
            set_login(self.login_var.get())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("ScreenQuery", str(exc), parent=self.win)
            self.login_var.set(_safe_login_enabled())

    def _request_row(self, parent) -> None:
        try:
            import Quartz
        except Exception:
            return
        row = ttk.Frame(parent)
        row.grid(row=2, column=0, sticky="w")
        ttk.Button(row, text="Request Screen Recording", command=Quartz.CGRequestScreenCaptureAccess).pack(side="left", padx=(0, 6))
        if hasattr(Quartz, "CGRequestListenEventAccess"):
            ttk.Button(row, text="Request Input Monitoring", command=Quartz.CGRequestListenEventAccess).pack(side="left")


def _bring_to_front(win: tk.Toplevel) -> None:
    """Menu-bar apps stay in the background unless Settings asks to be shown."""
    win.lift()
    win.focus_force()
    if sys.platform == "darwin":
        # Delay past the current event so activation does not nest inside Tk.
        win.after(1, _activate_settings_app)
        return
    try:
        win.attributes("-topmost", True)
        win.after(400, lambda: win.attributes("-topmost", False))
    except tk.TclError:
        return


def _activate_settings_app() -> None:
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyRegular

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)
    except Exception:
        return


def _return_to_menu_bar() -> None:
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        return


def _title_font():
    return ("TkDefaultFont", 18, "bold")


def _safe_login_enabled() -> bool:
    try:
        return login_enabled()
    except Exception:
        return False


def _stored_key(app) -> tuple[str, str]:
    try:
        stored = app.keystore.load() or ""
    except Exception as exc:  # keyring may be missing until dependencies are installed
        return "", str(exc)
    if stored:
        return stored, "A key is stored in the system keychain."
    return "", "No API key stored."


def _open_mac(kind: str) -> None:
    for url in MAC_SETTINGS_URLS[kind]:
        result = subprocess.run(["open", url], check=False)
        if result.returncode == 0:
            return
