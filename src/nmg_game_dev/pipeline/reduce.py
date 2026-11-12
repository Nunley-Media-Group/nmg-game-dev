"""Reduce pipeline: the background ``reduce`` job for an over-budget generated asset (#139).

``execute_reduce`` runs one reduce request end to end:

1. Checkpoint.  The open session is saved to a checkpoint copy and its ``<Name>`` content hash is
   recorded, or a ``--blend`` file is copied and hashed headlessly.
2. Reduce.  One headless Blender process runs ``reduce_asset`` on the checkpoint and writes
   ``reduce.blend`` and the ``reduce.json`` envelope.  A failing envelope raises its own code.
3. Load-back.  A session run that reduced loads ``<Name>`` and ``<Name>_High`` back into the
   session, but only when the session's ``<Name>`` still has the checkpoint hash.  Otherwise the
   run fails with ``reduce.session_changed`` and carries the result ``.blend`` path.  A
   ``within_budget`` result loads nothing.

The job runs through ``pipeline.jobs`` (``kind: "reduce"``), so it shares the cache-root lock,
the status file, and ``get_finalize_job`` with finalize.  The CLI and the ``reduce_asset`` MCP tool
both return the same result dict.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .blender_proc import ProgressCallback, StepRunner, SubprocessStepRunner
from .engine import FinalizeClients, checkpoint_session
from .errors import PipelineError

REDUCE_STEP: Final = "reduce"
HIGH_SUFFIX: Final = "_High"
# A session load-back replaces the reduced <Name> and its <Name>_High original together.
LOAD_BACK_SUFFIXES: Final[tuple[str, ...]] = ("", HIGH_SUFFIX)
_PASCAL_CASE = r"^[A-Z][A-Za-z0-9]*$"
_INVALID_REQUEST: Final = "reduce.invalid_request"
_INVALID_OVERRIDE: Final = "reduce.invalid_override"

Device = Literal["GPU", "CPU"]


class PartOptions(BaseModel):
    """Per-part overrides for one mesh part, keyed by its object name in the request.

    Attributes:
        share: Fraction of the Desktop budget for this part, above 0 and at most 1.
        tris: Exact triangle target for this part.  Either ``share`` or ``tris``, not both.
        cage_extrusion: Bake cage extrusion in metres for this part only.
        max_ray_distance: Bake ray distance in metres for this part only.
    """

    model_config = ConfigDict(frozen=True)

    share: float | None = Field(default=None, gt=0, le=1)
    tris: int | None = Field(default=None, ge=1)
    cage_extrusion: float | None = Field(default=None, gt=0)
    max_ray_distance: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _one_split(self) -> PartOptions:
        if self.share is not None and self.tris is not None:
            raise ValueError("a part takes share or tris, not both")
        return self


class ReduceRequest(BaseModel):
    """Immutable, validated description of one reduce run.

    Attributes:
        collection: Blender collection holding the generated asset, e.g. ``Crate``.
        asset_class: Contract class whose Desktop budget applies.  Any value other than the five
            contract classes is refused inside Blender with ``reduce.class_unsupported``.
        blend: Optional saved ``.blend`` to reduce headlessly instead of the open session.
        budgets_path: Optional ``nmg-budgets.json`` with Desktop overrides.
        device: Bake device.  ``GPU`` falls back to ``CPU`` inside Blender when unavailable.
        cage_extrusion: Asset-wide bake cage extrusion in metres.  ``None`` uses 0.03.
        max_ray_distance: Asset-wide bake ray distance in metres.  ``None`` uses 0.10.
        miss_threshold: Largest unbaked share a part may have.  ``None`` uses 0.01.
        parts: Per-part overrides by object name.
    """

    model_config = ConfigDict(frozen=True)

    collection: str = Field(pattern=_PASCAL_CASE)
    asset_class: str = Field(min_length=1)
    blend: Path | None = None
    budgets_path: Path | None = None
    device: Device = "GPU"
    cage_extrusion: float | None = Field(default=None, gt=0)
    max_ray_distance: float | None = Field(default=None, gt=0)
    miss_threshold: float | None = Field(default=None, ge=0, le=1)
    parts: dict[str, PartOptions] = Field(default_factory=dict)

    def to_json_dict(self) -> dict[str, object]:
        """Return the JSON projection written to ``<job_dir>/request.json``."""
        return self.model_dump(mode="json")


class ReduceSessionChangedError(PipelineError):
    """``reduce.session_changed``: the session changed during the run, so nothing was loaded.

    ``result`` carries the full result dict, and the message names the result ``.blend``.
    """

    def __init__(self, message: str, remediation: str, result: dict[str, Any]) -> None:
        super().__init__(
            code="reduce.session_changed",
            message=message,
            remediation=remediation,
            stage="reduce",
        )
        self.result = result


def build_request(
    *,
    collection: str,
    asset_class: str,
    blend: str | Path | None = None,
    budgets_path: str | Path | None = None,
    device: str = "GPU",
    cage_extrusion: float | None = None,
    max_ray_distance: float | None = None,
    miss_threshold: float | None = None,
    parts: Mapping[str, Mapping[str, Any]] | None = None,
) -> ReduceRequest:
    """Validate the arguments into a ``ReduceRequest``.

    Raises ``PipelineError`` with ``reduce.invalid_override`` for a bad per-part value and
    ``reduce.invalid_request`` for any other bad argument, before any job starts.
    """
    values: dict[str, Any] = {
        "collection": collection,
        "asset_class": asset_class,
        "blend": Path(blend) if blend else None,
        "budgets_path": Path(budgets_path) if budgets_path else None,
        "device": device,
        "cage_extrusion": cage_extrusion,
        "max_ray_distance": max_ray_distance,
        "miss_threshold": miss_threshold,
        "parts": dict(parts or {}),
    }
    try:
        return ReduceRequest.model_validate(values)
    except ValidationError as error:
        raise _invalid(error) from error


def execute_reduce(
    request: ReduceRequest,
    *,
    job_dir: Path,
    clients: FinalizeClients | None = None,
    runner: StepRunner | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run the reduce for ``request`` and return its result dict.

    Raises ``PipelineError`` for a failed reduce, with the code Blender reported.  Raises
    ``ReduceSessionChangedError`` when the session changed and nothing was loaded back.
    """
    active_clients = clients if clients is not None else FinalizeClients()
    active_runner = runner if runner is not None else SubprocessStepRunner()
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "request.json").write_text(
        json.dumps(request.to_json_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    asset_hash, checkpoint = checkpoint_session(
        collection=request.collection,
        blend=request.blend,
        job_dir=job_dir,
        runner=active_runner,
        clients=active_clients,
    )
    envelope = active_runner.run_step(
        REDUCE_STEP,
        job_dir=job_dir,
        in_blend=checkpoint,
        on_progress=_relay(progress),
    )
    if not envelope.get("ok"):
        raise _step_failure(envelope)

    outputs = envelope.get("outputs") or {}
    reduced = dict(outputs.get("result") or {})
    result_blend = Path(str(outputs.get("blend") or checkpoint))
    # Only a reduced session asset is loaded back; a within_budget result changes nothing.
    session_run = request.blend is None and reduced.get("state") == "reduced"
    loaded_back = False
    if session_run:
        session = active_clients.blender
        # checkpoint_session always creates the session client for a session run.
        assert session is not None
        load = session.load_back(
            result_blend=result_blend,
            collection=request.collection,
            expected_hash=asset_hash,
            suffixes=LOAD_BACK_SUFFIXES,
        )
        loaded_back = load.get("loaded") is True
    final = _result(request, reduced, result_blend, loaded_back=loaded_back)
    if session_run and not loaded_back:
        raise ReduceSessionChangedError(
            message=(
                f"{request.collection} changed in the Blender session after the checkpoint, so "
                f"nothing was loaded back. The result is at {result_blend}."
            ),
            remediation="Open the result .blend to review it, or rerun reduce on the unchanged "
            "session to load it back.",
            result=final,
        )
    return final


def _result(
    request: ReduceRequest,
    reduced: dict[str, Any],
    result_blend: Path,
    *,
    loaded_back: bool,
) -> dict[str, Any]:
    """The one result shape the job status, the CLI, and the MCP tool all return."""
    return {
        **reduced,
        "kind": "reduce",
        "collection": request.collection,
        "loaded_back": loaded_back,
        "result_blend": str(result_blend),
    }


def _step_failure(envelope: Mapping[str, Any]) -> PipelineError:
    error = envelope.get("error")
    if isinstance(error, dict):
        return PipelineError(
            code=str(error.get("code", "reduce.failed")),
            message=str(error.get("message", "The reduce step failed")),
            remediation=str(error.get("remediation", "Read blender-reduce.log, then rerun.")),
            stage="reduce",
        )
    return PipelineError(
        code="reduce.failed",
        message=str(envelope.get("summary", "The reduce step failed without an error")),
        remediation="Read blender-reduce.log in the job directory, then rerun.",
        stage="reduce",
    )


def _invalid(error: ValidationError) -> PipelineError:
    first = error.errors()[0]
    location = first.get("loc", ())
    code = _INVALID_OVERRIDE if location and location[0] == "parts" else _INVALID_REQUEST
    return PipelineError(
        code=code,
        message=f"The reduce arguments are invalid: {first.get('msg', 'invalid value')}",
        remediation="Use a PascalCase collection, a non-empty asset_class, positive cage and ray "
        "distances, a miss threshold from 0 to 1, and per-part share (0 to 1) or tris (at least "
        "1), never both.",
        stage="reduce",
    )


def _relay(progress: ProgressCallback | None) -> ProgressCallback:
    def emit(event: dict[str, Any]) -> None:
        if progress is not None:
            progress({"step": REDUCE_STEP, **event})

    return emit


def parts_from_json(text: str | None) -> dict[str, dict[str, Any]]:
    """Parse the CLI ``--parts`` JSON object. A bad value raises ``reduce.invalid_request``."""
    if not text:
        return {}
    try:
        parsed: Any = json.loads(text)
    except json.JSONDecodeError as error:
        raise PipelineError(
            code=_INVALID_REQUEST,
            message=f"--parts is not valid JSON: {error}",
            remediation='Pass a JSON object such as \'{"Wall": {"share": 0.4}}\'.',
            stage="reduce",
        ) from error
    if not isinstance(parsed, dict):
        raise PipelineError(
            code=_INVALID_REQUEST,
            message="--parts must be a JSON object keyed by part name.",
            remediation='Pass a JSON object such as \'{"Wall": {"share": 0.4}}\'.',
            stage="reduce",
        )
    return parsed


__all__ = [
    "HIGH_SUFFIX",
    "LOAD_BACK_SUFFIXES",
    "REDUCE_STEP",
    "PartOptions",
    "ReduceRequest",
    "ReduceSessionChangedError",
    "build_request",
    "execute_reduce",
    "parts_from_json",
]
