"""ScreenQuery mark in the EyesRhythm family.

Same soft blue rounded square (#5B9FE0, same corner radius). The glyph is a
white screen with a question mark: a capture you can ask about, not an eye.
"""

from __future__ import annotations

from pathlib import Path

# EyesRhythm brand blue, mist, and ink.
BLUE = (91, 159, 224, 255)
WHITE = (255, 255, 255, 255)
INK = (26, 42, 56, 255)

_FONT = Path(__file__).resolve().parents[1] / "frontend" / "public" / "fonts" / "Inter-Bold.ttf"


def draw_icon(size: int = 64):
    from PIL import Image, ImageDraw, ImageFont

    canvas = size if size >= 512 else max(size * 8, 256)
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    unit = canvas / 128.0

    def at(value: float) -> float:
        return value * unit

    draw.rounded_rectangle(
        [at(4), at(4), at(124), at(124)],
        radius=at(36),
        fill=BLUE,
    )
    # Screenshot card. Same visual mass as EyesRhythm's eye, rectangular.
    draw.rounded_rectangle(
        [at(26), at(34), at(102), at(94)],
        radius=at(16),
        fill=WHITE,
    )
    font_size = max(8, int(round(40 * unit)))
    font = _font(font_size)
    draw.text((at(64), at(64)), "?", font=font, fill=INK, anchor="mm")
    if canvas != size:
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    return image


def _font(size: int):
    from PIL import ImageFont

    if _FONT.is_file():
        return ImageFont.truetype(str(_FONT), size=size)
    return ImageFont.load_default()
