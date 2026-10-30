"""The three ``finalize`` MCP tools as plain functions over ``FinalizeService`` (#69).

``mcp-servers/finalize`` registers these.  They return plain dicts.  A failure comes back as
``{"error": {"code", "message", "remediation", "stage"}}``, and the same error is logged to stderr
by the server.  Keeping the logic here lets the tests cover it without the MCP SDK.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.request import FinalizeRequest
from nmg_game_dev.pipeline.steps import STEP_ORDER, parse_step

from .service import FinalizeService, build_request, clamp_wait, error_dict

_JOB_FIELDS = ("job_id", "state", "step", "progress", "message", "result", "error")


def finalize_asset(
    *,
    collection: str,
    category: str,
    asset_class: str,
    export_root: str,
    blend: str | None = None,
    budgets_path: str | None = None,
    force: bool = False,
    wait_seconds: float = 0,
    service: FinalizeService | None = None,
) -> dict[str, Any]:
    """Finalize every step for the collection.  Returns the job id and the result, if finished."""
    try:
        request = _request(collection, category, asset_class, export_root, blend, budgets_path)
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
    category: str,
    asset_class: str,
    export_root: str,
    blend: str | None = None,
    budgets_path: str | None = None,
    force: bool = False,
    wait_seconds: float = 0,
    service: FinalizeService | None = None,
) -> dict[str, Any]:
    """Run one step through the same implementation ``finalize_asset`` uses."""
    try:
        canonical = parse_step(step).name
        request = _request(collection, category, asset_class, export_root, blend, budgets_path)
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


class _InvalidRequestError(Exception):
    def __init__(self, payload: dict[str, str]) -> None:
        super().__init__(payload["message"])
        self.payload = payload


def _request(
    collection: str,
    category: str,
    asset_class: str,
    export_root: str,
    blend: str | None,
    budgets_path: str | None,
) -> FinalizeRequest:
    try:
        return build_request(
            collection=collection,
            category=category,
            asset_class=asset_class,
            export_root=export_root,
            blend=blend,
            budgets_path=budgets_path,
        )
    except ValidationError as error:
        raise _InvalidRequestError(
            {
                "code": "finalize.invalid_request",
                "message": f"The finalize arguments are invalid: {error.errors()[0]['msg']}",
                "remediation": "Use a PascalCase collection and category, a valid asset_class "
                "(small_prop, standard_prop, hero_prop, character, environment_piece), and an "
                "export_root directory.",
                "stage": "finalize",
            }
        ) from error


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

    response: dict[str, Any] = {"job_id": job_id, "status": status.get("state")}
    if status.get("state") == "succeeded":
        response["result"] = status.get("result")
    elif status.get("state") == "failed":
        response["error"] = status.get("error")
    return response
