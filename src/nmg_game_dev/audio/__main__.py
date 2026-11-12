"""CLI: ``python -m nmg_game_dev.audio import --file F --name N --kind sfx|music [--loop]`` (#155).

The CLI calls ``import_audio``, the same function the finalize ``import_audio`` tool calls, and
prints the same JSON. A ``PipelineError`` prints ``ERROR [<code>] <message>`` and
``Remediation: <text>`` to stderr and exits 1. Argument errors exit 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from nmg_game_dev.audio.core import import_audio
from nmg_game_dev.audio.request import KINDS
from nmg_game_dev.pipeline.clients.unreal_mcp import UnrealMcpClient
from nmg_game_dev.pipeline.errors import PipelineError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nmg_game_dev.audio",
        description="Import a saved ElevenLabs sound effect or music file into Unreal (#155).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import", help="Store a WAV under SourceArt and import it as a SoundWave.")
    imp.add_argument("--file", required=True, type=Path, help="Saved .wav, .mp3, .ogg, or .flac.")
    imp.add_argument("--name", required=True, help="PascalCase asset name, e.g. DoorCreak.")
    imp.add_argument("--kind", required=True, choices=sorted(KINDS), help="sfx or music.")
    imp.add_argument("--loop", action="store_true", help="Set the SoundWave to loop.")
    imp.add_argument("--project", type=Path, default=None, help="Project root (default: CWD).")
    imp.add_argument("--url", default=None, help="Unreal MCP endpoint (default: UE_MCP_PORT).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    client = UnrealMcpClient(args.url) if args.url else None
    try:
        result = import_audio(
            args.file,
            args.name,
            args.kind,
            args.loop,
            project_root=args.project,
            unreal_client=client,
        )
    except PipelineError as error:
        print(f"ERROR [{error.code}] {error.message}", file=sys.stderr)
        print(f"Remediation: {error.remediation}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
