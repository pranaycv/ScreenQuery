"""Screenshot folders and unique PNG names.

Both the default folder and a chosen folder use the same layout:
<base>/<YYYY-MM-DD>/ScreenQuery-<HHmmss>-<milliseconds>.png
Default base is ~/ScreenQuery.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


APP_FOLDER_NAME = "ScreenQuery"


def resolve_directory(
    custom_folder: str | None,
    when: datetime,
    home: Path,
) -> Path:
    custom = normalized_custom_folder(custom_folder, home)
    base = custom if custom is not None else home / APP_FOLDER_NAME
    return base / day_folder(when)


def filename(when: datetime) -> str:
    stamp = when.strftime("%H%M%S")
    millis = when.microsecond // 1000
    return f"ScreenQuery-{stamp}-{millis:03d}.png"


def unique_filename(preferred: str, existing: set[str]) -> str:
    if preferred not in existing:
        return preferred
    base, dot, ext = preferred.rpartition(".")
    if not dot:
        base, ext = preferred, "png"
    index = 2
    while index < 10_000:
        candidate = f"{base}-{index}.{ext}"
        if candidate not in existing:
            return candidate
        index += 1
    return f"{base}-{when_token()}.{ext}"


def day_folder(when: datetime) -> str:
    return when.strftime("%Y-%m-%d")


def normalized_custom_folder(custom_folder: str | None, home: Path) -> Path | None:
    if custom_folder is None:
        return None
    raw = custom_folder.strip()
    if not raw:
        return None
    raw = expand_tilde(raw, home)
    raw = strip_trailing_slashes(raw)
    if raw in {"", "~"}:
        return None
    path = Path(raw)
    if path.is_absolute():
        return path
    return home / raw


def expand_tilde(path: str, home: Path) -> str:
    home_path = strip_trailing_slashes(str(home))
    if path == "~":
        return home_path
    if path.startswith("~/") or path.startswith("~\\"):
        return str(Path(home_path) / path[2:])
    return path


def strip_trailing_slashes(path: str) -> str:
    if path in {"/", "\\"}:
        return path
    while len(path) > 1 and path.endswith(("/", "\\")):
        path = path[:-1]
    return path


def abbreviate(path: Path, home: Path) -> str:
    try:
        relative = path.resolve().relative_to(home.resolve())
    except (ValueError, OSError):
        try:
            relative = path.relative_to(home)
        except ValueError:
            return str(path)
    return "~/" + relative.as_posix()


def when_token() -> str:
    return datetime.now().strftime("%H%M%S%f")
