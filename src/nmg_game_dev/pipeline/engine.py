"""Finalize orchestration: checkpoint, the cached step chain, gates, load-back, and UE import (#69).

``execute`` runs one request end to end:

1. Checkpoint.  A session run asks Blender to save a checkpoint copy of the open collection and
   returns its content hash.  A ``--blend`` run copies the file and hashes it headlessly.
2. Step chain.  Each step's key is ``cache.key(step, input_hash, settings_hash)``.  The first input
   hash is the asset hash.  Later inputs are the previous step's output hash.  A hit restores the
   step's blobs where they are missing.  A miss runs the step, gates its reports, and stores it.
   When the alias index for the current asset matches the recorded settings, its recorded keys are
   used instead, so an already-finalized session is served from cache.
   Per-clip steps (``export_anims``, ``import_anims``, #138) skip this whole-step cache.  They run
   through ``pipeline/anims.py``, which caches each clip on its own key, and they do not move the
   input hash, so a clip-only change leaves the mesh steps' keys valid.
3. Load-back.  For a session run that reaches ``import_ue``, the result replaces the session's
   collections, unless the session changed since the checkpoint.  A refusal lets ``import_ue`` run
   and then fails the run with ``finalize.session_changed``.
4. UE import.  ``import_ue`` runs only after every earlier step passed.  ``import_anims`` runs
   after it, against the Desktop skeleton it created.

Errors are ``PipelineError`` with a stable code.  A failing step stops the chain before any later
step runs.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from nmg_game_dev.unreal.import_asset import import_variant

from . import anims
from .blender_proc import ProgressCallback, StepRunner
from .cache import ArtifactCache, CacheEntry
from .clients.blender_session import BlenderSessionClient
from .clients.unreal_mcp import UnrealMcpClient
from .errors import PipelineError
from .request import FinalizeRequest
from .result import FinalizeResult, StepResult
from .steps import (
    STEP_ORDER,
    STEPS,
    VARIANTS,
    StepName,
    blobs_for,
    budget_fingerprint,
    chain_input,
    envelope_outputs,
    gate_outputs,
    ordered_steps,
    output_hash,
    settings_hash,
    ue_destination,
)

ProgressSink = Callable[[dict[str, Any]], None]
StepSink = Callable[[StepResult], None]


class BlenderSession(Protocol):
    """The live Blender session.  ``BlenderSessionClient`` implements it; tests use a fake."""

    def checkpoint(self, *, collection: str, path: Path) -> str:
        """Save a checkpoint copy to ``path`` and return the collection content hash."""
        ...

    def load_back(
        self,
        *,
        result_blend: Path,
        collection: str,
        expected_hash: str,
    ) -> dict[str, Any]:
        """Load the result into the session unless the session changed, and report which."""
        ...


class UnrealPythonRunner(Protocol):
    """The Unreal MCP surface the import uses.  ``UnrealMcpClient`` implements it."""

    def execute_python_code(self, code: str) -> str:
        """Run UE Python and return the tool's text output."""
        ...


class FinalizeSessionChangedError(PipelineError):
    """``finalize.session_changed``: the session changed during the run, so nothing was loaded.

    The run still imported into UE.  ``result`` carries the full ``FinalizeResult``, and the result
    ``.blend`` is named in the message.
    """

    def __init__(self, message: str, remediation: str, result: FinalizeResult) -> None:
        super().__init__(
            code="finalize.session_changed",
            message=message,
            remediation=remediation,
            stage="finalize",
        )
        self.result = result


@dataclass
class FinalizeClients:
    """Optional client overrides.  Real clients are created on first use when left unset."""

    blender: BlenderSession | None = None
    unreal: UnrealPythonRunner | None = None


@dataclass
class _Run:
    request: FinalizeRequest
    cache: ArtifactCache
    job_dir: Path
    runner: StepRunner
    clients: FinalizeClients
    progress: ProgressSink | None


def execute(
    request: FinalizeRequest,
    steps: tuple[str, ...] | list[str],
    *,
    force: bool,
    cache: ArtifactCache,
    job_dir: Path,
    runner: StepRunner,
    clients: FinalizeClients | None = None,
    progress: ProgressSink | None = None,
    on_step: StepSink | None = None,
) -> FinalizeResult:
    """Run ``steps`` for ``request`` (plus the earlier steps they depend on) and return the result.

    Raises ``PipelineError`` (or ``FinalizeSessionChangedError``) when a step fails.
    """
    run = _Run(
        request=request,
        cache=cache,
        job_dir=job_dir,
        runner=runner,
        clients=clients if clients is not None else FinalizeClients(),
        progress=progress,
    )
    chain = ordered_steps(tuple(steps))
    job_dir.mkdir(parents=True, exist_ok=True)
    # The Blender entry reads the request from the job directory, so every run writes it there.
    (job_dir / "request.json").write_text(
        json.dumps(request.to_json_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    asset_hash, checkpoint = _checkpoint(run)
    budgets = budget_fingerprint(request.budgets_path)
    whole_steps = [step for step in chain if not STEPS[step].per_clip]
    current_settings = {step: settings_hash(step, request, budgets) for step in whole_steps}

    alias = None if force else cache.alias(asset_hash, job_dir=job_dir)
    alias_mode = alias is not None and all(
        step in alias.get("steps", {})
        and alias.get("settings", {}).get(step) == current_settings[step]
        for step in whole_steps
    )
    session_holds_result = bool(alias_mode and alias is not None and alias.get("loaded_back"))
    load_back_needed = request.blend is None and "import_ue" in chain and not session_holds_result

    input_hash = asset_hash
    keys: dict[str, str] = {}
    outputs_by_step: dict[str, dict[str, Any]] = {}
    results: list[StepResult] = []
    last_blend = checkpoint
    loaded_back = False
    refused: dict[str, Any] | None = None
    post_hash: str | None = None

    for index, step in enumerate(chain):
        spec = STEPS[step]
        _emit(run, state="running", step=step, progress=index / len(chain), message="starting")
        if step == "import_ue" and load_back_needed:
            load = _load_back(run, asset_hash=asset_hash, result_blend=last_blend)
            if load.get("loaded") is True:
                loaded_back = True
                post_hash = str(load.get("hash", ""))
            else:
                refused = load

        if spec.per_clip:
            # Per-clip steps keep their own cache and leave the input hash unchanged (#138).
            clip_outputs = _run_per_clip(run, step, outputs_by_step, last_blend, force=force)
            outputs_by_step[step] = clip_outputs
            # With no clips nothing was re-run, so the step is served from cache exactly when the
            # step before it was.  The probe itself is never cached.
            if clip_outputs["clips"]:
                all_cached = anims.clips_all_cached(clip_outputs)
            else:
                all_cached = bool(results) and results[-1].cache_hit
            clip_result = StepResult(
                step=step,
                cache_hit=all_cached,
                outputs=clip_outputs,
                summary=_summary(step, clip_outputs, all_cached),
            )
            results.append(clip_result)
            if on_step is not None:
                on_step(clip_result)
            continue

        if alias_mode and alias is not None:
            key = str(alias["steps"][step])
        else:
            key = cache.key(step, input_hash, current_settings[step])
        keys[step] = key

        entry = None if force else cache.get(key, job_dir=job_dir)
        if entry is not None:
            _restore_missing(run, key, step, entry)
            outputs = dict(entry.outputs)
            produced_hash = entry.output_hash
            cache_hit = True
        else:
            outputs = _run_step(run, step, outputs_by_step, last_blend)
            produced_hash = output_hash(step, outputs, blobs_for(step, outputs), job_dir=job_dir)
            cache.put(
                key,
                step=step,
                output_hash=produced_hash,
                outputs=outputs,
                blobs=blobs_for(step, outputs),
                job_dir=job_dir,
            )
            cache_hit = False

        if spec.mutates_scene:
            last_blend = Path(str(outputs["blend"]))
        input_hash = chain_input(asset_hash, produced_hash)
        outputs_by_step[step] = outputs
        result = StepResult(
            step=step,
            cache_hit=cache_hit,
            outputs=outputs,
            summary=_summary(step, outputs, cache_hit),
        )
        results.append(result)
        if on_step is not None:
            on_step(result)

    result_blend = str(last_blend) if "variants" in chain else None
    desktop, mobile = _content_paths(outputs_by_step)
    final = FinalizeResult(
        steps=results,
        desktop_content_path=desktop,
        mobile_content_path=mobile,
        loaded_back=loaded_back,
        result_blend=result_blend,
        animations=_animations_result(outputs_by_step),
    )

    if tuple(chain) == STEP_ORDER:
        record = {
            "steps": keys,
            "settings": current_settings,
            "result_blend": result_blend,
            "content_paths": {"desktop": desktop, "mobile": mobile},
            "loaded_back": False,
        }
        cache.put_alias(asset_hash, record, job_dir=job_dir)
        if loaded_back and post_hash:
            cache.put_alias(post_hash, {**record, "loaded_back": True}, job_dir=job_dir)

    if refused is not None:
        blend = result_blend or str(checkpoint)
        raise FinalizeSessionChangedError(
            message=(
                f"{request.collection} changed in the Blender session after the checkpoint, so "
                f"nothing was loaded back. The result is at {blend}."
            ),
            remediation=(
                "Open the result .blend to review it, or rerun finalize on the unchanged "
                "session to load it back."
            ),
            result=final,
        )
    return final


def _checkpoint(run: _Run) -> tuple[str, Path]:
    checkpoint = run.job_dir / "checkpoint.blend"
    request = run.request
    if request.blend is None:
        if run.clients.blender is None:
            run.clients.blender = BlenderSessionClient()
        asset_hash = run.clients.blender.checkpoint(
            collection=request.collection,
            path=checkpoint,
        )
        return asset_hash, checkpoint
    if not request.blend.is_file():
        raise PipelineError(
            code="finalize.blend_not_found",
            message=f"The .blend to finalize does not exist: {request.blend}",
            remediation="Pass the path of a saved .blend with --blend, or omit it to finalize the "
            "open session.",
            stage="finalize",
        )
    run.job_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(request.blend, checkpoint)
    return run.runner.hash(job_dir=run.job_dir, in_blend=checkpoint), checkpoint


def _run_step(
    run: _Run,
    step: StepName,
    outputs_by_step: dict[str, dict[str, Any]],
    last_blend: Path,
) -> dict[str, Any]:
    if step == "import_ue":
        return _run_import(run, outputs_by_step)

    in_blend: Path | None
    if step in ("validate", "bake"):
        in_blend = run.job_dir / "checkpoint.blend"
    elif step == "reimport":
        in_blend = None
    else:
        in_blend = last_blend

    inputs: dict[str, Any] | None = None
    if step == "reimport":
        export = outputs_by_step["export"]["variants"]
        inputs = {
            "variants": {
                variant: {
                    "dir": export[variant]["dir"],
                    "pre_report": export[variant]["pre_report"],
                }
                for variant in VARIANTS
            }
        }

    envelope = run.runner.run_step(
        step,
        job_dir=run.job_dir,
        in_blend=in_blend,
        inputs=inputs,
        on_progress=_progress_callback(run, step),
    )
    outputs = envelope_outputs(step, envelope)
    gate_outputs(step, outputs)
    return outputs


def _run_per_clip(
    run: _Run,
    step: StepName,
    outputs_by_step: dict[str, dict[str, Any]],
    last_blend: Path,
    *,
    force: bool,
) -> dict[str, Any]:
    if step == "export_anims":
        return anims.run_export_anims(
            run.request,
            cache=run.cache,
            job_dir=run.job_dir,
            runner=run.runner,
            in_blend=last_blend,
            force=force,
            on_progress=_progress_callback(run, step),
        )
    owned: UnrealMcpClient | None = None

    def client() -> UnrealPythonRunner:
        nonlocal owned
        if run.clients.unreal is not None:
            return run.clients.unreal
        if owned is None:
            owned = UnrealMcpClient()
        return owned

    try:
        return anims.run_import_anims(
            run.request,
            cache=run.cache,
            job_dir=run.job_dir,
            exported=outputs_by_step["export_anims"]["clips"],
            client=client,
            force=force,
        )
    finally:
        if owned is not None:
            owned.close()


def _animations_result(outputs_by_step: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Return the ``animations`` entry of the result, or ``None`` when no clip step ran (#138)."""
    exported = outputs_by_step.get("export_anims")
    imported = outputs_by_step.get("import_anims")
    if exported is None and imported is None:
        return None
    export_clips = exported["clips"] if exported is not None else []
    import_hits: dict[str, bool] = {}
    if imported is not None:
        import_hits = {clip["name"]: bool(clip["cache_hit"]) for clip in imported["clips"]}
    clips = [
        {
            "name": clip["name"],
            "asset_path": clip["asset_path"],
            "export_cache_hit": bool(clip["cache_hit"]),
            "import_cache_hit": import_hits.get(clip["name"]),
        }
        for clip in export_clips
    ]
    source = imported if imported is not None else (exported or {})
    return {
        "content_path": source.get("content_dir"),
        "clips": clips,
        "stale": list(imported["stale"]) if imported is not None else [],
        "compatible": list(imported["compatible"]) if imported is not None else [],
    }


def _run_import(run: _Run, outputs_by_step: dict[str, dict[str, Any]]) -> dict[str, Any]:
    request = run.request
    export = outputs_by_step["export"]["variants"]
    client: UnrealPythonRunner
    owned: UnrealMcpClient | None = None
    if run.clients.unreal is not None:
        client = run.clients.unreal
    else:
        owned = UnrealMcpClient()
        client = owned
    imports: dict[str, Any] = {}
    paths: dict[str, str] = {}
    # A rigged Mobile reuses the Desktop skeleton and physics asset, so both variants name the
    # Desktop folder, and Desktop is imported first (VARIANTS orders it).
    skeleton_dest = ue_destination(request, "Desktop")
    try:
        for variant in VARIANTS:
            entry = export[variant]
            report: dict[str, Any] = json.loads(
                Path(str(entry["pre_report"])).read_text(encoding="utf-8")
            )
            destination = ue_destination(request, variant)
            imports[variant] = import_variant(
                client,
                variant_dir=str(entry["dir"]),
                dest=destination,
                name=request.collection,
                report=report,
                skeleton_dest=skeleton_dest,
            )
            paths[variant] = destination
    finally:
        if owned is not None:
            owned.close()
    return {
        "desktop_content_path": paths["Desktop"],
        "mobile_content_path": paths["Mobile"],
        "imports": imports,
    }


def _load_back(run: _Run, *, asset_hash: str, result_blend: Path) -> dict[str, Any]:
    if run.clients.blender is None:
        run.clients.blender = BlenderSessionClient()
    _emit(run, state="running", step="import_ue", progress=None, message="loading back")
    return run.clients.blender.load_back(
        result_blend=result_blend,
        collection=run.request.collection,
        expected_hash=asset_hash,
    )


def _restore_missing(run: _Run, key: str, step: StepName, entry: CacheEntry) -> None:
    targets = blobs_for(step, entry.outputs)
    for name in entry.blob_names:
        target = targets.get(name)
        if target is not None and not target.exists():
            run.cache.restore(key, name, target)


def _content_paths(outputs_by_step: dict[str, dict[str, Any]]) -> tuple[str | None, str | None]:
    imported = outputs_by_step.get("import_ue")
    if imported is None:
        return None, None
    return str(imported["desktop_content_path"]), str(imported["mobile_content_path"])


def _summary(step: StepName, outputs: dict[str, Any], cache_hit: bool) -> str:
    bake = outputs.get("bake")
    if step == "bake" and isinstance(bake, dict) and isinstance(bake.get("summary"), str):
        # bake_core's own one-line summary (#67) is the step's summary.
        return str(bake["summary"])
    if STEPS[step].per_clip:
        clips = outputs.get("clips", [])
        if not clips:
            return f"{step}: no clips"
        hits = sum(1 for clip in clips if clip.get("cache_hit") is True)
        return f"{step}: {len(clips)} clip(s), {hits} from cache"
    prefix = "served from cache" if cache_hit else "ran"
    return f"{step} {prefix}"


def _progress_callback(run: _Run, step: str) -> ProgressCallback:
    def relay(event: dict[str, Any]) -> None:
        event = {"step": step, **event}
        if run.progress is not None:
            run.progress(event)

    return relay


def _emit(run: _Run, *, state: str, step: str, progress: float | None, message: str) -> None:
    if run.progress is not None:
        run.progress({"state": state, "step": step, "progress": progress, "message": message})
