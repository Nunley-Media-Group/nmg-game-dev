"""The ``finalize`` MCP tools (#69, #148, #149) and ``import_audio`` (#155) as plain functions.

``mcp-servers/finalize`` registers these.  They return plain dicts.  A failure comes back as
``{"error": {"code", "message", "remediation", "stage"}}``, and the same error is logged to stderr
by the server.  Keeping the logic here lets the tests cover it without the MCP SDK.

``finalize_asset`` takes one ``collection`` or a ``requests`` batch, which finalizes its entries one
at a time, in order, under one lock.  The wait options apply to the whole call.  A missing
``export_root`` is ``<project>/game/assets``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

from nmg_game_dev.audio import import_audio as _import_audio
from nmg_game_dev.design.paths import project_root as _project_root
from nmg_game_dev.godot.material_variants import list_material_variants as list_variants
from nmg_game_dev.godot.project import require_project
from nmg_game_dev.godot.runner import GodotRunner
from nmg_game_dev.godot.shot import take_shot
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.request import FinalizeRequest
from nmg_game_dev.pipeline.steps import STEP_ORDER, parse_step

from .service import (
    FinalizeService,
    MissingArgumentError,
    build_batch,
    build_reduce_request,
    build_request,
    clamp_wait,
    default_export_root,
    error_dict,
)

_JOB_FIELDS = ("job_id", "state", "step", "progress", "message", "result", "error", "batch")
_PASCAL: Final = re.compile(r"^[A-Z][A-Za-z0-9]*$")
MAX_SHOT_AFTER_S: Final = 60.0


def finalize_asset(
    *,
    collection: str | None = None,
    category: str | None = None,
    asset_class: str | None = None,
    export_root: str | None = None,
    blend: str | None = None,
    budgets_path: str | None = None,
    material_variants_path: str | None = None,
    force: bool = False,
    wait_seconds: float = 0,
    requests: list[dict[str, Any]] | None = None,
    fail_fast: bool = False,
    wait_for_lock: bool = False,
    lock_wait_seconds: float | None = None,
    compatible_with: list[str] | None = None,
    service: FinalizeService | None = None,
) -> dict[str, Any]:
    """Finalize one collection, or a batch of ``requests`` in order.

    Pass exactly one of ``collection`` or ``requests``.  The batch entries take the finalize
    request keys.  The top-level category, asset class, export root, blend, and budgets fill in any
    key an entry omits.  Without an export root anywhere, ``<project>/game/assets`` is used.
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
    try:
        request = _request(
            collection,
            category,
            asset_class,
            export_root,
            blend,
            budgets_path,
            material_variants_path,
            compatible_with,
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
    export_root: str | None = None,
    blend: str | None = None,
    budgets_path: str | None = None,
    material_variants_path: str | None = None,
    force: bool = False,
    wait_seconds: float = 0,
    wait_for_lock: bool = False,
    lock_wait_seconds: float | None = None,
    compatible_with: list[str] | None = None,
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
            material_variants_path,
            compatible_with,
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


def list_material_variants(
    *,
    category: str,
    collection: str,
    export_root: str | Path | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """List a finalized asset's material variants from the files finalize wrote (#148, #249 FR6).

    Reads only ``<export_root>/<Category>/<Name>/nmg-variants.json`` and checks which variant
    ``.tres`` files exist; ``export_root`` defaults to ``$CLAUDE_PROJECT_DIR/game/assets``.  Returns
    rows of ``{name, material, desktop, mobile}`` sorted by material, then name, where
    ``desktop``/``mobile`` is the ``res://`` path of the ``.tres`` or ``None``.  An asset with no
    material variants returns ``[]``.  A missing or invalid sidecar returns ``{"error": ...}`` with
    ``finalize.material_variants_failed``.  The listing never starts Godot.
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
    root = Path(export_root) if export_root else default_export_root()
    try:
        return list_variants(root, category, collection)
    except PipelineError as error:
        return {"error": error_dict(error)}


def import_audio(
    file: str,
    name: str,
    kind: str,
    loop: bool | None = None,
    *,
    max_seconds: float | None = None,
    loudness_lufs: float | None = None,
    loop_crossfade_ms: int | None = None,
    finish: bool | None = None,
    project_root: str | Path | None = None,
    godot: GodotRunner | None = None,
) -> dict[str, Any]:
    """Finish and store a saved sound as a WAV, and import it into Godot (#155, #249, #252).

    A sound effect becomes an ``AudioStreamWAV`` and music an ``AudioStreamOggVorbis`` under
    ``game/assets/Audio/``. ``loop`` and the finishing arguments (``max_seconds``,
    ``loudness_lufs``, ``loop_crossfade_ms``, ``finish``) override the sound's stored settings.
    Returns the same result JSON as ``python -m nmg_game_dev.audio import`` (``godot_asset``,
    ``imported_to_godot``, ``finish``, ``settings``), or ``{"error"}``.
    """
    try:
        return _import_audio(
            file,
            name,
            kind,
            loop,
            max_seconds=max_seconds,
            loudness_lufs=loudness_lufs,
            loop_crossfade_ms=loop_crossfade_ms,
            finish=finish,
            project_root=Path(project_root) if project_root else None,
            godot=godot,
        )
    except PipelineError as error:
        return {"error": error_dict(error)}


def game_screenshot(
    path: str,
    after: float = 3,
    options: list[str] | None = None,
    *,
    project_root: str | Path | None = None,
    godot: GodotRunner | None = None,
) -> dict[str, Any]:
    """Save a PNG of the running consumer game after ``after`` seconds (#251 FR4, AC5, AC6).

    Runs ``game/project.godot`` windowed with the launch ``options`` and ``--nmg-shot``, so
    NmgLaunch writes the root viewport to ``path`` and quits. A relative ``path`` resolves against
    the consumer root (``CLAUDE_PROJECT_DIR``, else the working directory). Returns
    ``{"path", "width", "height"}``, or ``{"error": {code, message, remediation, stage}}``:
    ``shot.invalid_after`` for ``after`` outside 0 to 60, ``shot.invalid_path``,
    ``godot.project_missing``, ``godot.not_found``, or ``shot.no_image``.
    """
    try:
        if not 0 <= after <= MAX_SHOT_AFTER_S:
            raise PipelineError(
                code="shot.invalid_after",
                message=f"after must be between 0 and {MAX_SHOT_AFTER_S:g} seconds, got {after:g}.",
                remediation="Pass an after between 0 and 60 seconds.",
                stage="shot",
            )
        root = Path(project_root) if project_root else _project_root()
        game = require_project(root / "game" / "project.godot")
        target = Path(path)
        if not target.is_absolute():
            target = root / target
        return take_shot(game, target, after, options or [], runner=godot)
    except PipelineError as error:
        return {"error": error_dict(error)}


class _InvalidRequestError(Exception):
    def __init__(self, payload: dict[str, str]) -> None:
        super().__init__(payload["message"])
        self.payload = payload


def _invalid(message: str) -> dict[str, str]:
    return {
        "code": "finalize.invalid_request",
        "message": message,
        "remediation": "Pass exactly one of collection or requests.",
        "stage": "finalize",
    }


def _request(
    collection: str,
    category: str | None,
    asset_class: str | None,
    export_root: str | None,
    blend: str | None,
    budgets_path: str | None,
    material_variants_path: str | None = None,
    compatible_with: list[str] | None = None,
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
            compatible_with=compatible_with or (),
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
    return _finish(lambda: active.start_reduce(request), active, wait_seconds=wait_seconds)


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
    return _job_response(job_id, status)


def _job_response(job_id: str, status: dict[str, Any]) -> dict[str, Any]:
    response: dict[str, Any] = {"job_id": job_id, "status": status.get("state")}
    if status.get("state") == "succeeded":
        response["result"] = status.get("result")
    elif status.get("state") == "failed":
        response["error"] = status.get("error")
    return response
