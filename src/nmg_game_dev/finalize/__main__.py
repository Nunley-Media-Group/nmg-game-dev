"""Command line for the finalize pipeline (#69).

    python -m nmg_game_dev.finalize {all,validate,bake,variants,export,reimport,import_ue}
        --collection N --category C --class K --export-root R
        [--blend B] [--budgets P] [--device GPU|CPU] [--force] [--json]

    python -m nmg_game_dev.finalize run-job <job_dir>        (internal: the background job body)

Exit codes: 0 success; 1 a step failed (``ERROR [code] message`` and ``Remediation:`` on stderr);
2 a prerequisite is missing (Blender or an MCP endpoint is unreachable).  The command blocks until
its job is terminal.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final, TextIO

from pydantic import ValidationError

from nmg_game_dev.pipeline import jobs
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.steps import STEP_ORDER

from .service import (
    FinalizeService,
    MissingArgumentError,
    build_request,
    error_dict,
    is_prerequisite,
)

STEP_COMMANDS: Final = ("all", *STEP_ORDER)
EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_PREREQUISITE: Final = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nmg_game_dev.finalize",
        description="Finalize an authored Blender asset into Desktop and Mobile Unreal content.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    for name in STEP_COMMANDS:
        step = commands.add_parser(name, help=_STEP_HELP.get(name, "Run every step (default)."))
        _add_asset_arguments(step)
    run_job = commands.add_parser(
        "run-job", help="Internal: run a job directory in the background."
    )
    run_job.add_argument("job_dir", type=Path)
    return parser


_STEP_HELP: Final = {
    "validate": "Run the contract validation.",
    "bake": "Bake the authored materials.",
    "variants": "Build the Desktop and Mobile variants.",
    "export": "Export the FBX variants and the sidecar.",
    "reimport": "Re-import the exported variants and check them.",
    "import_ue": "Import the variants into Unreal and finish the materials.",
}


def _add_asset_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--collection", required=True, help="Blender collection, e.g. Crate.")
    parser.add_argument(
        "--category",
        help="Content category, e.g. Props. Defaults to the design backlog entry's category.",
    )
    parser.add_argument(
        "--class",
        dest="asset_class",
        help="small_prop, standard_prop, hero_prop, character, or environment_piece. Defaults to "
        "the design backlog entry's asset_class.",
    )
    parser.add_argument("--export-root", required=True, help="Directory for the exported variants.")
    parser.add_argument("--blend", help="Finalize this saved .blend instead of the open session.")
    parser.add_argument("--budgets", help="Budget overrides file. Defaults to nmg-budgets.json.")
    parser.add_argument("--device", choices=("GPU", "CPU"), default="GPU", help="Bake device.")
    parser.add_argument(
        "--force", action="store_true", help="Rerun every step, ignoring the cache."
    )
    parser.add_argument("--json", action="store_true", help="Print the result as JSON on stdout.")


def main(
    argv: Sequence[str] | None = None,
    *,
    service: FinalizeService | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the command and return its exit code."""
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    args = build_parser().parse_args(argv)

    if args.command == "run-job":
        status = jobs.run_job(Path(args.job_dir))
        return EXIT_OK if status.get("state") == "succeeded" else EXIT_FAILED

    steps = STEP_ORDER if args.command == "all" else (args.command,)
    try:
        request = build_request(
            collection=args.collection,
            category=args.category,
            asset_class=args.asset_class,
            export_root=args.export_root,
            blend=args.blend,
            budgets_path=args.budgets,
            device=args.device,
        )
    except MissingArgumentError as error:
        return _report_error(error.payload(), args.json, out, err)
    except ValidationError as error:
        return _report_error(
            {
                "code": "finalize.invalid_request",
                "message": f"The finalize arguments are invalid: {error.errors()[0]['msg']}",
                "remediation": "Check --collection and --category (PascalCase), --class, and "
                "--export-root.",
                "stage": "finalize",
            },
            args.json,
            out,
            err,
        )

    active = service if service is not None else FinalizeService()
    try:
        status = active.run(request, steps, force=args.force)
    except PipelineError as error:
        return _report_error(error_dict(error), args.json, out, err)

    if status.get("state") == "succeeded":
        _print_success(status, args.json, out)
        return EXIT_OK
    error_payload: dict[str, Any] = status.get("error") or {
        "code": "finalize.failed",
        "message": "The finalize job failed without an error description",
        "remediation": "Read the job's status.json and blender-*.log files.",
        "stage": "finalize",
    }
    return _report_error(error_payload, args.json, out, err)


def _print_success(status: dict[str, Any], as_json: bool, out: TextIO) -> None:
    result = status.get("result") or {}
    if as_json:
        out.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return
    for step in result.get("steps", []):
        source = "cache" if step.get("cache_hit") else "ran"
        out.write(f"{step.get('step')}: {step.get('summary', '')} ({source})\n")
    if result.get("desktop_content_path"):
        out.write(f"Desktop: {result['desktop_content_path']}\n")
        out.write(f"Mobile: {result['mobile_content_path']}\n")


def _report_error(
    error: dict[str, Any],
    as_json: bool,
    out: TextIO,
    err: TextIO,
) -> int:
    code = str(error.get("code", "finalize.failed"))
    err.write(f"ERROR [{code}] {error.get('message', '')}\n")
    err.write(f"Remediation: {error.get('remediation', '')}\n")
    if as_json:
        out.write(json.dumps({"error": error}, indent=2, sort_keys=True) + "\n")
    return EXIT_PREREQUISITE if is_prerequisite(code) else EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
