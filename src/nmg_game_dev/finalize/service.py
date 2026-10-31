"""Finalize job service shared by the CLI and the ``finalize`` MCP server (#69).

Both entry points use one implementation.  The CLI blocks on a job until it is terminal.  The MCP
tools return a job id at once, or the finished result when it completes within ``wait_seconds``.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from nmg_game_dev.design import backlog as design_backlog
from nmg_game_dev.design.paths import backlog_path, project_root
from nmg_game_dev.pipeline import jobs
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.request import FinalizeRequest
from nmg_game_dev.pipeline.steps import STEP_ORDER

BUDGET_FILE: Final = "nmg-budgets.json"
MAX_WAIT_SECONDS: Final = 150


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


def build_request(
    *,
    collection: str,
    category: str | None,
    asset_class: str | None,
    export_root: str | Path,
    blend: str | Path | None = None,
    budgets_path: str | Path | None = None,
    device: str = "GPU",
) -> FinalizeRequest:
    """Validate the arguments into a ``FinalizeRequest``, defaulting the budget file.

    A ``None`` category or asset class comes from the design backlog (#112 FR5).  Raises
    ``MissingArgumentError`` when neither the argument nor the backlog supplies it, and
    ``pydantic.ValidationError`` for an invalid argument, both before any step runs.
    """
    category, asset_class, backlog = resolve_backlog(collection, category, asset_class)
    checked = backlog_path(project_root())
    if category is None:
        raise MissingArgumentError("category", checked)
    if asset_class is None:
        raise MissingArgumentError("asset_class", checked)
    budgets = Path(budgets_path) if budgets_path else default_budgets_path()
    return FinalizeRequest.model_validate(
        {
            "collection": collection,
            "category": category,
            "asset_class": asset_class,
            "export_root": Path(export_root),
            "blend": Path(blend) if blend else None,
            "budgets_path": budgets,
            "device": device,
            "backlog_path": backlog,
        }
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
    ) -> str:
        """Start a job for ``steps`` and return its id without waiting."""
        return jobs.start(
            request,
            tuple(steps),
            force=force,
            cache_root=self._cache_root,
            launcher=self._launcher,
        )

    def status(self, job_id: str) -> dict[str, Any]:
        """Return the job's current status."""
        return jobs.status(job_id, cache_root=self._cache_root)

    def wait(self, job_id: str, *, timeout_s: float) -> dict[str, Any]:
        """Return the job's status once it is terminal, or after ``timeout_s`` seconds."""
        return jobs.wait(job_id, timeout_s=timeout_s, cache_root=self._cache_root)

    def run(
        self,
        request: FinalizeRequest,
        steps: Sequence[str] = STEP_ORDER,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """Start a job and block until it is terminal.  Used by the CLI."""
        job_id = self.start(request, steps, force=force)
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
