"""Headless entry for finalize_core: one finalize step, or the content hash of a saved file.

    blender --background <in.blend> --python scripts/blender/finalize_entry.py -- \\
        <validate|bake|variants|export> --job-dir D [--inputs PATH]
    blender --background --factory-startup --python scripts/blender/finalize_entry.py -- \\
        reimport --job-dir D [--inputs PATH]
    blender --background <in.blend> --python scripts/blender/finalize_entry.py -- \\
        hash --job-dir D

D holds request.json (written by the host). A step writes its envelope to D/<step>.json and
prints NMG_PROGRESS lines on stdout; hash writes D/hash.json. Exit 0 when the step succeeded,
1 when it failed (the envelope is still written), and 2 for an unexpected error after a
best-effort envelope. The add-on is loaded from its source directory, as contract_entry.py does,
and nothing is registered.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADDON_DIR = _REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon"
_PACKAGE = "nmg_game_dev_blender_addon"
_STEPS = ("validate", "bake", "variants", "export", "reimport")
_REMEDIATION = "Check the Blender log for the traceback, fix the cause, and rerun."


def _load_core() -> Any:
    spec = importlib.util.spec_from_file_location(
        _PACKAGE,
        _ADDON_DIR / "__init__.py",
        submodule_search_locations=[str(_ADDON_DIR)],
    )
    if spec is None or spec.loader is None:
        raise SystemExit(f"finalize_entry: cannot load the add-on package at {_ADDON_DIR}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PACKAGE] = module
    spec.loader.exec_module(module)
    return importlib.import_module(f"{_PACKAGE}.finalize_core")


def _parse(argv: list[str]) -> argparse.Namespace:
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser(prog="finalize_entry")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in (*_STEPS, "hash"):
        command = commands.add_parser(name)
        command.add_argument("--job-dir", required=True)
        command.add_argument("--inputs")
    return parser.parse_args(argv)


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", "utf-8")
    os.replace(tmp, path)


def _hash(core: Any, request: dict[str, Any], out: Path) -> bool:
    import bpy  # noqa: PLC0415 - only available inside Blender

    collection = str(request["collection"])
    if bpy.data.collections.get(collection) is None:
        payload: dict[str, Any] = {
            "ok": False,
            "hash": None,
            "error": {
                "code": "finalize.collection_not_found",
                "message": f"No collection named {collection!r} is in the open file.",
                "remediation": "Open the file that holds the asset, or set collection to its name.",
            },
        }
    else:
        payload = {"ok": True, "hash": core.content_hash(collection), "error": None}
    _write_json(out / "hash.json", payload)
    return bool(payload["ok"])


def main() -> None:
    args = _parse(sys.argv)
    job = Path(args.job_dir)
    out_name = "hash.json" if args.command == "hash" else f"{args.command}.json"
    try:
        job.mkdir(parents=True, exist_ok=True)
        core = _load_core()
        request: dict[str, Any] = json.loads((job / "request.json").read_text(encoding="utf-8"))
        if args.command == "hash":
            sys.exit(0 if _hash(core, request, job) else 1)
        inputs: dict[str, Any] | None = None
        if args.inputs:
            inputs = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
        envelope = core.run_step(args.command, request, job, inputs)
    except Exception as error:  # noqa: BLE001 - every failure must leave an envelope behind
        traceback.print_exc(file=sys.stderr)
        envelope = {
            "schemaVersion": 1,
            "step": args.command,
            "ok": False,
            "summary": f"unexpected error: {error}",
            "outputs": {},
            "error": {
                "code": f"{args.command}.internal_error",
                "message": str(error),
                "remediation": _REMEDIATION,
            },
        }
        _write_json(job / out_name, envelope)
        sys.exit(2)
    _write_json(job / out_name, envelope)
    sys.exit(0 if envelope["ok"] else 1)


if __name__ == "__main__":
    main()
