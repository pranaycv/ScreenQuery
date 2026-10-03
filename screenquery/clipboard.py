"""Put a captured image on the system clipboard as image data."""

from __future__ import annotations

import io
import sys


def copy_image(image) -> None:
    """Copy a PIL image to the clipboard as PNG (macOS) or DIB (Windows)."""
    if sys.platform == "darwin":
        _copy_macos(image)
        return
    if sys.platform == "win32":
        _copy_windows(image)
        return
    _copy_other(image)


def _png_bytes(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _copy_macos(image) -> None:
    """Copy PNG via osascript so AppKit pasteboard calls do not deadlock the UI thread."""
    import os
    import subprocess
    import tempfile
    from pathlib import Path

    png = _png_bytes(image)
    handle, raw_path = tempfile.mkstemp(suffix=".png")
    try:
        os.write(handle, png)
    finally:
        os.close(handle)
    path = Path(raw_path)
    try:
        script = f'set the clipboard to (read POSIX file "{path}" as «class PNGf»)'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(detail or "Could not place the screenshot on the clipboard.")
    finally:
        path.unlink(missing_ok=True)


def _copy_windows(image) -> None:
    import ctypes

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "BMP")
    dib = buffer.getvalue()[14:]
    CF_DIB = 8
    GMEM_MOVEABLE = 0x0002
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not user32.OpenClipboard(None):
        raise RuntimeError("Could not open the clipboard.")
    try:
        if not user32.EmptyClipboard():
            raise RuntimeError("Could not clear the clipboard.")
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dib))
        if not handle:
            raise RuntimeError("Could not allocate clipboard memory.")
        locked = kernel32.GlobalLock(handle)
        if not locked:
            kernel32.GlobalFree(handle)
            raise RuntimeError("Could not lock clipboard memory.")
        ctypes.memmove(locked, dib, len(dib))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_DIB, handle):
            kernel32.GlobalFree(handle)
            raise RuntimeError("Could not place the screenshot on the clipboard.")
    finally:
        user32.CloseClipboard()


def _copy_other(image) -> None:
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    tool = shutil.which("wl-copy") or shutil.which("xclip")
    if tool is None:
        raise RuntimeError("Clipboard image copy needs wl-copy or xclip on this system.")
    png = _png_bytes(image)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        handle.write(png)
        path = handle.name
    try:
        if Path(tool).name == "wl-copy":
            result = subprocess.run([tool, "-t", "image/png"], input=png, check=False)
        else:
            result = subprocess.run(
                [tool, "-selection", "clipboard", "-t", "image/png", "-i", path],
                check=False,
            )
        if result.returncode != 0:
            raise RuntimeError("Could not place the screenshot on the clipboard.")
    finally:
        Path(path).unlink(missing_ok=True)
