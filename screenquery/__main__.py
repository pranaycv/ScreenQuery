"""python -m screenquery"""

from __future__ import annotations

import sys

from screenquery import __version__


def main() -> None:
    if "--check" in sys.argv:
        print(f"ScreenQuery {__version__} on {sys.platform}")
        return
    from screenquery.app import run

    run()


if __name__ == "__main__":
    main()
