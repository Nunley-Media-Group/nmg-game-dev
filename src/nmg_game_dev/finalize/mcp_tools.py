"""The three ``finalize`` MCP tools as plain functions over ``FinalizeService`` (#69, #149).

``mcp-servers/finalize`` registers these.  They return plain dicts.  A failure comes back as
``{"error": {"code", "message", "remediation", "stage"}}``, and the same error is logged to stderr
by the server.  Keeping the logic here lets the tests cover it without the MCP SDK.

``finalize_asset`` takes one ``collection`` or a ``requests`` batch, which finalizes its entries one
at a time, in order, under one lock.  The wait and PIE options apply to the whole call.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.request import DEFAULT_PIE_WAIT_SECONDS, FinalizeRequest
from nmg_game_dev.pipeline.steps import STEP_ORDER, parse_step

from .service import (
    FinalizeService,
    MissingArgumentError,
    build_batch,
    build_request,
    clamp_wait,
    error_dict,
)

_JOB_FIELDS = ("job_id", "state", "step", "progress", "message", "result", "error", "batch")


def finalize_asset(
    *,
    collection: str | None = None,
    category: str | None = None,
    asset_class: str | None = None,
    export_root: str | None = None,
    blend: str | None = None,
    budgets_path: str | None = None,
    force: bool = False,
    wait_seconds: float = 0,
    requests: list[dict[str, Any]] | None = None,
    fail_fast: bool = False,
    wait_for_lock: bool = False,
    lock_wait_seconds: float | None = None,
    pie_mode: str = "wait",
    pie_wait_seconds: float = DEFAULT_PIE_WAIT_SECONDS,
    service: FinalizeService | None = None,
) -> dict[str, Any]:
    """Finalize one collection, or a batch of ``requests`` in order.

    Pass exactly one of ``collection`` (with ``export_root``) or ``requests``.  The batch entries
    take the finalize request keys.  The top-level category, asset class, export root, blend,
    budgets, and PIE options fill in any key an entry omits.
    """
    active = service or FinalizeService()
    if requests is not None:
        if collection is not None:
            return {
                "error": _invalid(
                    "Pass collection for one asset, or requests for a batch, not both."
                )
            }
        defaults: dict[str, object] = {
            "category": category,
            "asset_class": asset_class,
            "export_root": export_root,
            "blend": blend,
            "budgets_path": budgets_path,
            "pie_mode": pie_mode,
            "pie_wait_seconds": pie_wait_seconds,
        }
        try:
            batch = build_batch(requests, defaults=defaults)
        except PipelineError as error:
            return {"error": error_dict(error)}
        return _finish(
            lambda: active.start_batch(
                batch,
                STEP_ORDER,
                force=force,
                fail_fast=fail_fast,
                wait_for_lock=wait_for_lock,
                lock_wait_s=lock_wait_seconds,
            ),
            active,
            wait_seconds=wait_seconds,
        )

    if collection is None:
        return {"error": _invalid("Pass collection for one asset, or requests for a batch.")}
    if export_root is None:
        return {"error": _invalid("export_root is required for a single collection.")}
    try:
        request = _request(
            collection,
            category,
            asset_class,
            export_root,
            blend,
            budgets_path,
            pie_mode,
            pie_wait_seconds,
        )
    except _InvalidRequestError as error:
        return {"error": error.payload}
    return _finish(
        lambda: active.start(
            request,
            STEP_ORDER,
            force=force,
            wait_for_lock=wait_for_lock,
            lock_wait_s=lock_wait_seconds,
        ),
        active,
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
    force: bool = False,
    wait_seconds: float = 0,
    wait_for_lock: bool = False,
    lock_wait_seconds: float | None = None,
    pie_mode: str = "wait",
    pie_wait_seconds: float = DEFAULT_PIE_WAIT_SECONDS,
    service: FinalizeService | None = None,
) -> dict[str, Any]:
    """Run one step through the same implementation ``finalize_asset`` uses."""
    active = service or FinalizeService()
    try:
        canonical = parse_step(step).name
        request = _request(
            collection,
            category,
            asset_class,
            export_root,
            blend,
            budgets_path,
            pie_mode,
            pie_wait_seconds,
        )
    except PipelineError as error:
        return {"error": error_dict(error)}
    except _InvalidRequestError as error:
        return {"error": error.payload}
    return _finish(
        lambda: active.start(
            request,
            (canonical,),
            force=force,
            wait_for_lock=wait_for_lock,
            lock_wait_s=lock_wait_seconds,
        ),
        active,
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


def _invalid(message: str) -> dict[str, str]:
    return {
        "code": "finalize.invalid_request",
        "message": message,
        "remediation": "Pass exactly one of collection or requests, with export_root for a "
        "single collection.",
        "stage": "finalize",
    }


def _request(
    collection: str,
    category: str | None,
    asset_class: str | None,
    export_root: str,
    blend: str | None,
    budgets_path: str | None,
    pie_mode: str,
    pie_wait_seconds: float,
) -> FinalizeRequest:
    try:
        return build_request(
            collection=collection,
            category=category,
            asset_class=asset_class,
            export_root=export_root,
            blend=blend,
            budgets_path=budgets_path,
            pie_mode=pie_mode,
            pie_wait_seconds=pie_wait_seconds,
        )
    except MissingArgumentError as error:
        raise _InvalidRequestError(error.payload()) from error
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


def _finish(
    start: Callable[[], str],
    service: FinalizeService,
    *,
    wait_seconds: float,
) -> dict[str, Any]:
    """Start a job, wait up to ``wait_seconds`` for it, and return the job id with its state."""
    try:
        job_id = start()
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
