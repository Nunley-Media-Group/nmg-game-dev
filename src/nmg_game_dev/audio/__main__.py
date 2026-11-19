"""CLI: ``python -m nmg_game_dev.audio`` with ``import`` and ``refinish`` subcommands (#155, #252).

``import --file F --name N --kind sfx|music [--loop] [--max-seconds S] [--loudness-lufs L]
[--loop-crossfade-ms MS] [--finish | --no-finish]`` calls ``import_audio``.
``refinish (--all | Name ...)`` calls ``refinish``. Both are the same functions the finalize
``import_audio`` tool and the tests call, and they print the same JSON. A ``PipelineError``
prints ``ERROR [<code>] <message>`` and ``Remediation: <text>`` to stderr and exits 1. Argument
errors exit 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from nmg_game_dev.audio.core import import_audio, refinish
from nmg_game_dev.audio.request import KINDS
from nmg_game_dev.pipeline.errors import PipelineError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nmg_game_dev.audio",
        description="Import a saved ElevenLabs sound effect or music file into the Godot project.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    imp = sub.add_parser(
        "import",
        help="Finish a WAV, store it under SourceArt, and import it into game/assets/Audio/.",
    )
    imp.add_argument("--file", required=True, type=Path, help="Saved .wav, .mp3, .ogg, or .flac.")
    imp.add_argument("--name", required=True, help="PascalCase asset name, e.g. DoorCreak.")
    imp.add_argument("--kind", required=True, choices=sorted(KINDS), help="sfx or music.")
    imp.add_argument("--loop", action="store_true", help="Make the imported stream loop.")
    imp.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help="Cut the sound to at most this many seconds. Stored per sound.",
    )
    imp.add_argument(
        "--loudness-lufs",
        type=float,
        default=None,
        help="Integrated loudness target, -40 to -5 LUFS (default -16 sfx, -18 music).",
    )
    imp.add_argument(
        "--loop-crossfade-ms",
        type=int,
        default=None,
        help="Length of the loop seam crossfade in milliseconds (default 500).",
    )
    imp.add_argument(
        "--finish",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="--no-finish imports the stored WAV unchanged: no trim, cut, loop crossfade, or "
        "loudness match. --finish turns finishing back on. Default: the stored setting, else on.",
    )
    imp.add_argument("--project", type=Path, default=None, help="Project root (default: CWD).")

    ref = sub.add_parser(
        "refinish",
        help="Re-finish stored sounds from SourceArt with the settings in audio.json.",
    )
    ref.add_argument("names", nargs="*", metavar="Name", help="Sound names listed in audio.json.")
    ref.add_argument("--all", action="store_true", help="Re-finish every sound in audio.json.")
    ref.add_argument("--project", type=Path, default=None, help="Project root (default: CWD).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result: Any
        if args.command == "import":
            result = import_audio(
                args.file,
                args.name,
                args.kind,
                args.loop,
                max_seconds=args.max_seconds,
                loudness_lufs=args.loudness_lufs,
                loop_crossfade_ms=args.loop_crossfade_ms,
                finish=args.finish,
                project_root=args.project,
            )
        else:
            if args.all == bool(args.names):
                parser.error("refinish takes either --all or one or more sound names")
            result = refinish(None if args.all else args.names, project_root=args.project)
    except PipelineError as error:
        print(f"ERROR [{error.code}] {error.message}", file=sys.stderr)
        print(f"Remediation: {error.remediation}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
