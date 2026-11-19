"""CLI: ``python -m nmg_game_dev.godot`` runs the headless smoke run or the game screenshot (#251).

    smoke [--frames N] [--project PATH]
    shot <path> [--after S] [--project PATH] [-- <launch options>]

``--project`` defaults to ``<consumer root>/game/project.godot``. Smoke success prints
``smoke passed (<N> frames)``; shot success prints the ``{path, width, height}`` JSON. A
``PipelineError`` prints ``ERROR [<code>]: …`` and ``Remediation: …`` to stderr and exits 1.
Argument errors exit 2 through argparse. Tokens after ``--`` are the shot's launch options.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from nmg_game_dev.audio.paths import project_root
from nmg_game_dev.pipeline.errors import PipelineError

from .binary import resolve_godot
from .project import require_project
from .runner import GodotRunner, SubprocessGodotRunner
from .shot import take_shot
from .smoke import DEFAULT_FRAMES, run_smoke

__all__ = ["main"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nmg_game_dev.godot",
        description="Run the consumer's Godot game headless for a smoke run, or save a screenshot.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    smoke = commands.add_parser("smoke", help="Run the game headless and fail on runtime errors.")
    smoke.add_argument("--frames", type=int, default=DEFAULT_FRAMES)
    smoke.add_argument("--project", type=Path, default=None)
    shot = commands.add_parser("shot", help="Save a PNG of the running game after a delay.")
    shot.add_argument("path", type=Path, help="Where to write the PNG.")
    shot.add_argument("--after", type=float, default=3.0, help="Seconds to wait before saving.")
    shot.add_argument("--project", type=Path, default=None)
    return parser


def _split_at_separator(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    """Split ``argv`` at the first ``--``: the arguments before it, and the launch options after."""
    if "--" not in argv:
        return list(argv), []
    index = list(argv).index("--")
    return list(argv[:index]), list(argv[index + 1 :])


def main(argv: Sequence[str] | None = None, *, runner: GodotRunner | None = None) -> int:
    """Run one command and return its exit code. ``runner`` replaces the real Godot in tests."""
    head, options = _split_at_separator(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    args = parser.parse_args(head)
    if options and args.command != "shot":
        parser.error("launch options after -- are only accepted by the shot command")
    if args.command == "smoke" and args.frames < 1:
        parser.error("--frames must be at least 1")
    project_file: Path = args.project or project_root() / "game" / "project.godot"
    try:
        game = require_project(project_file)
        if args.command == "smoke":
            active = runner if runner is not None else SubprocessGodotRunner(resolve_godot())
            run_smoke(active, game, args.frames)
            print(f"smoke passed ({args.frames} frames)")
            return 0
        info = take_shot(game, args.path, args.after, options, runner=runner)
        print(json.dumps(info))
        return 0
    except PipelineError as error:
        print(f"ERROR [{error.code}]: {error.message}", file=sys.stderr)
        print(f"Remediation: {error.remediation}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
