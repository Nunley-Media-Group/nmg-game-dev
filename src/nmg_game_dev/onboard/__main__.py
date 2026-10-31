"""CLI: ``python -m nmg_game_dev.onboard install|volumes``.

``install`` onboards a consumer and prints the step report (``--json`` for JSON). Drift exits 0. A
preflight or step failure prints ``ERROR [<code>]: …`` and ``Remediation: …`` to stderr and exits 1.
``volumes`` prints the JSON list of volumes and whether each fits the texture models.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from nmg_game_dev.onboard.errors import OnboardError
from nmg_game_dev.onboard.paths import framework_root
from nmg_game_dev.onboard.report import format_report
from nmg_game_dev.onboard.runner import run_onboard
from nmg_game_dev.onboard.volumes import volumes_json


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nmg_game_dev.onboard",
        description="Onboard a consumer game project to nmg-game-dev.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install", help="Install or re-verify the framework in a consumer.")
    install.add_argument("--consumer", type=Path, required=True, help="The consumer project root.")
    install.add_argument(
        "--uproject", type=Path, default=None, help="The .uproject, if not unique."
    )
    install.add_argument(
        "--models-dir",
        type=Path,
        default=None,
        help="Folder for the texture models (default: TEXTURE_GEN_MODELS_DIR).",
    )
    install.add_argument(
        "--refresh",
        action="store_true",
        help="Restore drifted framework-owned copies and move VibeUE to its 5-8 branch head.",
    )
    install.add_argument("--json", action="store_true", help="Print the report as JSON.")

    sub.add_parser("volumes", help="List volumes and whether each fits the texture models.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "volumes":
        print(volumes_json())
        return 0
    env = dict(os.environ)
    try:
        results = run_onboard(
            args.consumer,
            framework=framework_root(env),
            uproject=args.uproject,
            models_dir=args.models_dir,
            refresh=args.refresh,
            env=env,
        )
    except OnboardError as error:
        print(f"ERROR [{error.code}]: {error.message}", file=sys.stderr)
        print(f"Remediation: {error.remediation}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps([result.as_json() for result in results], indent=2))
    else:
        print(format_report(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
