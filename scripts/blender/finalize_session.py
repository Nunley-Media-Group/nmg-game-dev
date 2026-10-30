"""Live-session operations for finalize: checkpoint the open scene and load a result back into it.

The host sets two globals and then exec's this file through the Blender MCP execute_code tool:

    NMG_OP = "checkpoint" | "load_back"
    NMG_PAYLOAD = {"addon_dir": <repo>/plugins/nmg-game-dev-blender-addon, ...}

    checkpoint: {"collection": N, "path": P}   saves a copy of the scene to P, returns the hash
    load_back:  {"result_blend": P, "collection": N, "expected_hash": H}

Each run prints exactly one line, NMG_RESULT <json>. Failures come back as
{"ok": false, "error": {"code", "message", "remediation"}} and never raise into the session.
The add-on package is loaded by file path, as scripts/blender/contract_entry.py does, unless it is
already imported. Nothing is registered, and the scene changes only in load_back.
"""

import importlib
import importlib.util
import json
import sys
from pathlib import Path

import bpy

_PACKAGE = "nmg_game_dev_blender_addon"


def _session_core(addon_dir):
    if _PACKAGE not in sys.modules:
        init = Path(addon_dir) / "__init__.py"
        spec = importlib.util.spec_from_file_location(
            _PACKAGE, init, submodule_search_locations=[str(addon_dir)]
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[_PACKAGE] = module
        spec.loader.exec_module(module)
    return importlib.import_module(f"{_PACKAGE}.finalize_core")


def _checkpoint(payload):
    core = _session_core(payload["addon_dir"])
    collection = payload["collection"]
    if bpy.data.collections.get(collection) is None:
        return {
            "ok": False,
            "error": {
                "code": "finalize.collection_not_found",
                "message": f"No collection named {collection!r} is in the open file.",
                "remediation": "Open the file that holds the asset, or set collection to its name.",
            },
        }
    digest = core.content_hash(collection)
    bpy.ops.wm.save_as_mainfile(filepath=payload["path"], copy=True)
    return {"ok": True, "hash": digest, "path": payload["path"]}


def _load_back(payload):
    core = _session_core(payload["addon_dir"])
    try:
        result = core.load_back(
            payload["result_blend"], payload["collection"], payload["expected_hash"]
        )
    except core.LoadBackError as error:
        return {
            "ok": False,
            "error": {
                "code": error.code,
                "message": error.message,
                "remediation": error.remediation,
            },
        }
    return {"ok": True, **result}


def _dispatch(op, payload):
    if op == "checkpoint":
        return _checkpoint(payload)
    if op == "load_back":
        return _load_back(payload)
    return {
        "ok": False,
        "error": {
            "code": "finalize.session_unknown_op",
            "message": f"Unknown session operation {op!r}.",
            "remediation": "Use checkpoint or load_back.",
        },
    }


try:
    _nmg_result = _dispatch(NMG_OP, NMG_PAYLOAD)  # noqa: F821 - set by the host before exec
except Exception as _error:  # noqa: BLE001 - report every failure as a result line
    _nmg_result = {
        "ok": False,
        "error": {
            "code": "finalize.session_failed",
            "message": str(_error),
            "remediation": "Check the Blender console for the traceback, then rerun finalize.",
        },
    }

print("NMG_RESULT " + json.dumps(_nmg_result, sort_keys=True, default=str), flush=True)
