"""CLI: ``python -m nmg_game_dev.secrets scan [--staged | --tracked] [--root PATH]`` (#255).

The flags and exit codes belong to ``nmg_game_dev.secrets.scan.main``: 0 when clean, 1 with one
masked line per match, 2 when git fails.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from nmg_game_dev.secrets.scan import main as scan_main

USAGE = "usage: python -m nmg_game_dev.secrets scan [--staged | --tracked] [--root PATH]"


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "scan":
        print(USAGE, file=sys.stderr)
        return 2
    return scan_main(args[1:])


if __name__ == "__main__":
    raise SystemExit(main())
