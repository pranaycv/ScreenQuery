"""Full-desktop screenshot. mss monitor 0 is every display in one image."""

from __future__ import annotations


def grab_fullscreen():
    import mss
    from PIL import Image

    with mss.mss() as sct:
        if not sct.monitors:
            raise RuntimeError("No display was available to capture.")
        shot = sct.grab(sct.monitors[0])
        return Image.frombytes("RGB", shot.size, shot.rgb)
