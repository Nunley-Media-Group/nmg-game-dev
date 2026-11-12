"""Finalize job service shared by the CLI and the ``finalize`` MCP server (#69).

Both entry points use one implementation.  The CLI blocks on a job until it is terminal.  The MCP
tools return a job id at once, or the finished result when it completes within ``wait_seconds``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

from nmg_game_dev.design import backlog as design_backlog
from nmg_game_dev.design.paths import backlog_path, project_root
from nmg_game_dev.pipeline import jobs
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.reduce import ReduceRequest
from nmg_game_dev.pipeline.reduce import build_request as build_reduce_validated
from nmg_game_dev.pipeline.request import DEFAULT_PIE_WAIT_SECONDS, FinalizeRequest
from nmg_game_dev.pipeline.steps import STEP_ORDER

BUDGET_FILE: Final = "nmg-budgets.json"
MATERIAL_VARIANTS_SUFFIX: Final = ".material-variants.json"
MAX_WAIT_SECONDS: Final = 150
BATCH_ENTRY_KEYS: Final = frozenset(
    {
        "collection",
        "category",
        "asset_class",
        "export_root",
        "blend",
        "budgets_path",
        "device",
        "pie_mode",
        "pie_wait_seconds",
        "compatible_with",
        "material_variants_path",
    }
)


class MissingArgumentError(ValueError):
    """``category`` or ``asset_class`` is absent and no design backlog entry supplies it."""

    def __init__(self, argument: str, checked: Path) -> None:
        self.argument = argument
        self.checked = checked
        super().__init__(
            f"{argument} is required: no design backlog entry supplies it (checked {checked})"
        )

    def payload(self) -> dict[str, str]:
        """Return the ``finalize.invalid_request`` payload the MCP tools and the CLI share."""
        return {
            "code": "finalize.invalid_request",
            "message": str(self),
            "remediation": f"Pass {self.argument} explicitly, or add a docs/design asset entry "
            "for the collection and run `python -m nmg_game_dev.design sync`.",
            "stage": "finalize",
        }


def resolve_backlog(
    collection: str, category: str | None, asset_class: str | None
) -> tuple[str | None, str | None, Path | None]:
    """Fill a missing ``category`` or ``asset_class`` from the design backlog.

    Explicit values always win.  The backlog path is returned whenever an asset entry matches
    ``collection``, so a successful ``finalize_asset`` can mark that entry.  An unreadable backlog
    counts as no match.
    """
    path = backlog_path(project_root())
    try:
        entry = design_backlog.find_asset(path, collection)
    except (OSError, ValueError):
        entry = None
    if entry is None:
        return category, asset_class, None
    if category is None and entry.fields.get("category") is not None:
        category = str(entry.fields["category"])
    if asset_class is None and entry.fields.get("asset_class") is not None:
        asset_class = str(entry.fields["asset_class"])
    return category, asset_class, path


def default_budgets_path() -> Path | None:
    """Return the project's ``nmg-budgets.json`` when it exists, else ``None``.

    The project root is ``CLAUDE_PROJECT_DIR`` when set, otherwise the working directory.  The
    add-on's contract defaults apply when this returns ``None``.
    """
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
    candidate = root / BUDGET_FILE
    return candidate if candidate.is_file() else None


def resolve_material_variants(
    collection: str,
    blend: Path | None,
    explicit: str | Path | None,
) -> Path | None:
    """Return the absolute material-variants declaration for a request, or ``None`` (#148).

    An explicit path wins and must exist.  Without one, the declaration named
    ``<collection>.material-variants.json`` beside ``blend`` is used when it is there.  A session
    run without an explicit path has no ``blend`` to search, so it declares no material variants.
    """
    if explicit:
        path = Path(explicit).resolve()
        if not path.is_file():
            raise PipelineError(
                code="finalize.material_variants_not_found",
                message=f"The material-variants declaration does not exist: {path}",
                remediation="Pass the path of an existing <Name>.material-variants.json, or omit "
                "it to use the one beside the .blend.",
                stage="finalize",
            )
        return path
    if blend is not None:
        candidate = blend.resolve().parent / f"{collection}{MATERIAL_VARIANTS_SUFFIX}"
        if candidate.is_file():
            return candidate
    return None


def build_request(
    *,
    collection: str,
    category: str | None,
    asset_class: str | None,
    export_root: str | Path,
    blend: str | Path | None = None,
    budgets_path: str | Path | None = None,
    device: str = "GPU",
    pie_mode: str = "wait",
    pie_wait_seconds: object = DEFAULT_PIE_WAIT_SECONDS,
    compatible_with: Sequence[str] = (),
    material_variants_path: str | Path | None = None,
) -> FinalizeRequest:
    """Validate the arguments into a ``FinalizeRequest``, defaulting the budget file.

    A ``None`` category or asset class comes from the design backlog (#112 FR5).  Raises
    ``MissingArgumentError`` when neither the argument nor the backlog supplies it, and
    ``pydantic.ValidationError`` for an invalid argument, both before any step runs.  Raises
    ``PipelineError`` (``finalize.material_variants_not_found``) for a missing explicit
    material-variants path.
    """
    category, asset_class, backlog = resolve_backlog(collection, category, asset_class)
    checked = backlog_path(project_root())
    if category is None:
        raise MissingArgumentError("category", checked)
    if asset_class is None:
        raise MissingArgumentError("asset_class", checked)
    budgets = Path(budgets_path) if budgets_path else default_budgets_path()
    blend_path = Path(blend) if blend else None
    declaration = resolve_material_variants(collection, blend_path, material_variants_path)
    return FinalizeRequest.model_validate(
        {
            "collection": collection,
            "category": category,
            "asset_class": asset_class,
            "export_root": Path(export_root),
            "blend": blend_path,
            "budgets_path": budgets,
            "device": device,
            "backlog_path": backlog,
            "pie_mode": pie_mode,
            "pie_wait_seconds": pie_wait_seconds,
            "compatible_with": tuple(compatible_with),
            "material_variants_path": declaration,
        }
    )


class _EntryError(ValueError):
    """One batch entry is invalid.  The message is the reason, without the index."""


def build_batch(
    entries: Sequence[object], *, defaults: Mapping[str, object] | None = None
) -> list[FinalizeRequest]:
    """Validate every batch entry before any work starts (#149, FR10).

    ``defaults`` fill in any key an entry omits, so a batch-wide ``export_root`` or PIE mode applies
    to every entry.  Raises ``finalize.invalid_batch`` naming the zero-based index and reason of
    each invalid entry.  Nothing is written, so no job directory exists after a failure.
    """
    shared = {key: value for key, value in (defaults or {}).items() if value is not None}
    requests: list[FinalizeRequest] = []
    problems: list[str] = []
    for index, entry in enumerate(entries):
        try:
            requests.append(_request_from_entry(entry, shared))
        except _EntryError as error:
            problems.append(f"index {index}: {error}")
    if problems:
        raise PipelineError(
            code="finalize.invalid_batch",
            message="The batch has invalid entries; nothing was started. " + "; ".join(problems),
            remediation="Fix each listed entry (zero-based index), then rerun the batch.",
            stage="finalize",
        )
    return requests


def _request_from_entry(entry: object, shared: Mapping[str, object]) -> FinalizeRequest:
    if not isinstance(entry, Mapping):
        raise _EntryError("the entry must be a JSON object")
    unknown = sorted(str(key) for key in entry if key not in BATCH_ENTRY_KEYS)
    if unknown:
        raise _EntryError(f"unknown key(s): {', '.join(unknown)}")
    merged: dict[str, object] = {**shared, **entry}
    for key in ("collection", "export_root"):
        if merged.get(key) is None:
            raise _EntryError(f"{key} is required")
    try:
        return build_request(
            collection=str(merged["collection"]),
            category=_optional_str(merged.get("category")),
            asset_class=_optional_str(merged.get("asset_class")),
            export_root=str(merged["export_root"]),
            blend=_optional_str(merged.get("blend")),
            budgets_path=_optional_str(merged.get("budgets_path")),
            device=str(merged.get("device") or "GPU"),
            pie_mode=str(merged.get("pie_mode", "wait")),
            pie_wait_seconds=merged.get("pie_wait_seconds", DEFAULT_PIE_WAIT_SECONDS),
            compatible_with=_compatible_with(merged.get("compatible_with")),
            material_variants_path=_optional_str(merged.get("material_variants_path")),
        )
    except MissingArgumentError as error:
        raise _EntryError(str(error)) from error
    except PipelineError as error:
        raise _EntryError(error.message) from error
    except ValidationError as error:
        raise _EntryError(str(error.errors()[0]["msg"])) from error


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _compatible_with(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise _EntryError("compatible_with must be a list of <Category>/<Name> strings")
    return tuple(str(item) for item in value)


def build_reduce_request(
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
    """Validate the reduce arguments, defaulting the project's ``nmg-budgets.json`` (#139).

    Raises ``PipelineError`` (``reduce.invalid_request`` or ``reduce.invalid_override``) before
    any job starts.
    """
    budgets = Path(budgets_path) if budgets_path else default_budgets_path()
    return build_reduce_validated(
        collection=collection,
        asset_class=asset_class,
        blend=blend,
        budgets_path=budgets,
        device=device,
        cage_extrusion=cage_extrusion,
        max_ray_distance=max_ray_distance,
        miss_threshold=miss_threshold,
        parts=parts,
    )


class FinalizeService:
    """Starts, polls, and runs finalize jobs under one cache root.

    Parameters:
        cache_root: The cache root.  Defaults to ``NMG_GAME_DEV_CACHE_DIR`` or the standard path.
        launcher: How a job's background process starts.  Defaults to a detached
            ``python -m nmg_game_dev.finalize run-job``.  Tests substitute an in-process launcher.
    """

    def __init__(
        self,
        cache_root: Path | None = None,
        *,
        launcher: jobs.Launcher | None = None,
    ) -> None:
        self._cache_root = cache_root
        self._launcher = launcher

    def start(
        self,
        request: FinalizeRequest,
        steps: Sequence[str] = STEP_ORDER,
        *,
        force: bool = False,
        wait_for_lock: bool = False,
        lock_wait_s: float | None = None,
    ) -> str:
        """Start a job for ``steps`` and return its id without waiting."""
        return jobs.start(
            request,
            tuple(steps),
            force=force,
            cache_root=self._cache_root,
            launcher=self._launcher,
            wait_for_lock=wait_for_lock,
            lock_wait_s=lock_wait_s,
        )

    def start_batch(
        self,
        requests: Sequence[FinalizeRequest],
        steps: Sequence[str] = STEP_ORDER,
        *,
        force: bool = False,
        fail_fast: bool = False,
        wait_for_lock: bool = False,
        lock_wait_s: float | None = None,
    ) -> str:
        """Start one job that finalizes ``requests`` in order, and return its id without waiting."""
        return jobs.start_batch(
            requests,
            tuple(steps),
            force=force,
            fail_fast=fail_fast,
            cache_root=self._cache_root,
            launcher=self._launcher,
            wait_for_lock=wait_for_lock,
            lock_wait_s=lock_wait_s,
        )

    def status(self, job_id: str) -> dict[str, Any]:
        """Return the job's current status."""
        return jobs.status(job_id, cache_root=self._cache_root)

    def wait(self, job_id: str, *, timeout_s: float) -> dict[str, Any]:
        """Return the job's status once it is terminal, or after ``timeout_s`` seconds."""
        return jobs.wait(job_id, timeout_s=timeout_s, cache_root=self._cache_root)

    def start_reduce(self, request: ReduceRequest) -> str:
        """Start a reduce job and return its id without waiting (#139)."""
        return jobs.start_reduce(request, cache_root=self._cache_root, launcher=self._launcher)

    def run(
        self,
        request: FinalizeRequest,
        steps: Sequence[str] = STEP_ORDER,
        *,
        force: bool = False,
        wait_for_lock: bool = False,
        lock_wait_s: float | None = None,
    ) -> dict[str, Any]:
        """Start a job and block until it is terminal.  Used by the CLI."""
        job_id = self.start(
            request, steps, force=force, wait_for_lock=wait_for_lock, lock_wait_s=lock_wait_s
        )
        return self.wait(job_id, timeout_s=float("inf"))

    def run_batch(
        self,
        requests: Sequence[FinalizeRequest],
        steps: Sequence[str] = STEP_ORDER,
        *,
        force: bool = False,
        fail_fast: bool = False,
        wait_for_lock: bool = False,
        lock_wait_s: float | None = None,
    ) -> dict[str, Any]:
        """Start a batch and block until it is terminal.  Used by the CLI."""
        job_id = self.start_batch(
            requests,
            steps,
            force=force,
            fail_fast=fail_fast,
            wait_for_lock=wait_for_lock,
            lock_wait_s=lock_wait_s,
        )
        return self.wait(job_id, timeout_s=float("inf"))


def clamp_wait(wait_seconds: float) -> float:
    """Clamp a requested wait to 0–150 seconds, as the MCP tools promise."""
    return min(max(float(wait_seconds), 0.0), float(MAX_WAIT_SECONDS))


def error_dict(error: PipelineError) -> dict[str, str]:
    """Return the ``{"error": ...}`` payload shape the MCP tools and the CLI share."""
    return {
        "code": error.code,
        "message": error.message,
        "remediation": error.remediation,
        "stage": error.stage,
    }


def is_prerequisite(code: str) -> bool:
    """Return ``True`` for failures the caller fixes by setting up the environment (exit 2)."""
    return code in {
        "finalize.blender_not_found",
        "mcp.blender.unreachable",
        "mcp.unreal.unreachable",
    }
