"""PNG save and the smaller JPEG sent to OpenAI."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

from screenquery.paths import filename, resolve_directory, unique_filename


class ImageError(Exception):
    pass


def scale_size(width: int, height: int, max_side: int) -> tuple[int, int]:
    longest = max(width, height)
    if longest <= max_side or max_side <= 0:
        return width, height
    scale = max_side / longest
    return max(1, round(width * scale)), max(1, round(height * scale))


def save_png(image, custom_folder: str | None, when: datetime | None = None, home: Path | None = None) -> Path:
    moment = when or datetime.now().astimezone()
    root = home or Path.home()
    directory = resolve_directory(custom_folder, moment, root)
    if directory.exists() and not directory.is_dir():
        raise ImageError(f"The save folder is not a directory ({directory}).")
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ImageError(f"ScreenQuery could not write the screenshot to {directory}.") from exc
    existing = {path.name for path in directory.iterdir()} if directory.exists() else set()
    path = directory / unique_filename(filename(moment), existing)
    try:
        image.save(path, format="PNG")
    except OSError as exc:
        raise ImageError(f"ScreenQuery could not write the screenshot to {path}.") from exc
    return path


def prepared_jpeg(image, max_side: int = 2048, max_bytes: int = 4_500_000) -> bytes:
    """Downscale and JPEG-compress a screenshot for the vision request."""
    from PIL import Image

    source = image if isinstance(image, Image.Image) else Image.frombytes("RGB", image.size, image.tobytes())
    dimension = max_side
    quality = 82
    last = b""
    for _ in range(6):
        width, height = scale_size(source.width, source.height, dimension)
        resized = source if (width, height) == (source.width, source.height) else source.resize((width, height), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        rgb = resized.convert("RGB")
        rgb.save(buffer, format="JPEG", quality=quality)
        last = buffer.getvalue()
        if len(last) <= max_bytes:
            return last
        dimension = max(640, int(dimension * 0.75))
        quality = max(55, quality - 8)
    if last:
        return last
    raise ImageError("The screenshot could not be prepared for OpenAI.")
