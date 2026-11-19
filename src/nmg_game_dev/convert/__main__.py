"""CLI: ``python -m nmg_game_dev.convert [--project DIR] [--models-dir DIR] [--dry-run] [--json]``.

#249 FR11.

Exit 0 when every item converted (or a dry run planned it), 1 on a guard or item failure, and 2 on
an argument error. A guard failure prints ``ERROR [<code>]: …`` and ``Remediation: …`` to stderr.
``--json`` prints the result as JSON after the progress lines.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from nmg_game_dev.convert.runner import default_onboard, run_convert
from nmg_game_dev.pipeline.errors import PipelineError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nmg_game_dev.convert",
        description="Convert an Unreal consumer project to Godot.",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="The consumer root. Default: CLAUDE_PROJECT_DIR when set, else the working directory.",
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=None,
        help="The texture models folder onboarding checks. Default: TEXTURE_GEN_MODELS_DIR.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the planned conversions and deletions only."
    )
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exit_:
        return 2 if exit_.code not in (0, None) else 0
    project: Path
    if args.project is not None:
        project = args.project
    else:
        raw = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
        project = Path(raw) if raw else Path.cwd()
    if not project.is_dir():
        print(f"error: --project {project} is not a directory", file=sys.stderr)
        return 2
    try:
        models_dir: Path | None = args.models_dir
        result = run_convert(
            project,
            dry_run=args.dry_run,
            onboard=lambda root: default_onboard(root, models_dir=models_dir),
        )
    except PipelineError as error:
        print(f"ERROR [{error.code}]: {error.message}", file=sys.stderr)
        print(f"Remediation: {error.remediation}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result.as_json(), indent=2))
    for failure in result.failures:
        print(f"ERROR [{failure.code}] {failure.item}: {failure.message}", file=sys.stderr)
        print(f"Remediation: {failure.remediation}", file=sys.stderr)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
