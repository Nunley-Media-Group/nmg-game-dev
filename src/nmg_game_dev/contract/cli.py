"""Command-line entry for the contract checks: validate, reimport, and render.

Each subcommand runs ``scripts/blender/contract_entry.py`` headless and maps the outcome to an
exit code: 0 for a passing report or written render output, 1 for a failing report, and 2 when
Blender cannot be found or does not write its report.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.quality.contract import load_report

from .blender import resolve_blender, run_blender, stderr_tail

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_ERROR = 2
RENDER_REPORT_NAME = "render-report.json"


def main(argv: Sequence[str] | None = None) -> int:
    """Run one subcommand and return its exit code."""
    args = _parser().parse_args(argv)
    try:
        blender = resolve_blender()
        if args.command == "render":
            return _render(blender, args)
        return _check(blender, args)
    except PipelineError as error:
        print(f"contract: error [{error.code}] {error.message}", file=sys.stderr)
        print(f"remediation: {error.remediation}", file=sys.stderr)
        return EXIT_ERROR


def _check(blender: Path, args: argparse.Namespace) -> int:
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    if args.command == "validate":
        entry_args = ["--blend", args.blend, "--collection", args.collection]
        entry_args += ["--class", args.asset_class]
        if args.budgets:
            entry_args += ["--budgets", args.budgets]
        factory_startup = False
    else:
        entry_args = ["--variant-dir", args.variant_dir, "--pre-report", args.pre_report]
        factory_startup = True
    entry_args += ["--report", str(report)]

    _execute(blender, args.command, entry_args, report, factory_startup=factory_startup)
    result = load_report(report)
    if result.passed:
        print("contract: PASS")
        return EXIT_PASS

    rules = ", ".join(finding.rule for finding in result.findings)
    print(f"contract: FAIL ({len(result.findings)} findings): {rules}")
    for finding in result.findings:
        print(
            f"  {finding.rule} {finding.target}: {finding.message} Remediation: "
            f"{finding.remediation}",
            file=sys.stderr,
        )
    return EXIT_FAIL


def _render(blender: Path, args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = out / RENDER_REPORT_NAME
    entry_args = ["--blend", args.blend, "--collection", args.collection, "--out", str(out)]
    entry_args += ["--resolution", str(args.resolution)]
    if args.proof_variant_dir:
        entry_args += ["--proof-variant-dir", args.proof_variant_dir]
    if args.pre_bake:
        entry_args += ["--pre-bake", args.pre_bake]
    entry_args += ["--report", str(report)]

    _execute(blender, "render", entry_args, report, factory_startup=False)
    written = _rendered_count(report)
    print(f"render: wrote {written} file(s) to {out}")
    return EXIT_PASS


def _execute(
    blender: Path,
    subcommand: str,
    entry_args: list[str],
    report: Path,
    *,
    factory_startup: bool,
) -> None:
    """Run Blender and raise ``contract.no_report`` unless it wrote the report file.

    A stale report from an earlier run is removed first, so it cannot stand in for this run.
    """
    report.unlink(missing_ok=True)
    result = run_blender(blender, subcommand, entry_args, factory_startup=factory_startup)
    if report.is_file():
        return
    raise PipelineError(
        code="contract.no_report",
        message=f"Blender exited with code {result.returncode} without writing {report}. "
        f"Last output:\n{stderr_tail(result)}",
        remediation="Fix the input named in the Blender output above, then rerun. Open the .blend "
        "in Blender to confirm it loads.",
        stage="contract",
    )


def _rendered_count(report: Path) -> int:
    try:
        data: Any = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PipelineError(
            code="contract.report_unreadable",
            message=f"Render report is missing or malformed: {report} ({error})",
            remediation="Rerun the render so it writes a valid render report, then retry.",
            stage="contract",
        ) from error
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list):
        raise PipelineError(
            code="contract.report_unreadable",
            message=f"Render report has no 'files' list: {report}",
            remediation="Rerun the render; the render report must list the files it wrote.",
            stage="contract",
        )
    return len(files)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nmg_game_dev.contract",
        description="Run the contract validator, re-import check, and review renders in "
        "headless Blender.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate one asset collection")
    validate.add_argument("--blend", required=True, help="the .blend file to open")
    validate.add_argument("--collection", required=True, help="asset collection <Name>")
    validate.add_argument("--class", dest="asset_class", required=True, help="asset class")
    validate.add_argument("--report", required=True, help="where to write the JSON report")
    validate.add_argument("--budgets", default=None, help="optional nmg-budgets.json")

    reimport = commands.add_parser("reimport", help="re-import an exported variant folder")
    reimport.add_argument("--variant-dir", required=True, help="folder with SM_<Name>.fbx")
    reimport.add_argument("--pre-report", required=True, help="validation report before export")
    reimport.add_argument("--report", required=True, help="where to write the JSON report")

    render = commands.add_parser("render", help="write review renders and the texture proof")
    render.add_argument("--blend", required=True, help="the .blend file to open")
    render.add_argument("--collection", required=True, help="asset collection <Name>")
    render.add_argument("--out", required=True, help="output folder")
    render.add_argument("--proof-variant-dir", default=None, help="variant folder to proof")
    render.add_argument("--pre-bake", default=None, help="optional pre-bake render image")
    render.add_argument("--resolution", type=int, default=1024, help="render size in pixels")
    return parser
