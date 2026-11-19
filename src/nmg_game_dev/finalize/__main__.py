"""Command line for the finalize pipeline (#69, #148, #149).

    python -m nmg_game_dev.finalize {all,validate,bake,variants,export,export_anims,reimport,
        import_godot,import_anims}
        (--collection N [--collection M ...] | --batch FILE)
        [--category C] [--class K] [--export-root R] [--blend B] [--budgets P]
        [--material-variants P] [--device GPU|CPU] [--compatible-with C/N ...] [--force]
        [--fail-fast] [--wait [--wait-limit S]] [--json]

    python -m nmg_game_dev.finalize reduce --collection N --class C [--blend B] [--budgets P]
        [--device GPU|CPU] [--cage M] [--ray M] [--miss-threshold X] [--parts JSON] [--wait S]

    python -m nmg_game_dev.finalize material-variants --category C --collection N
        [--export-root R] [--json]
        (lists the asset's material variants from the files finalize wrote, #148)

    python -m nmg_game_dev.finalize check --category C --collection N [--export-root R] [--json]
        (is the asset up to date from its finalize record? exit 0 yes, 1 no, 2 invalid, #247)

    python -m nmg_game_dev.finalize run-job <job_dir>        (internal: the background job body)

Several ``--collection`` values, or a ``--batch`` file of finalize requests, run as one batch: the
collections are finalized one at a time, in order, under one lock.  A ``--batch`` entry takes its
own keys, and the asset options given on the command line fill in any key an entry omits.
``--material-variants`` and ``--compatible-with`` apply to one collection only.  ``--export-root``
defaults to ``<project>/game/assets`` (the project is ``CLAUDE_PROJECT_DIR`` or the working
directory).
``--skip-up-to-date`` (a batch only, #247) finalizes nothing that ``check`` already reports up to
date; those items are counted as ``up_to_date``.

Exit codes: 0 success; 1 a step or a collection failed (``ERROR [code] message`` and
``Remediation:`` on stderr; a batch prints one line per collection); 2 a prerequisite is missing
(Blender, the Blender MCP, Godot, or the Godot project is missing) or the arguments are wrong.
The command blocks until its job is terminal.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final, TextIO

from pydantic import ValidationError

from nmg_game_dev.pipeline import jobs, records
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.reduce import parts_from_json
from nmg_game_dev.pipeline.steps import STEP_ORDER

from .mcp_tools import list_material_variants
from .service import (
    FinalizeService,
    MissingArgumentError,
    build_batch,
    build_reduce_request,
    build_request,
    default_export_root,
    error_dict,
    is_prerequisite,
    skip_needs_batch_error,
)

STEP_COMMANDS: Final = ("all", *STEP_ORDER)
LIST_VARIANTS_COMMAND: Final = "material-variants"
CHECK_COMMAND: Final = "check"
EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_PREREQUISITE: Final = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nmg_game_dev.finalize",
        description="Finalize an authored Blender asset into Desktop and Mobile Godot resources.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    for name in STEP_COMMANDS:
        step = commands.add_parser(name, help=_STEP_HELP.get(name, "Run every step (default)."))
        _add_asset_arguments(step)
    reduce = commands.add_parser(
        "reduce", help="Reduce an over-budget generated asset to its Desktop budget (#139)."
    )
    _add_reduce_arguments(reduce)

    listing = commands.add_parser(
        LIST_VARIANTS_COMMAND,
        help="List a finalized asset's material variants from the files finalize wrote.",
    )
    listing.add_argument("--category", required=True, help="Asset category, e.g. Props.")
    listing.add_argument("--collection", required=True, help="Asset name, e.g. Crate.")
    listing.add_argument(
        "--export-root", help="The finalize export root. Defaults to <project>/game/assets."
    )
    listing.add_argument("--json", action="store_true", help="Print the rows as JSON on stdout.")
    check = commands.add_parser(
        CHECK_COMMAND,
        help="Say whether an asset is up to date, from its finalize record (no Blender or Godot).",
    )
    check.add_argument("--category", required=True, help="Asset category, e.g. Props.")
    check.add_argument("--collection", required=True, help="Asset name, e.g. Crate.")
    check.add_argument(
        "--export-root", help="The finalize export root. Defaults to <project>/game/assets."
    )
    check.add_argument("--json", action="store_true", help="Print the check as JSON on stdout.")
    run_job = commands.add_parser(
        "run-job", help="Internal: run a job directory in the background."
    )
    run_job.add_argument("job_dir", type=Path)
    return parser


def _add_reduce_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--collection", required=True, help="Blender collection, e.g. Crate.")
    parser.add_argument(
        "--class",
        dest="asset_class",
        required=True,
        help="Contract class whose Desktop budget applies: small_prop, standard_prop, hero_prop, "
        "character, or environment_piece.",
    )
    parser.add_argument("--blend", help="Reduce this saved .blend instead of the open session.")
    parser.add_argument("--budgets", help="Budget overrides file. Defaults to nmg-budgets.json.")
    parser.add_argument("--device", choices=("GPU", "CPU"), default="GPU", help="Bake device.")
    parser.add_argument("--cage", type=float, help="Cage extrusion in metres (default 0.03).")
    parser.add_argument("--ray", type=float, help="Max ray distance in metres (default 0.10).")
    parser.add_argument(
        "--miss-threshold", type=float, help="Largest unbaked share per part (default 0.01)."
    )
    parser.add_argument(
        "--parts",
        help="Per-part overrides: a JSON object keyed by part name, e.g. Wall with share 0.4.",
    )
    parser.add_argument(
        "--wait",
        type=float,
        help="Seconds to wait for the job before printing its status. Default: until it finishes.",
    )


_STEP_HELP: Final = {
    "validate": "Run the contract validation.",
    "bake": "Bake the authored materials.",
    "variants": "Build the Desktop and Mobile variants.",
    "export": "Export the .glb variants and the sidecars.",
    "export_anims": "Export one animation .glb per clip on the rig.",
    "reimport": "Re-import the exported variants and check them.",
    "import_godot": "Import the variants into the Godot project headless and verify them.",
    "import_anims": "Import the clips as Godot animation libraries and verify them.",
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
        help="Asset category, e.g. Props. Defaults to the design backlog entry's category.",
    )
    parser.add_argument(
        "--class",
        dest="asset_class",
        help="small_prop, standard_prop, hero_prop, character, environment_piece, or terrain. "
        "Defaults to the design backlog entry's asset_class.",
    )
    parser.add_argument(
        "--export-root",
        help="Directory for the exported variants, inside the Godot project. Defaults to "
        "<project>/game/assets; a --batch entry may set its own.",
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
        "--compatible-with",
        action="append",
        default=[],
        metavar="CATEGORY/NAME",
        help="Another character whose Desktop skeleton this character's clips may play on. "
        "Repeat for each. import_anims checks every animated bone exists in its skeleton.",
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
        "--skip-up-to-date",
        action="store_true",
        help="In a batch, skip each collection that its finalize record shows up to date (#247). "
        "A single collection is refused.",
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
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run-job":
        status = jobs.run_job(Path(args.job_dir))
        return EXIT_OK if status.get("state") == "succeeded" else EXIT_FAILED

    if args.command == "reduce":
        return _run_reduce(args, service, out, err)
    if args.command == LIST_VARIANTS_COMMAND:
        return _list_variants(args, out, err)
    if args.command == CHECK_COMMAND:
        return _check(args, out, err)

    if args.wait_limit is not None and not args.wait:
        parser.error("--wait-limit needs --wait")
    is_batch = args.batch is not None or len(args.collection) > 1
    if args.skip_up_to_date and not is_batch:
        return _report_error(skip_needs_batch_error(), args.json, out, err)
    if is_batch and args.material_variants is not None:
        parser.error(
            "--material-variants applies to one --collection; set material_variants_path in "
            "each --batch entry"
        )
    if is_batch and args.compatible_with:
        parser.error(
            "--compatible-with applies to one --collection; set compatible_with in each --batch "
            "entry"
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
            compatible_with=args.compatible_with,
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
            skip_up_to_date=args.skip_up_to_date,
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


def _run_reduce(
    args: argparse.Namespace,
    service: FinalizeService | None,
    out: TextIO,
    err: TextIO,
) -> int:
    """Run the reduce job and print its status JSON, the same shape the MCP tool returns (#139)."""
    try:
        request = build_reduce_request(
            collection=args.collection,
            asset_class=args.asset_class,
            blend=args.blend,
            budgets_path=args.budgets,
            device=args.device,
            cage_extrusion=args.cage,
            max_ray_distance=args.ray,
            miss_threshold=args.miss_threshold,
            parts=parts_from_json(args.parts),
        )
    except PipelineError as error:
        return _report_error(error_dict(error), False, out, err)

    active = service if service is not None else FinalizeService()
    timeout = args.wait if args.wait is not None else float("inf")
    try:
        job_id = active.start_reduce(request)
        status = active.wait(job_id, timeout_s=timeout)
    except PipelineError as error:
        return _report_error(error_dict(error), False, out, err)

    out.write(json.dumps({"job_id": job_id, **status}, indent=2, sort_keys=True, default=str))
    out.write("\n")
    if status.get("state") != "failed":
        # Succeeded, or still running when --wait ran out; the job id in the output can be polled.
        return EXIT_OK
    error_payload: dict[str, Any] = status.get("error") or {
        "code": "reduce.failed",
        "message": "The reduce job failed without an error description",
        "remediation": "Read the job's status.json and blender-reduce.log files.",
        "stage": "reduce",
    }
    return _report_error(error_payload, False, out, err)


def _check(args: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    """Print whether an asset is up to date from its record (#247 AC5).

    Exit 0 when up to date, 1 when not, and 2 for invalid arguments.
    """
    if not records.valid_asset_names(args.category, args.collection):
        err.write(
            "ERROR [finalize.invalid_request] --category and --collection must be PascalCase\n"
        )
        err.write("Remediation: Pass the Props-style category and the Crate-style collection.\n")
        return EXIT_PREREQUISITE
    export_root = Path(args.export_root) if args.export_root else default_export_root()
    check = records.check(args.category, args.collection, export_root)
    name = f"{args.category}/{args.collection}"
    if args.json:
        payload = {
            "category": args.category,
            "collection": args.collection,
            "up_to_date": check.up_to_date,
            "reason": check.reason,
            "record": check.record,
        }
        out.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    elif check.up_to_date:
        out.write(f"{name}: up to date\n")
    else:
        out.write(f"{name}: not up to date ({check.reason})\n")
    return EXIT_OK if check.up_to_date else EXIT_FAILED


def _list_variants(args: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    rows = list_material_variants(
        category=args.category,
        collection=args.collection,
        export_root=args.export_root,
    )
    if isinstance(rows, dict):
        return _report_error(rows["error"], args.json, out, err)
    if args.json:
        out.write(json.dumps(rows, indent=2, sort_keys=True) + "\n")
        return EXIT_OK
    if not rows:
        out.write(f"{args.collection} has no material variants.\n")
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
    if result.get("desktop_resource_path"):
        out.write(f"Desktop: {result['desktop_resource_path']}\n")
        out.write(f"Mobile: {result['mobile_resource_path']}\n")


def _print_batch(batch: dict[str, Any], as_json: bool, out: TextIO) -> None:
    if as_json:
        out.write(json.dumps({"batch": batch}, indent=2, sort_keys=True) + "\n")
        return
    for item in batch.get("items", []):
        out.write(f"{item.get('collection')}: {item.get('state')}\n")
        error = item.get("error")
        if isinstance(error, dict):
            out.write(f"  [{error.get('code')}] {error.get('message')} ({error.get('stage')})\n")
    up_to_date = f", {batch['up_to_date']} up to date" if batch.get("up_to_date") else ""
    out.write(
        f"Batch: {batch.get('succeeded', 0)} succeeded, {batch.get('failed', 0)} failed, "
        f"{batch.get('skipped', 0)} skipped{up_to_date}\n"
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
