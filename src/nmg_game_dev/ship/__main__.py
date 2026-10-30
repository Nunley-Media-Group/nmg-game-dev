"""CLI: ``python -m nmg_game_dev.ship <target> --project <uproject> [--release-dir DIR]``.

On ``ShipError`` the CLI prints ``ERROR [<code>]: …`` and ``Remediation: …`` to stderr and exits 1.
Argument errors exit 2 through argparse.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.release_notes import RELEASE_NOTES_NAME
from nmg_game_dev.ship.runner import run_ship
from nmg_game_dev.ship.targets import TARGETS


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m nmg_game_dev.ship",
        description="Build, gate, sign, notarize, and package an NMG game per platform.",
    )
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--project", required=True, type=Path, help="Path to the .uproject file.")
    parser.add_argument(
        "--release-dir",
        type=Path,
        default=None,
        help="Release folder. Defaults to <project dir>/release.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the plan; build nothing.")
    args = parser.parse_args(argv)
    release_dir: Path = args.release_dir or args.project.parent / "release"
    try:
        entries = run_ship(args.target, args.project, release_dir, args.dry_run, dict(os.environ))
    except ShipError as error:
        print(f"ERROR [{error.code}]: {error.message}", file=sys.stderr)
        print(f"Remediation: {error.remediation}", file=sys.stderr)
        return 1
    for entry in entries:
        print(f"{entry.platform}: {entry.path} sha256={entry.sha256}")
    print(f"Release notes: {release_dir / RELEASE_NOTES_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
