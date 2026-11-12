"""The reduce job body: run reduce_asset in background Blender and write its envelope (#139).

finalize_entry.py calls run_reduce with the job's request.json and the job directory. Blender has
already opened the checkpoint, so the scene here is the session's copy. The result is written to
<job>/reduce.blend and returned in an envelope the host reads as <job>/reduce.json:

    {"schemaVersion": 1, "step": "reduce", "ok": bool, "summary": str,
     "outputs": {"result": {...} | {}, "blend": "<job>/reduce.blend" | None},
     "error": None | {"code", "message", "remediation"}}

Progress is printed as NMG_PROGRESS lines, the same protocol the finalize steps use.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import bpy

from ..reduce_core import ReduceError, reduce_asset

SCHEMA_VERSION: Final = 1
STEP: Final = "reduce"


def run_reduce(request: Mapping[str, Any], job: str | Path) -> dict[str, Any]:
    """Reduce the request's collection and return the reduce envelope. Never raises ReduceError."""
    job_dir = Path(job)
    job_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = reduce_asset(
            str(request["collection"]),
            str(request["asset_class"]),
            _optional_path(request.get("budgets_path")),
            device=str(request.get("device") or "GPU"),
            cage_extrusion=request.get("cage_extrusion"),
            max_ray_distance=request.get("max_ray_distance"),
            parts=_parts(request.get("parts")),
            miss_threshold=request.get("miss_threshold"),
            out_dir=job_dir / "reduce",
            progress=_progress,
        )
    except ReduceError as error:
        return _envelope(
            ok=False,
            summary=error.message,
            outputs={"result": {}, "blend": None},
            error={
                "code": error.code,
                "message": error.message,
                "remediation": error.remediation,
            },
        )
    blend = job_dir / "reduce.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), copy=True)
    return _envelope(
        ok=True,
        summary=str(result["summary"]),
        outputs={"result": result, "blend": str(blend)},
        error=None,
    )


def _envelope(
    *,
    ok: bool,
    summary: str,
    outputs: dict[str, Any],
    error: dict[str, str] | None,
) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "step": STEP,
        "ok": ok,
        "summary": summary,
        "outputs": outputs,
        "error": error,
    }


def _optional_path(value: Any) -> str | None:
    return str(value) if value else None


def _parts(value: Any) -> dict[str, dict[str, Any]]:
    """The request's per-part options with the unset (null) fields dropped."""
    if not value:
        return {}
    return {
        str(name): {key: item for key, item in dict(spec or {}).items() if item is not None}
        for name, spec in dict(value).items()
    }


def _progress(fraction: float, message: str) -> None:
    line = {"state": "running", "step": STEP, "progress": round(fraction, 3), "message": message}
    print("NMG_PROGRESS " + json.dumps(line, sort_keys=True), flush=True)
