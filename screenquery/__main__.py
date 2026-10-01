"""python -m screenquery"""

from __future__ import annotations

import os
import sys

from screenquery import __version__


def main() -> None:
    if "--check" in sys.argv:
        message = f"ScreenQuery {__version__} on {sys.platform}"
        print(message)
        marker = os.environ.get("SCREENQUERY_CHECK_FILE")
        if marker:
            from pathlib import Path

            Path(marker).write_text(message + "\n", encoding="utf-8")
        return
    from screenquery.app import run

    run()


if __name__ == "__main__":
    main()
