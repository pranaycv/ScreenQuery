"""Borderless always-on-top status window. Click the title or ✕ to dismiss."""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from tkinter import ttk

from screenquery.status import Status, dismiss_seconds


def ui_font(size: int = 12, weight: str = "normal") -> tuple:
    if sys.platform == "darwin":
        return ("Helvetica Neue", size, weight)
    if sys.platform == "win32":
        return ("Segoe UI", size, weight)
    return ("TkDefaultFont", size, weight)


class StatusOverlay:
    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self._after_id = None
        self._status: Status | None = None
        self._hovering = False
        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-alpha", 0.94)
        except tk.TclError:
            pass
        if sys.platform == "darwin":
            try:
                self.win.tk.call(
                    "::tk::unsupported::MacWindowStyle",
                    "style",
                    self.win._w,
                    "help",
                    "noActivates",
                )
            except tk.TclError:
                pass
        self.win.configure(bg="#1e1e1e")
        self.win.bind("<Enter>", self._entered)
        self.win.bind("<Leave>", self._left)
        self.body = tk.Frame(self.win, bg="#1e1e1e", padx=16, pady=14)
        self.body.pack(fill="both", expand=True)

    def hide(self) -> None:
        self._cancel_timer()
        self.win.withdraw()

    def present(self, status: Status) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        self._header()
        if status.banner:
            tk.Label(
                self.body,
                text=status.banner,
                bg="#1e1e1e",
                fg="#ff6b6b" if status.banner_is_error else "#f5f5f7",
                font=ui_font(12),
                wraplength=380,
                justify="left",
            ).pack(anchor="w", pady=(8, 0))
        if status.save_display:
            tk.Label(
                self.body,
                text="Saved",
                bg="#1e1e1e",
                fg="#30d158",
                font=ui_font(12, "bold"),
            ).pack(anchor="w", pady=(10, 0))
            tk.Label(
                self.body,
                text=status.save_display,
                bg="#1e1e1e",
                fg="#b0b0b5",
                font=ui_font(11),
                wraplength=380,
                justify="left",
            ).pack(anchor="w")
            if status.save_full:
                ttk.Button(
                    self.body,
                    text="Show in Folder",
                    command=lambda path=status.save_full: reveal(path),
                ).pack(anchor="w", pady=(6, 0))
        if status.save_error:
            tk.Label(
                self.body,
                text=status.save_error,
                bg="#1e1e1e",
                fg="#ff6b6b",
                font=ui_font(12),
                wraplength=380,
                justify="left",
            ).pack(anchor="w", pady=(8, 0))
        if status.llm_working:
            tk.Label(
                self.body,
                text="Asking OpenAI…",
                bg="#1e1e1e",
                fg="#f5f5f7",
                font=ui_font(12),
            ).pack(anchor="w", pady=(10, 0))
        if status.answer:
            tk.Label(
                self.body,
                text="OpenAI",
                bg="#1e1e1e",
                fg="#f5f5f7",
                font=ui_font(12, "bold"),
            ).pack(anchor="w", pady=(10, 0))
            text = tk.Text(
                self.body,
                height=10,
                width=48,
                bg="#2a2a2c",
                fg="#f5f5f7",
                insertbackground="#f5f5f7",
                relief="flat",
                wrap="word",
                font=ui_font(12),
            )
            text.insert("1.0", status.answer)
            text.configure(state="disabled")
            text.pack(anchor="w", pady=(4, 0))
            ttk.Button(
                self.body,
                text="Copy",
                command=lambda answer=status.answer: self._copy(answer),
            ).pack(anchor="w", pady=(6, 0))
        if status.llm_error:
            tk.Label(
                self.body,
                text=status.llm_error,
                bg="#1e1e1e",
                fg="#ff6b6b",
                font=ui_font(12),
                wraplength=380,
                justify="left",
            ).pack(anchor="w", pady=(8, 0))

        self.win.update_idletasks()
        width = max(self.win.winfo_reqwidth(), 420)
        height = self.win.winfo_reqheight()
        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        x = max(16, screen_w - width - 24)
        y = max(16, screen_h - height - 72)
        self.win.geometry(f"{width}x{height}+{x}+{y}")
        self.win.deiconify()
        self.win.lift()
        _avoid_activating(self.win)
        self._status = status
        self._schedule(status)

    def _entered(self, _event) -> None:
        self._hovering = True
        self._cancel_timer()

    def _left(self, _event) -> None:
        self.win.after(80, self._check_pointer)

    def _header(self) -> None:
        row = tk.Frame(self.body, bg="#1e1e1e")
        row.pack(fill="x")
        title = tk.Label(
            row,
            text="ScreenQuery",
            bg="#1e1e1e",
            fg="#f5f5f7",
            font=ui_font(14, "bold"),
            cursor="hand2",
        )
        title.pack(side="left")
        title.bind("<Button-1>", lambda _event: self.hide())
        close = tk.Label(
            row,
            text="✕",
            bg="#1e1e1e",
            fg="#f5f5f7",
            font=ui_font(12, "bold"),
            cursor="hand2",
        )
        close.pack(side="right")
        close.bind("<Button-1>", lambda _event: self.hide())

    def _copy(self, answer: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(answer)

    def _check_pointer(self) -> None:
        if not self.win.winfo_viewable():
            return
        px, py = self.win.winfo_pointerxy()
        x, y = self.win.winfo_rootx(), self.win.winfo_rooty()
        width, height = self.win.winfo_width(), self.win.winfo_height()
        inside = x <= px < x + width and y <= py < y + height
        self._hovering = inside
        if inside:
            self._cancel_timer()
        elif self._status is not None:
            self._schedule(self._status)

    def _schedule(self, status: Status) -> None:
        self._cancel_timer()
        if self._hovering:
            return
        delay = dismiss_seconds(status)
        if delay is None:
            return
        self._after_id = self.win.after(int(delay * 1000), self.hide)

    def _cancel_timer(self) -> None:
        if self._after_id is not None:
            try:
                self.win.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None


def _avoid_activating(win: tk.Toplevel) -> None:
    """Keep the status window from taking focus on Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        extended = -20
        no_activate = 0x08000000
        tool_window = 0x00000080
        style = user32.GetWindowLongW(hwnd, extended)
        user32.SetWindowLongW(hwnd, extended, style | no_activate | tool_window)
    except Exception:
        return


def reveal(path: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", path], check=False)
    elif sys.platform == "win32":
        subprocess.run(["explorer", f"/select,{path}"], check=False)
    else:
        subprocess.run(["xdg-open", str(PathParent(path))], check=False)


def PathParent(path: str) -> str:
    from pathlib import Path

    return str(Path(path).parent)
