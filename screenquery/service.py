"""Capture flow: save a PNG, ask OpenAI, or both."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from screenquery.paths import abbreviate
from screenquery.settings_store import Settings
from screenquery.status import Status

MISSING_KEY = (
    "No OpenAI API key yet. Open Settings and paste a key. "
    "ScreenQuery stores it in the system keychain, not in preferences."
)
NOTHING_ENABLED = (
    "Turn on Save screenshot, Copy to clipboard, Send to OpenAI, or a combination in Settings."
)
SENDING_OFF = (
    "Send to OpenAI is off, so there is no model reply. "
    "Your key is saved. Turn on Send to OpenAI in Settings."
)


def perform_capture(
    settings: Settings,
    image,
    save_png: Callable,
    explain: Callable,
    load_key: Callable[[], str | None],
    home: Path,
    copy_png: Callable | None = None,
) -> Status:
    clipboard_on = bool(getattr(settings, "clipboard_enabled", True))
    if not settings.save_enabled and not settings.llm_enabled and not clipboard_on:
        return Status(banner=NOTHING_ENABLED, banner_is_error=True)

    status = Status()
    if clipboard_on and copy_png is not None:
        try:
            copy_png(image)
            status.clipboard_copied = True
        except Exception as exc:  # noqa: BLE001 - show the clipboard message
            status.clipboard_error = str(exc)
    if settings.save_enabled:
        try:
            path = Path(save_png(image, settings.custom_folder))
            status.save_full = str(path)
            status.save_display = abbreviate(path, home)
        except Exception as exc:  # noqa: BLE001 - show the saver's message
            status.save_error = str(exc)

    if settings.llm_enabled:
        key = (load_key() or "").strip()
        if not key:
            status.llm_error = MISSING_KEY
        else:
            try:
                status.answer = explain(image, key, settings.base_url, settings.model)
            except Exception as exc:  # noqa: BLE001 - show the client message
                status.llm_error = str(exc)
    return status
