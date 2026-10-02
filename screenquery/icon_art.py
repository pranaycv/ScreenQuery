"""Small viewfinder icon drawn with Pillow for the tray and frozen builds."""

from __future__ import annotations


def draw_icon(size: int = 64):
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (size, size), (47, 111, 255, 255))
    draw = ImageDraw.Draw(image)
    margin = int(size * 0.18)
    arm = int(size * 0.28)
    thick = max(2, int(size * 0.08))
    color = (255, 255, 255, 255)
    # Four viewfinder corners.
    pairs = (
        (margin, margin, 1, 1),
        (size - margin, margin, -1, 1),
        (margin, size - margin, 1, -1),
        (size - margin, size - margin, -1, -1),
    )
    for x, y, sx, sy in pairs:
        hx = x if sx > 0 else x - arm
        draw.rectangle((hx, y - thick // 2, hx + arm, y + thick // 2), fill=color)
        vy = y if sy > 0 else y - arm
        vx = x - thick // 2 if sx > 0 else x - thick // 2
        draw.rectangle((vx, vy, vx + thick, vy + arm), fill=color)
    center = size // 2
    radius = int(size * 0.12)
    draw.ellipse(
        (center - radius, center - radius, center + radius, center + radius),
        outline=color,
        width=thick,
    )
    dot = max(2, thick // 2)
    draw.ellipse((center - dot, center - dot, center + dot, center + dot), fill=color)
    return image
