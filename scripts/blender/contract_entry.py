"""Headless entry for contract_core, run by the host CLI and by run_isolated.

    blender --background [--factory-startup] --python scripts/blender/contract_entry.py -- \\
        validate --blend B --collection N --class C --report R [--budgets P]
    blender --background --factory-startup --python scripts/blender/contract_entry.py -- \\
        reimport --variant-dir D --pre-report R --report OUT
    blender --background --python scripts/blender/contract_entry.py -- \\
        render --blend B --collection N --out O --report R \\
        [--proof-variant-dir D] [--pre-bake P] [--resolution N]

The add-on package is loaded from its source directory, so the check needs no installed add-on.
Each command writes its JSON report to --report. A ContractError exits 2 with the remediation
on stderr; a failing report still exits 0 here, and the host CLI turns it into exit 1.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADDON_DIR = _REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon"
_PACKAGE = "nmg_game_dev_blender_addon"


def _load_contract_core() -> Any:
    spec = importlib.util.spec_from_file_location(
        _PACKAGE,
        _ADDON_DIR / "__init__.py",
        submodule_search_locations=[str(_ADDON_DIR)],
    )
    if spec is None or spec.loader is None:
        raise SystemExit(f"contract_entry: cannot load the add-on package at {_ADDON_DIR}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PACKAGE] = module
    spec.loader.exec_module(module)
    return importlib.import_module(f"{_PACKAGE}.contract_core")


def _parse(argv: list[str]) -> argparse.Namespace:
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser(prog="contract_entry")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("--blend")
    validate.add_argument("--collection", required=True)
    validate.add_argument("--class", dest="asset_class", required=True)
    validate.add_argument("--budgets")
    validate.add_argument("--report", required=True)

    reimport = commands.add_parser("reimport")
    reimport.add_argument("--variant-dir", required=True)
    reimport.add_argument("--pre-report", required=True)
    reimport.add_argument("--report", required=True)

    render = commands.add_parser("render")
    render.add_argument("--blend")
    render.add_argument("--collection", required=True)
    render.add_argument("--out", required=True)
    render.add_argument("--proof-variant-dir")
    render.add_argument("--pre-bake")
    render.add_argument("--resolution", type=int, default=1024)
    render.add_argument("--report", required=True)
    return parser.parse_args(argv)


def main() -> None:
    import bpy  # noqa: PLC0415 - only available inside Blender

    args = _parse(sys.argv)
    core = _load_contract_core()
    try:
        if args.command == "reimport":
            bpy.ops.wm.read_factory_settings(use_empty=True)
            report = core.reimport_check(args.variant_dir, args.pre_report)
        else:
            if args.blend:
                bpy.ops.wm.open_mainfile(filepath=args.blend)
            if args.command == "validate":
                report = core.validate_asset(args.collection, args.asset_class, args.budgets)
            else:
                report = core.render_review(args.collection, args.out, args.resolution)
                if args.proof_variant_dir:
                    proof = core.render_texture_proof(
                        args.proof_variant_dir,
                        args.out,
                        pre_bake=args.pre_bake,
                        collection=args.collection,
                        resolution=args.resolution,
                    )
                    report["proof"] = proof["proof"]
    except core.ContractError as error:
        print(f"contract_entry: {error}", file=sys.stderr)
        sys.exit(2)

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sys.exit(0)


if __name__ == "__main__":
    main()
