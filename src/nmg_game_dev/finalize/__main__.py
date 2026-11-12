"""Command line for the finalize pipeline (#69).

    python -m nmg_game_dev.finalize {all,validate,bake,variants,export,export_anims,reimport,
        import_ue,import_anims}
        --collection N --category C --class K --export-root R
        [--blend B] [--budgets P] [--device GPU|CPU] [--compatible-with C/N ...]
        [--force] [--json]

    python -m nmg_game_dev.finalize reduce --collection N --class C [--blend B] [--budgets P]
        [--device GPU|CPU] [--cage M] [--ray M] [--miss-threshold X] [--parts JSON] [--wait S]

    python -m nmg_game_dev.finalize material-variants --category C --collection N [--json]
        (lists the material variants Unreal holds for the asset, #148)

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
from nmg_game_dev.pipeline.reduce import parts_from_json
from nmg_game_dev.pipeline.steps import STEP_ORDER
from nmg_game_dev.unreal.import_asset import UnrealPythonClient

from .mcp_tools import list_material_variants
from .service import (
    FinalizeService,
    MissingArgumentError,
    build_reduce_request,
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
    reduce = commands.add_parser(
        "reduce", help="Reduce an over-budget generated asset to its Desktop budget (#139)."
    )
    _add_reduce_arguments(reduce)

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
    "export": "Export the FBX variants and the sidecar.",
    "export_anims": "Export one animation FBX per clip on the rig.",
    "reimport": "Re-import the exported variants and check them.",
    "import_ue": "Import the variants into Unreal and finish the materials.",
    "import_anims": "Import the clips as AnimSequences on the Desktop skeleton.",
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
    parser.add_argument(
        "--material-variants",
        dest="material_variants",
        help="Material-variants declaration. Defaults to <collection>.material-variants.json "
        "beside --blend.",
    )
    parser.add_argument("--device", choices=("GPU", "CPU"), default="GPU", help="Bake device.")
    parser.add_argument(
        "--compatible-with",
        action="append",
        default=[],
        metavar="CATEGORY/NAME",
        help="Another character whose Desktop skeleton this character's clips may play on. "
        "Repeat for each. import_anims registers both directions.",
    )
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
    unreal_client: UnrealPythonClient | None = None,
) -> int:
    """Run the command and return its exit code.

    ``unreal_client`` replaces the Unreal MCP connection for ``material-variants``, so tests can
    run the command without an editor.
    """
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    args = build_parser().parse_args(argv)

    if args.command == "run-job":
        status = jobs.run_job(Path(args.job_dir))
        return EXIT_OK if status.get("state") == "succeeded" else EXIT_FAILED

    if args.command == "reduce":
        return _run_reduce(args, service, out, err)
    if args.command == LIST_VARIANTS_COMMAND:
        return _list_variants(args, out, err, unreal_client)

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
