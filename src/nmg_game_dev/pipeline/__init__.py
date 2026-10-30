"""Finalize pipeline: turns an authored Blender asset into Desktop and Mobile Unreal content (#69).

An agent authors an asset freely in Blender.  The pipeline then finalizes that asset in six steps,
in order: ``validate`` → ``bake`` → ``variants`` → ``export`` → ``reimport`` → ``import_ue``.
Each step is a cached unit, and each Blender step runs headless.  The package does not generate
assets from prompts.  There is no ``Prompt`` type, no ``generate`` stage, and no ``source``
argument.

Public API::

    finalize(request, *, steps=STEP_ORDER, force=False, ...) -> FinalizeResult
    run_step(step, request, *, force=False, ...) -> StepResult

Failures raise ``PipelineError`` with ``code``, ``message``, ``remediation``, and ``stage``.  Later
steps never run after a failure.  Background runs, which the CLI and the ``finalize`` MCP server
use, are in ``pipeline.jobs``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from pathlib import Path

from .blender_proc import ProgressCallback, StepRunner, SubprocessStepRunner
from .cache import ArtifactCache
from .engine import (
    BlenderSession,
    FinalizeClients,
    FinalizeSessionChangedError,
    UnrealPythonRunner,
    execute,
)
from .errors import PipelineError
from .request import AssetClass, Device, FinalizeRequest
from .result import FinalizeResult, StepResult
from .steps import STEP_ORDER, StepName

__all__ = [
    "STEP_ORDER",
    "AssetClass",
    "BlenderSession",
    "Device",
    "FinalizeClients",
    "FinalizeRequest",
    "FinalizeResult",
    "FinalizeSessionChangedError",
    "PipelineError",
    "ProgressCallback",
    "StepName",
    "StepResult",
    "StepRunner",
    "SubprocessStepRunner",
    "UnrealPythonRunner",
    "finalize",
    "run_step",
]


def finalize(
    request: FinalizeRequest,
    *,
    steps: Sequence[str] = STEP_ORDER,
    force: bool = False,
    cache_dir: Path | None = None,
    clients: FinalizeClients | None = None,
    runner: StepRunner | None = None,
    job_dir: Path | None = None,
    progress: ProgressCallback | None = None,
) -> FinalizeResult:
    """Finalize ``request`` in-process and return the result.

    Parameters
    ----------
    request:
        The authored asset to finalize.
    steps:
        Steps to run.  Requesting a step also runs every earlier step it depends on.  Defaults to
        the full ``STEP_ORDER``.
    force:
        Bypass cache lookups.  Results are still written.
    cache_dir:
        Override the cache root.  Defaults to ``${NMG_GAME_DEV_CACHE_DIR:-~/.cache/nmg-game-dev}``.
    clients:
        Optional Blender session and Unreal client overrides.  Real clients are used when unset.
    runner:
        Optional step runner.  Defaults to headless Blender subprocesses.  Tests substitute an
        in-process fake.
    job_dir:
        Optional job directory.  A fresh one under the cache root is used when unset.
    progress:
        Optional callback that receives progress events.

    Raises
    ------
    PipelineError
        When a step fails.  No later step runs.  A refused load-back raises
        ``FinalizeSessionChangedError``, a ``PipelineError`` subclass that carries the result.
    """
    cache = ArtifactCache(cache_dir)
    return execute(
        request,
        tuple(steps),
        force=force,
        cache=cache,
        job_dir=job_dir if job_dir is not None else _direct_job_dir(cache),
        runner=runner if runner is not None else SubprocessStepRunner(),
        clients=clients,
        progress=progress,
    )


def run_step(
    step: str,
    request: FinalizeRequest,
    *,
    force: bool = False,
    cache_dir: Path | None = None,
    clients: FinalizeClients | None = None,
    runner: StepRunner | None = None,
    job_dir: Path | None = None,
    progress: ProgressCallback | None = None,
) -> StepResult:
    """Run one step through the same implementation ``finalize`` uses and return its result.

    The step's prerequisites run first, and they come from the cache when they are already there.
    """
    result = finalize(
        request,
        steps=(step,),
        force=force,
        cache_dir=cache_dir,
        clients=clients,
        runner=runner,
        job_dir=job_dir,
        progress=progress,
    )
    return result.steps[-1]


def _direct_job_dir(cache: ArtifactCache) -> Path:
    job = cache.root / "jobs" / f"direct-{uuid.uuid4().hex[:12]}"
    job.mkdir(parents=True, exist_ok=True)
    return job
