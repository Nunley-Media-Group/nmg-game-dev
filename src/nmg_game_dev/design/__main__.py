"""Command line for the design backlog (#112).

    python -m nmg_game_dev.design sync [--project DIR]
    python -m nmg_game_dev.design scaffold [--project DIR] [--url URL]

``sync`` parses ``docs/design/**/*.md`` into ``docs/design/backlog.json`` and prints one
``<status> <type> <asset_name>: <source>`` line per entry.  On any ``design.*`` error it prints
every error line and writes nothing.  ``scaffold`` creates the region, mission, and system assets
in the open Unreal editor and prints ``created``, ``unchanged``, ``skipped``, or ``error`` lines.

Exit codes: 0 success; 1 a design error, a failed item, or a missing or unreadable backlog;
2 the Unreal editor is unreachable (``mcp.unreal.unreachable``).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, TextIO

from nmg_game_dev.pipeline.clients.unreal_mcp import UnrealMcpClient
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.unreal.import_asset import UnrealPythonClient

from . import backlog
from .parse import parse_tree
from .paths import backlog_path, project_root
from .scaffold import UNREACHABLE, ScaffoldReport, run_scaffold

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_PREREQUISITE: Final = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nmg_game_dev.design",
        description="Sync markdown design docs into a backlog and scaffold them in Unreal.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    sync = commands.add_parser("sync", help="Parse docs/design into docs/design/backlog.json.")
    _add_project_argument(sync)

    scaffold = commands.add_parser(
        "scaffold", help="Create the region, mission, and system assets in Unreal."
    )
    _add_project_argument(scaffold)
    scaffold.add_argument(
        "--url",
        help="Unreal MCP endpoint. Defaults to http://127.0.0.1:$UE_MCP_PORT/mcp.",
    )
    return parser


def _add_project_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        type=Path,
        help="Project root. Defaults to CLAUDE_PROJECT_DIR, or the working directory.",
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    client: UnrealPythonClient | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the command and return its exit code.

    ``client`` replaces the live Unreal MCP client.  Tests pass a fake.
    """
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    args = build_parser().parse_args(argv)
    root = args.project if args.project is not None else project_root()
    if args.command == "sync":
        return _sync(root, out, err)
    return _scaffold(root, client, args.url, out, err)


def _sync(root: Path, out: TextIO, err: TextIO) -> int:
    entries, errors = parse_tree(root)
    if errors:
        for error in errors:
            out.write(error.line() + "\n")
        return EXIT_FAILED

    path = backlog_path(root)
    try:
        previous = backlog.load(path)
    except ValueError as error:
        err.write(f"ERROR: {error}. Fix or delete the file, then run sync again.\n")
        return EXIT_FAILED
    merged = backlog.merge(previous, entries)
    backlog.write_atomic(path, backlog.dump(merged))
    for entry in merged:
        out.write(f"{entry.status} {entry.type} {entry.asset_name}: {entry.source}\n")
    return EXIT_OK


def _scaffold(
    root: Path,
    client: UnrealPythonClient | None,
    url: str | None,
    out: TextIO,
    err: TextIO,
) -> int:
    report = ScaffoldReport()
    try:
        if client is not None:
            run_scaffold(client, root, report)
        else:
            with UnrealMcpClient(url) as live:
                run_scaffold(live, root, report)
    except FileNotFoundError:
        err.write(
            f"ERROR: {backlog_path(root)} does not exist. Run `python -m nmg_game_dev.design sync` "
            "first.\n"
        )
        return EXIT_FAILED
    except ValueError as error:
        err.write(f"ERROR: {error}. Fix or delete the file, then run scaffold again.\n")
        return EXIT_FAILED
    except PipelineError as error:
        _print_report(report, out)
        err.write(f"ERROR [{error.code}] {error.message}\n")
        err.write(f"Remediation: {error.remediation}\n")
        return EXIT_PREREQUISITE if error.code == UNREACHABLE else EXIT_FAILED

    _print_report(report, out)
    return EXIT_FAILED if report.failed else EXIT_OK


def _print_report(report: ScaffoldReport, out: TextIO) -> None:
    for line in report.lines:
        out.write(line.text() + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
