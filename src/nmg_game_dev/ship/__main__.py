"""CLI: ``python -m nmg_game_dev.ship <target> --project <game/project.godot> [--release-dir DIR]``.

``--bump major|minor|patch`` or ``--version X.Y.Z`` sets the build version (#254); they are mutually
exclusive, and with neither the current version ships. ``--release-dir`` defaults to
``<consumer root>/release``, the folder above ``game/``. On a ``PipelineError`` (``ShipError``,
``godot.not_found``) the CLI prints ``ERROR [<code>]: …`` and ``Remediation: …`` to stderr and exits
1. Argument errors exit 2 through argparse.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.ship.release_notes import RELEASE_NOTES_NAME
from nmg_game_dev.ship.runner import run_ship
from nmg_game_dev.ship.targets import TARGETS
from nmg_game_dev.ship.version import BUMPS


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m nmg_game_dev.ship",
        description="Gate, export, sign, notarize, and package an NMG Godot game per platform.",
    )
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument(
        "--project", required=True, type=Path, help="Path to the consumer's game/project.godot."
    )
    parser.add_argument(
        "--release-dir",
        type=Path,
        default=None,
        help="Release folder. Defaults to <consumer root>/release.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the plan; export nothing.")
    version_flags = parser.add_mutually_exclusive_group()
    version_flags.add_argument(
        "--bump",
        choices=BUMPS,
        default=None,
        help="Raise the current version by one part, then ship it.",
    )
    version_flags.add_argument(
        "--version",
        default=None,
        metavar="X.Y.Z",
        help="Ship this version, which must be greater than the current one.",
    )
    args = parser.parse_args(argv)
    release_dir: Path = args.release_dir or args.project.parent.parent / "release"
    try:
        entries = run_ship(
            args.target,
            args.project,
            release_dir,
            args.dry_run,
            dict(os.environ),
            bump=args.bump,
            version=args.version,
        )
    except PipelineError as error:
        print(f"ERROR [{error.code}]: {error.message}", file=sys.stderr)
        print(f"Remediation: {error.remediation}", file=sys.stderr)
        return 1
    for entry in entries:
        print(f"{entry.platform}: {entry.path} sha256={entry.sha256}")
    print(f"Release notes: {release_dir / RELEASE_NOTES_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
