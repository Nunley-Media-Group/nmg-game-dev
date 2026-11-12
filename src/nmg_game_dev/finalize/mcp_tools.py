"""The ``finalize`` MCP tools (#69) and ``import_audio`` (#155) as plain functions.

``mcp-servers/finalize`` registers these.  They return plain dicts.  A failure comes back as
``{"error": {"code", "message", "remediation", "stage"}}``, and the same error is logged to stderr
by the server.  Keeping the logic here lets the tests cover it without the MCP SDK.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

from pydantic import ValidationError

from nmg_game_dev.audio import import_audio as _import_audio
from nmg_game_dev.pipeline.clients.unreal_mcp import UnrealMcpClient
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.request import FinalizeRequest
from nmg_game_dev.pipeline.steps import STEP_ORDER, parse_step
from nmg_game_dev.unreal import list_material_variants as list_variants
from nmg_game_dev.unreal.import_asset import UnrealPythonClient

from .service import (
    FinalizeService,
    MissingArgumentError,
    build_reduce_request,
    build_request,
    clamp_wait,
    error_dict,
)

_JOB_FIELDS = ("job_id", "state", "step", "progress", "message", "result", "error")
_PASCAL: Final = re.compile(r"^[A-Z][A-Za-z0-9]*$")


def finalize_asset(
    *,
    collection: str,
    category: str | None = None,
    asset_class: str | None = None,
    export_root: str,
    blend: str | None = None,
    budgets_path: str | None = None,
    material_variants_path: str | None = None,
    force: bool = False,
    wait_seconds: float = 0,
    service: FinalizeService | None = None,
) -> dict[str, Any]:
    """Finalize every step for the collection.  Returns the job id and the result, if finished."""
    try:
        request = _request(
            collection,
            category,
            asset_class,
            export_root,
            blend,
            budgets_path,
            material_variants_path,
        )
    except _InvalidRequestError as error:
        return {"error": error.payload}
    return _start(
        service or FinalizeService(),
        request,
        STEP_ORDER,
        force=force,
        wait_seconds=wait_seconds,
    )


def run_finalize_step(
    *,
    step: str,
    collection: str,
    category: str | None = None,
    asset_class: str | None = None,
    export_root: str,
    blend: str | None = None,
    budgets_path: str | None = None,
    material_variants_path: str | None = None,
    force: bool = False,
    wait_seconds: float = 0,
    service: FinalizeService | None = None,
) -> dict[str, Any]:
    """Run one step through the same implementation ``finalize_asset`` uses."""
    try:
        canonical = parse_step(step).name
        request = _request(
            collection,
            category,
            asset_class,
            export_root,
            blend,
            budgets_path,
            material_variants_path,
        )
    except PipelineError as error:
        return {"error": error_dict(error)}
    except _InvalidRequestError as error:
        return {"error": error.payload}
    return _start(
        service or FinalizeService(),
        request,
        (canonical,),
        force=force,
        wait_seconds=wait_seconds,
    )


def get_finalize_job(job_id: str, *, service: FinalizeService | None = None) -> dict[str, Any]:
    """Return the job's status.  An unknown id comes back as ``finalize.job_not_found``."""
    try:
        status = (service or FinalizeService()).status(job_id)
    except PipelineError as error:
        return {"error": error_dict(error)}
    return {field: status.get(field) for field in _JOB_FIELDS if field in status}


def list_material_variants(
    *,
    category: str,
    collection: str,
    client: UnrealPythonClient | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """List the material variants Unreal holds for a finalized asset (#148, FR8).

    Returns rows of {name, material, desktop, mobile} sorted by material, then name. An asset with
    no material variants, or one not in Content, returns []. A failure returns {"error": {...}},
    such as mcp.unreal.unreachable when the Unreal MCP endpoint does not answer.
    """
    if not _PASCAL.fullmatch(category) or not _PASCAL.fullmatch(collection):
        return {
            "error": {
                "code": "finalize.invalid_request",
                "message": "category and collection must be PascalCase names",
                "remediation": "Pass the Props-style category and the Crate-style collection that "
                "finalize used.",
                "stage": "finalize",
            }
        }
    try:
        if client is not None:
            return list_variants(client, category, collection)
        with UnrealMcpClient() as owned:
            return list_variants(owned, category, collection)
    except PipelineError as error:
        return {"error": error_dict(error)}


def import_audio(file: str, name: str, kind: str, loop: bool = False) -> dict[str, Any]:
    """Store a saved sound as a WAV and import it as a SoundWave (#155, AC7).

    Returns the same result JSON as ``python -m nmg_game_dev.audio import``, or ``{"error"}``.
    """
    try:
        return _import_audio(file, name, kind, loop)
    except PipelineError as error:
        return {"error": error_dict(error)}


class _InvalidRequestError(Exception):
    def __init__(self, payload: dict[str, str]) -> None:
        super().__init__(payload["message"])
        self.payload = payload


def _request(
    collection: str,
    category: str | None,
    asset_class: str | None,
    export_root: str,
    blend: str | None,
    budgets_path: str | None,
    material_variants_path: str | None = None,
) -> FinalizeRequest:
    try:
        return build_request(
            collection=collection,
            category=category,
            asset_class=asset_class,
            export_root=export_root,
            blend=blend,
            budgets_path=budgets_path,
            material_variants_path=material_variants_path,
        )
    except MissingArgumentError as error:
        raise _InvalidRequestError(error.payload()) from error
    except PipelineError as error:
        raise _InvalidRequestError(error_dict(error)) from error
    except ValidationError as error:
        raise _InvalidRequestError(
            {
                "code": "finalize.invalid_request",
                "message": f"The finalize arguments are invalid: {error.errors()[0]['msg']}",
                "remediation": "Use a PascalCase collection and category, a valid asset_class "
                "(small_prop, standard_prop, hero_prop, character, environment_piece, "
                "terrain), and an export_root directory.",
                "stage": "finalize",
            }
        ) from error


def reduce_asset(
    *,
    collection: str,
    asset_class: str,
    blend: str | None = None,
    budgets_path: str | None = None,
    device: str = "GPU",
    cage_extrusion: float | None = None,
    max_ray_distance: float | None = None,
    miss_threshold: float | None = None,
    parts: Mapping[str, Mapping[str, Any]] | None = None,
    wait_seconds: float = 0,
    service: FinalizeService | None = None,
) -> dict[str, Any]:
    """Reduce an over-budget generated collection to its Desktop budget (#139).

    The same implementation as the panel operator, ``reduce_core.run_for_mcp``, and the CLI
    ``reduce`` command.  Returns the job id at once, or the result within ``wait_seconds``.
    """
    try:
        request = build_reduce_request(
            collection=collection,
            asset_class=asset_class,
            blend=blend,
            budgets_path=budgets_path,
            device=device,
            cage_extrusion=cage_extrusion,
            max_ray_distance=max_ray_distance,
            miss_threshold=miss_threshold,
            parts=parts,
        )
    except PipelineError as error:
        return {"error": error_dict(error)}
    active = service or FinalizeService()
    try:
        job_id = active.start_reduce(request)
        status = active.status(job_id)
        if clamp_wait(wait_seconds) > 0:
            status = active.wait(job_id, timeout_s=clamp_wait(wait_seconds))
    except PipelineError as error:
        return {"error": error_dict(error)}
    return _job_response(job_id, status)


def _start(
    service: FinalizeService,
    request: FinalizeRequest,
    steps: tuple[str, ...],
    *,
    force: bool,
    wait_seconds: float,
) -> dict[str, Any]:
    try:
        job_id = service.start(request, steps, force=force)
        status = service.status(job_id)
        if clamp_wait(wait_seconds) > 0:
            status = service.wait(job_id, timeout_s=clamp_wait(wait_seconds))
    except PipelineError as error:
        return {"error": error_dict(error)}
    return _job_response(job_id, status)


def _job_response(job_id: str, status: dict[str, Any]) -> dict[str, Any]:
    response: dict[str, Any] = {"job_id": job_id, "status": status.get("state")}
    if status.get("state") == "succeeded":
        response["result"] = status.get("result")
    elif status.get("state") == "failed":
        response["error"] = status.get("error")
    return response
