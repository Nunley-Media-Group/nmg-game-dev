"""Command line for the finalize pipeline (#69, #148, #149).

    python -m nmg_game_dev.finalize {all,validate,bake,variants,export,reimport,import_ue}
        (--collection N [--collection M ...] | --batch FILE)
        [--category C] [--class K] [--export-root R] [--blend B] [--budgets P]
        [--material-variants P] [--device GPU|CPU] [--force] [--fail-fast]
        [--wait [--wait-limit S]] [--pie wait|refuse] [--pie-wait-limit S] [--json]

    python -m nmg_game_dev.finalize material-variants --category C --collection N [--json]
        (lists the material variants Unreal holds for the asset, #148)

    python -m nmg_game_dev.finalize run-job <job_dir>        (internal: the background job body)

Several ``--collection`` values, or a ``--batch`` file of finalize requests, run as one batch: the
collections are finalized one at a time, in order, under one lock.  A ``--batch`` entry takes its
own keys, and the asset options given on the command line fill in any key an entry omits.

Exit codes: 0 success; 1 a step or a collection failed (``ERROR [code] message`` and
``Remediation:`` on stderr; a batch prints one line per collection); 2 a prerequisite is missing
(Blender or an MCP endpoint is unreachable) or the arguments are wrong.  The command blocks until
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
from nmg_game_dev.pipeline.request import DEFAULT_PIE_WAIT_SECONDS
from nmg_game_dev.pipeline.steps import STEP_ORDER
from nmg_game_dev.unreal.import_asset import UnrealPythonClient

from .mcp_tools import list_material_variants
from .service import (
    FinalizeService,
    MissingArgumentError,
    build_batch,
    build_request,
    error_dict,
    is_prerequisite,
)

STEP_COMMANDS: Final = ("all", *STEP_ORDER)
LIST_VARIANTS_COMMAND: Final = "material-variants"
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
    listing = commands.add_parser(
        LIST_VARIANTS_COMMAND,
        help="List the material variants Unreal holds for a finalized asset.",
    )
    listing.add_argument("--category", required=True, help="Content category, e.g. Props.")
    listing.add_argument("--collection", required=True, help="Asset name, e.g. Crate.")
    listing.add_argument("--json", action="store_true", help="Print the rows as JSON on stdout.")
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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--collection",
        action="append",
        help="Blender collection, e.g. Crate. Repeat to finalize several, in the order given.",
    )
    source.add_argument(
        "--batch",
        type=Path,
        metavar="FILE",
        help="JSON array of finalize requests (the finalize_asset keys), run in order.",
    )
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
    parser.add_argument(
        "--export-root",
        help="Directory for the exported variants. Required with --collection; a --batch entry "
        "may set its own.",
    )
    parser.add_argument("--blend", help="Finalize this saved .blend instead of the open session.")
    parser.add_argument("--budgets", help="Budget overrides file. Defaults to nmg-budgets.json.")
    parser.add_argument("--device", choices=("GPU", "CPU"), help="Bake device. Defaults to GPU.")
    parser.add_argument(
        "--material-variants",
        dest="material_variants",
        help="Material-variants declaration. Defaults to <collection>.material-variants.json "
        "beside --blend. One collection only; a --batch entry sets material_variants_path.",
    )
    parser.add_argument(
        "--force", action="store_true", help="Rerun every step, ignoring the cache."
    )
    parser.add_argument("--json", action="store_true", help="Print the result as JSON on stdout.")
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop a batch at the first failed collection; the rest are reported as skipped.",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for the finalize job lock instead of failing with finalize.job_running.",
    )
    parser.add_argument(
        "--wait-limit",
        type=float,
        metavar="SECONDS",
        help="With --wait, fail with finalize.job_running after this many seconds of waiting.",
    )
    parser.add_argument(
        "--pie",
        choices=("wait", "refuse"),
        default="wait",
        help="When the editor is in Play In Editor before an import: wait for it to end (default) "
        "or refuse at once.",
    )
    parser.add_argument(
        "--pie-wait-limit",
        type=float,
        default=DEFAULT_PIE_WAIT_SECONDS,
        metavar="SECONDS",
        help="With --pie wait, the longest wait for PIE to end (default 600).",
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    service: FinalizeService | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    unreal_client: UnrealPythonClient | None = None,
) -> int:
    """Run the command and return its exit code.

    ``unreal_client`` replaces the Unreal MCP connection for ``material-variants``, so tests can
    run the command without an editor.
    """
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run-job":
        status = jobs.run_job(Path(args.job_dir))
        return EXIT_OK if status.get("state") == "succeeded" else EXIT_FAILED

    if args.command == LIST_VARIANTS_COMMAND:
        return _list_variants(args, out, err, unreal_client)

    if args.collection is not None and args.export_root is None:
        parser.error("--export-root is required with --collection")
    if args.wait_limit is not None and not args.wait:
        parser.error("--wait-limit needs --wait")
    is_batch = args.batch is not None or len(args.collection) > 1
    if is_batch and args.material_variants is not None:
        parser.error(
            "--material-variants applies to one --collection; set material_variants_path in "
            "each --batch entry"
        )

    steps = STEP_ORDER if args.command == "all" else (args.command,)
    active = service if service is not None else FinalizeService()
    if is_batch:
        return _run_batch_command(args, steps, active, out, err)
    return _run_single_command(args, steps, active, out, err)


def _run_single_command(
    args: argparse.Namespace,
    steps: tuple[str, ...] | Sequence[str],
    active: FinalizeService,
    out: TextIO,
    err: TextIO,
) -> int:
    try:
        request = build_request(
            collection=args.collection[0],
            category=args.category,
            asset_class=args.asset_class,
            export_root=args.export_root,
            blend=args.blend,
            budgets_path=args.budgets,
            device=args.device or "GPU",
            pie_mode=args.pie,
            pie_wait_seconds=args.pie_wait_limit,
            material_variants_path=args.material_variants,
        )
    except MissingArgumentError as error:
        return _report_error(error.payload(), args.json, out, err)
    except PipelineError as error:
        return _report_error(error_dict(error), args.json, out, err)
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

    try:
        status = active.run(
            request,
            steps,
            force=args.force,
            wait_for_lock=args.wait,
            lock_wait_s=args.wait_limit,
        )
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


def _run_batch_command(
    args: argparse.Namespace,
    steps: tuple[str, ...] | Sequence[str],
    active: FinalizeService,
    out: TextIO,
    err: TextIO,
) -> int:
    defaults: dict[str, object] = {
        "category": args.category,
        "asset_class": args.asset_class,
        "export_root": args.export_root,
        "blend": args.blend,
        "budgets_path": args.budgets,
        "device": args.device,
        "pie_mode": args.pie,
        "pie_wait_seconds": args.pie_wait_limit,
    }
    try:
        entries = (
            [{"collection": name} for name in args.collection]
            if args.batch is None
            else _load_batch_file(args.batch)
        )
        requests = build_batch(entries, defaults=defaults)
        status = active.run_batch(
            requests,
            steps,
            force=args.force,
            fail_fast=args.fail_fast,
            wait_for_lock=args.wait,
            lock_wait_s=args.wait_limit,
        )
    except PipelineError as error:
        return _report_error(error_dict(error), args.json, out, err)

    batch = (status.get("result") or {}).get("batch")
    if batch is None:
        error_payload: dict[str, Any] = status.get("error") or {
            "code": "finalize.failed",
            "message": "The batch failed without an error description",
            "remediation": "Read the job's status.json and blender-*.log files.",
            "stage": "finalize",
        }
        return _report_error(error_payload, args.json, out, err)
    _print_batch(batch, args.json, out)
    return EXIT_OK if status.get("state") == "succeeded" else EXIT_FAILED


def _load_batch_file(path: Path) -> list[object]:
    """Read a ``--batch`` file: a JSON array of request objects."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise PipelineError(
            code="finalize.invalid_batch",
            message=f"The batch file {path} cannot be read: {error}",
            remediation="Pass the path of a JSON file holding an array of finalize requests.",
            stage="finalize",
        ) from error
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as error:
        raise PipelineError(
            code="finalize.invalid_batch",
            message=f"The batch file {path} is not valid JSON: {error}",
            remediation="Fix the JSON syntax, then rerun the batch.",
            stage="finalize",
        ) from error
    if not isinstance(data, list):
        raise PipelineError(
            code="finalize.invalid_batch",
            message=f"The batch file {path} must hold a JSON array of finalize requests",
            remediation="Wrap the requests in a JSON array.",
            stage="finalize",
        )
    return list(data)


def _list_variants(
    args: argparse.Namespace,
    out: TextIO,
    err: TextIO,
    unreal_client: UnrealPythonClient | None,
) -> int:
    rows = list_material_variants(
        category=args.category,
        collection=args.collection,
        client=unreal_client,
    )
    if isinstance(rows, dict):
        return _report_error(rows["error"], args.json, out, err)
    if args.json:
        out.write(json.dumps(rows, indent=2, sort_keys=True) + "\n")
        return EXIT_OK
    if not rows:
        out.write(f"{args.collection} has no material variants in Unreal.\n")
    for row in rows:
        out.write(
            f"{row['name']}  {row['material']}  Desktop: {row['desktop'] or '-'}  "
            f"Mobile: {row['mobile'] or '-'}\n"
        )
    return EXIT_OK


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


def _print_batch(batch: dict[str, Any], as_json: bool, out: TextIO) -> None:
    if as_json:
        out.write(json.dumps({"batch": batch}, indent=2, sort_keys=True) + "\n")
        return
    for item in batch.get("items", []):
        out.write(f"{item.get('collection')}: {item.get('state')}\n")
        error = item.get("error")
        if isinstance(error, dict):
            out.write(f"  [{error.get('code')}] {error.get('message')} ({error.get('stage')})\n")
    out.write(
        f"Batch: {batch.get('succeeded', 0)} succeeded, {batch.get('failed', 0)} failed, "
        f"{batch.get('skipped', 0)} skipped\n"
    )


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
