"""Capture the frontmost window, or the whole desktop if none is usable."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass

log = logging.getLogger("screenquery")

NO_WINDOW = (
    "No suitable window was found to capture. "
    "Focus the window you want, then try again."
)
SCREEN_RECORDING_DENIED = (
    "ScreenQuery is on in Screen & System Audio Recording for an older copy. "
    "Turn that switch off, then on, quit ScreenQuery, and open it again."
)

# Menu bar, our own UI, and the Screen Recording permission prompt. That prompt
# sits at the front of the window list while a real app window is focused, and
# screencapture cannot read it — which used to be reported as "no window".
_SKIP_OWNERS = {
    "Window Server",
    "Dock",
    "DockHelper",
    "SystemUIServer",
    "Control Center",
    "ControlCenter",
    "Notification Center",
    "NotificationCenter",
    "Spotlight",
    "ScreenQuery",
    "ScreenQuery Settings",
    "universalAccessAuthWarn",
    "CoreServicesUIAgent",
    "UserNotificationCenter",
    "loginwindow",
    "ScreenSaverEngine",
    "OSDUIHelper",
    "TextInputMenuAgent",
    "Wallpaper",
    "WallpaperAgent",
}

_SKIP_NAMES = {
    "Screen Recording",
    "ScreenQuery",
    "ScreenQuery Settings",
}


@dataclass(frozen=True)
class Display:
    """A screen in CoreGraphics points. Origin is the top-left, Y grows down."""

    x: float
    y: float
    width: float
    height: float
    display_id: int = 0


def display_containing(bounds, displays):
    """The display that holds the window's center, not merely the laptop."""
    try:
        cx = float(bounds.get("X", 0)) + float(bounds.get("Width", 0)) / 2
        cy = float(bounds.get("Y", 0)) + float(bounds.get("Height", 0)) / 2
    except (TypeError, ValueError):
        return None
    for display in displays:
        if display.x <= cx < display.x + display.width and display.y <= cy < display.y + display.height:
            return display
    return None


def crop_box(bounds, display: Display, image_width: int, image_height: int):
    """Window rectangle inside one display's pixel image.

    Returns None when the image size is not that display (for example the
    Retina laptop buffer passed in for a 1x extended screen). Callers must
    not then sample the laptop.
    """
    if display.width <= 0 or display.height <= 0 or image_width < 2 or image_height < 2:
        return None
    scale_x = image_width / display.width
    scale_y = image_height / display.height
    if abs(scale_x - scale_y) > 0.15:
        return None
    try:
        origin_x = float(bounds.get("X", 0))
        origin_y = float(bounds.get("Y", 0))
        width = float(bounds.get("Width", 0))
        height = float(bounds.get("Height", 0))
    except (TypeError, ValueError):
        return None
    left = int(round((origin_x - display.x) * scale_x))
    top = int(round((origin_y - display.y) * scale_y))
    right = int(round(left + width * scale_x))
    bottom = int(round(top + height * scale_y))
    if right - left < 2 or bottom - top < 2:
        return None
    if right <= 0 or bottom <= 0 or left >= image_width or top >= image_height:
        return None
    return (max(0, left), max(0, top), min(image_width, right), min(image_height, bottom))


def clip_to_display(bounds, display: Display):
    """The part of a top-left rectangle that lies on one display. None if it misses."""
    try:
        origin_x = float(bounds.get("X", 0))
        origin_y = float(bounds.get("Y", 0))
        width = float(bounds.get("Width", 0))
        height = float(bounds.get("Height", 0))
    except (TypeError, ValueError):
        return None
    left = max(origin_x, display.x)
    top = max(origin_y, display.y)
    right = min(origin_x + width, display.x + display.width)
    bottom = min(origin_y + height, display.y + display.height)
    if right - left < 2 or bottom - top < 2:
        return None
    return {"X": left, "Y": top, "Width": right - left, "Height": bottom - top}


def screen_recording_allowed() -> bool:
    """True only when this process already has the Screen Recording grant.

    Does not prompt. CGDisplayCreateImage and CGWindowListCreateImage show the
    system dialog whenever this is false, so callers must check first.
    """
    if sys.platform != "darwin":
        return True
    try:
        import Quartz

        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        return False


def grab_active_window():
    """Frontmost normal app window, or every display in one image."""
    if sys.platform == "darwin" and not screen_recording_allowed():
        raise RuntimeError(SCREEN_RECORDING_DENIED)
    if sys.platform == "darwin":
        return _grab_macos()
    if sys.platform == "win32":
        try:
            return _grab_windows()
        except RuntimeError:
            return grab_fullscreen()
    return grab_fullscreen()


def grab_region(bounds):
    """Crop a rectangle in CoreGraphics points. Origin is top-left, Y grows down.

    A rectangle on one display is cropped from that display's own pixels, so a
    2x laptop and a 1x extended screen are not mixed. A rectangle that crosses
    the bezel is pasted together in point space.
    """
    if sys.platform == "darwin" and not screen_recording_allowed():
        raise RuntimeError(SCREEN_RECORDING_DENIED)
    if sys.platform != "darwin":
        return _grab_region(
            int(bounds.get("X", 0)),
            int(bounds.get("Y", 0)),
            int(bounds.get("Width", 0)),
            int(bounds.get("Height", 0)),
        )
    return _grab_region_macos(bounds)


def grab_fullscreen():
    """Every display in one image. On macOS that includes the extended screen."""
    if sys.platform == "darwin":
        try:
            return _grab_all_displays()
        except Exception:
            log.exception("Could not composite the displays")
    import mss
    from PIL import Image

    with mss.mss() as sct:
        if not sct.monitors:
            raise RuntimeError("No display was available to capture.")
        shot = sct.grab(sct.monitors[0])
        return Image.frombytes("RGB", shot.size, shot.rgb)


def choose_window(windows, my_pid: int, front_pid: int | None = None):
    """Pick the frontmost on-screen window that is not ScreenQuery itself."""
    ordered = iter_capture_windows(windows, my_pid, front_pid)
    return ordered[0] if ordered else None


def iter_capture_windows(windows, my_pid: int, front_pid: int | None = None):
    """Usable windows, front app first, then the rest in z-order."""
    candidates = [win for win in windows if _usable(win, my_pid)]
    if front_pid is not None and front_pid != my_pid:
        owned = [win for win in candidates if _pid(win) == front_pid]
        if owned:
            rest = [win for win in candidates if _pid(win) != front_pid]
            return owned + rest
    return candidates


def resolve_capture(windows, my_pid: int, front_pid, capture_window, capture_screen):
    """Try each real window, then the full desktop. Always returns an image."""
    last_error = None
    for win in iter_capture_windows(windows, my_pid, front_pid):
        try:
            return capture_window(win)
        except Exception as exc:
            last_error = exc
            continue
    try:
        return capture_screen()
    except Exception:
        if last_error is not None:
            raise last_error
        raise


def _usable(win, my_pid: int) -> bool:
    if win is None or not hasattr(win, "get"):
        return False
    owner = str(win.get("kCGWindowOwnerName") or "")
    if owner in _SKIP_OWNERS:
        return False
    name = str(win.get("kCGWindowName") or "")
    if name in _SKIP_NAMES:
        return False
    try:
        pid = int(win.get("kCGWindowOwnerPID"))
    except (TypeError, ValueError):
        return False
    if pid == my_pid:
        return False
    try:
        layer = int(win.get("kCGWindowLayer", 0))
    except (TypeError, ValueError):
        layer = 0
    if layer != 0:
        return False
    bounds = win.get("kCGWindowBounds") or {}
    try:
        width = float(bounds.get("Width", 0))
        height = float(bounds.get("Height", 0))
    except (TypeError, ValueError):
        return False
    if width < 80 or height < 80:
        return False
    try:
        alpha = float(win.get("kCGWindowAlpha", 1))
    except (TypeError, ValueError):
        alpha = 1
    if alpha <= 0:
        return False
    return win.get("kCGWindowNumber") is not None


def _pid(win) -> int | None:
    try:
        return int(win.get("kCGWindowOwnerPID"))
    except (TypeError, ValueError):
        return None


def _grab_macos():
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGNullWindowID,
        kCGWindowListExcludeDesktopElements,
        kCGWindowListOptionOnScreenOnly,
    )

    options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
    info = CGWindowListCopyWindowInfo(options, kCGNullWindowID) or []
    front_pid = _frontmost_pid()

    def capture_window(win):
        # The display that contains the window, then that window's rectangle.
        # A window-id grab can come back as the built-in screen when the
        # window lives on an extended display.
        try:
            return _crop_window(win)
        except Exception:
            log.info("Could not crop %s from its display", win.get("kCGWindowOwnerName"))
        return _capture_window_id(int(win["kCGWindowNumber"]))

    return resolve_capture(info, os.getpid(), front_pid, capture_window, grab_fullscreen)


def _frontmost_pid() -> int | None:
    try:
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
    except Exception:
        return None
    if app is None:
        return None
    try:
        return int(app.processIdentifier())
    except (TypeError, ValueError):
        return None


def _capture_window_id(window_id: int):
    """Read one window through Quartz. screencapture -l fails for this app."""
    from Quartz import (
        CGDataProviderCopyData,
        CGImageGetBytesPerRow,
        CGImageGetDataProvider,
        CGImageGetHeight,
        CGImageGetWidth,
        CGRectNull,
        CGWindowListCreateImage,
        kCGWindowImageBoundsIgnoreFraming,
        kCGWindowListOptionIncludingWindow,
    )

    cg = CGWindowListCreateImage(
        CGRectNull,
        kCGWindowListOptionIncludingWindow,
        window_id,
        kCGWindowImageBoundsIgnoreFraming,
    )
    if cg is None:
        log.info("Window %s was not captured", window_id)
        raise RuntimeError(NO_WINDOW)
    width = int(CGImageGetWidth(cg))
    height = int(CGImageGetHeight(cg))
    if width < 2 or height < 2:
        log.info("Window %s came back empty", window_id)
        raise RuntimeError(NO_WINDOW)
    return _cgimage_to_pil(cg)


def _cgimage_to_pil(cg):
    from PIL import Image
    from Quartz import (
        CGDataProviderCopyData,
        CGImageGetBytesPerRow,
        CGImageGetDataProvider,
        CGImageGetHeight,
        CGImageGetWidth,
    )

    width = int(CGImageGetWidth(cg))
    height = int(CGImageGetHeight(cg))
    if width < 2 or height < 2:
        raise RuntimeError(NO_WINDOW)
    stride = int(CGImageGetBytesPerRow(cg))
    raw = bytes(CGDataProviderCopyData(CGImageGetDataProvider(cg)))
    # Little-endian premultiplied ARGB is B, G, R, A in memory. Alpha is opaque.
    image = Image.frombytes("RGBA", (width, height), raw, "raw", "BGRA", stride, 1)
    return image.convert("RGB")


def _crop_window(win):
    """Crop the window from the display that actually contains it.

    A combined desktop image mixes a 2x laptop with a 1x extended screen, so
    point offsets land on the built-in display. Capturing that one screen
    avoids the mix-up.
    """
    bounds = win.get("kCGWindowBounds") or {}
    displays = _macos_displays()
    display = display_containing(bounds, displays)
    if display is None:
        raise RuntimeError(NO_WINDOW)
    image = _display_image(display.display_id)
    box = crop_box(bounds, display, image.width, image.height)
    if box is None:
        raise RuntimeError(NO_WINDOW)
    return image.crop(box)


def _macos_displays() -> list[Display]:
    import Quartz

    _err, ids, _count = Quartz.CGGetActiveDisplayList(16, None, None)
    displays = []
    for display_id in ids:
        bounds = Quartz.CGDisplayBounds(display_id)
        displays.append(
            Display(
                x=float(bounds.origin.x),
                y=float(bounds.origin.y),
                width=float(bounds.size.width),
                height=float(bounds.size.height),
                display_id=int(display_id),
            )
        )
    return displays


def _display_image(display_id: int):
    import Quartz

    cg = Quartz.CGDisplayCreateImage(display_id)
    if cg is None:
        raise RuntimeError(NO_WINDOW)
    return _cgimage_to_pil(cg)


def _grab_region_macos(bounds):
    from PIL import Image

    displays = _macos_displays()
    hits = []
    for display in displays:
        clipped = clip_to_display(bounds, display)
        if clipped is not None:
            hits.append((display, clipped))
    if not hits:
        raise RuntimeError("That rectangle is off the screen. Drag over the part you want.")
    if len(hits) == 1:
        display, clipped = hits[0]
        image = _display_image(display.display_id)
        box = crop_box(clipped, display, image.width, image.height)
        if box is None:
            raise RuntimeError("That rectangle is too small. Drag across the word or the line.")
        return image.crop(box)

    width = max(1, int(round(float(bounds.get("Width", 1)))))
    height = max(1, int(round(float(bounds.get("Height", 1)))))
    canvas = Image.new("RGB", (width, height), (0, 0, 0))
    origin_x = float(bounds.get("X", 0))
    origin_y = float(bounds.get("Y", 0))
    for display, clipped in hits:
        image = _display_image(display.display_id)
        box = crop_box(clipped, display, image.width, image.height)
        if box is None:
            continue
        crop = image.crop(box)
        point_size = (max(1, int(round(clipped["Width"]))), max(1, int(round(clipped["Height"]))))
        if crop.size != point_size:
            crop = crop.resize(point_size, Image.Resampling.LANCZOS)
        canvas.paste(
            crop,
            (int(round(clipped["X"] - origin_x)), int(round(clipped["Y"] - origin_y))),
        )
    return canvas


def _grab_all_displays():
    from PIL import Image

    displays = _macos_displays()
    if not displays:
        raise RuntimeError("No display was available to capture.")
    shots = []
    for display in displays:
        image = _display_image(display.display_id)
        # Draw every screen in point space so a 2x laptop does not crowd out
        # the extended display.
        point = image.resize((max(1, int(round(display.width))), max(1, int(round(display.height)))), Image.Resampling.LANCZOS)
        shots.append((display, point))
    min_x = min(display.x for display, _image in shots)
    min_y = min(display.y for display, _image in shots)
    max_x = max(display.x + display.width for display, _image in shots)
    max_y = max(display.y + display.height for display, _image in shots)
    canvas = Image.new("RGB", (max(1, int(round(max_x - min_x))), max(1, int(round(max_y - min_y)))), (0, 0, 0))
    for display, image in shots:
        canvas.paste(image, (int(round(display.x - min_x)), int(round(display.y - min_y))))
    return canvas


def _grab_windows():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    my_pid = os.getpid()
    hwnd = user32.GetForegroundWindow()
    GW_HWNDNEXT = 2
    for _ in range(40):
        if not hwnd:
            break
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != my_pid and user32.IsWindowVisible(hwnd):
            rect = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                width = int(rect.right - rect.left)
                height = int(rect.bottom - rect.top)
                if width >= 80 and height >= 80:
                    return _grab_region(int(rect.left), int(rect.top), width, height)
        hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)
    raise RuntimeError(NO_WINDOW)


def _grab_region(left: int, top: int, width: int, height: int):
    import mss
    from PIL import Image

    with mss.mss() as sct:
        shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
        return Image.frombytes("RGB", shot.size, shot.rgb)
