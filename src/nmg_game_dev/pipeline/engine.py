"""Finalize orchestration: checkpoint, the cached step chain, gates, load-back, and Godot import.

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
3. Load-back.  For a session run that reaches ``import_godot``, the result replaces the session's
   collections, unless the session changed since the checkpoint.  A refusal lets ``import_godot``
   run and then fails the run with ``finalize.session_changed``.
4. Godot import (#249).  ``import_godot`` runs only after every earlier step passed.  It resolves
   the Godot binary (``godot.not_found``) unless a runner was injected, finds the
   ``project.godot`` above the export root, and runs ``godot.import_asset.import_variants`` (a
   mesh) or ``godot.terrain.import_terrain`` (a terrain): one headless ``--import`` plus a probe
   per variant.  ``import_anims`` runs after it, against the Desktop ``.glb`` it verified.

Errors are ``PipelineError`` with a stable code.  A failing step stops the chain before any later
step runs.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from . import anims
from .blender_proc import ProgressCallback, StepRunner
from .cache import ArtifactCache, CacheEntry
from .clients.blender_session import BlenderSessionClient
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
)

if TYPE_CHECKING:
    from nmg_game_dev.godot.runner import GodotRunner

# The nmg_game_dev.godot modules are imported where they are used: they import
# nmg_game_dev.pipeline.errors, so importing them while this package initializes would be circular.

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
        suffixes: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Load the result into the session unless the session changed, and report which.

        ``suffixes`` names the collections to replace (``("", "_High")`` for reduce); None keeps
        the add-on default of ``("", "_Mobile")``.
        """
        ...


class FinalizeSessionChangedError(PipelineError):
    """``finalize.session_changed``: the session changed during the run, so nothing was loaded.

    The run still imported into Godot.  ``result`` carries the full ``FinalizeResult``, and the
    result ``.blend`` is named in the message.
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
    """Optional client overrides.  Real clients are created on first use when left unset.

    ``godot`` runs ``godot --headless``.  When it is unset, the first Godot step resolves the binary
    (``GODOT_BIN``, then ``godot`` on PATH, then the macOS app) and raises ``godot.not_found`` when
    there is none.
    """

    blender: BlenderSession | None = None
    godot: GodotRunner | None = None


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
    load_back_needed = (
        request.blend is None and "import_godot" in chain and not session_holds_result
    )

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
        if step == "import_godot" and load_back_needed:
            load = _load_back(run, asset_hash=asset_hash, result_blend=last_blend)
            if load.get("loaded") is True:
                loaded_back = True
                post_hash = str(load.get("hash", ""))
            else:
                refused = load

        if spec.per_clip:
            # Per-clip steps keep their own cache and leave the input hash unchanged (#138).  Clips
            # are read from this run's checkpoint: the asset hash does not cover actions, so after a
            # clip-only change the mesh steps restore a cached variants .blend holding the old
            # actions.  The variants step changes only meshes, so SK_<Name> is the same in both.
            clip_outputs = _run_per_clip(run, step, outputs_by_step, checkpoint, force=force)
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
    desktop, mobile = _resource_paths(outputs_by_step)
    final = FinalizeResult(
        steps=results,
        desktop_resource_path=desktop,
        mobile_resource_path=mobile,
        loaded_back=loaded_back,
        result_blend=result_blend,
        animations=_animations_result(outputs_by_step),
    )

    if tuple(chain) == STEP_ORDER:
        record = {
            "steps": keys,
            "settings": current_settings,
            "result_blend": result_blend,
            "resource_paths": {"desktop": desktop, "mobile": mobile},
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
    return checkpoint_session(
        collection=run.request.collection,
        blend=run.request.blend,
        job_dir=run.job_dir,
        runner=run.runner,
        clients=run.clients,
    )


def checkpoint_session(
    *,
    collection: str,
    blend: Path | None,
    job_dir: Path,
    runner: StepRunner,
    clients: FinalizeClients,
) -> tuple[str, Path]:
    """Save the collection's checkpoint copy and return its content hash and path.

    ``blend`` None saves a copy of the open session through the Blender session client.  A saved
    ``.blend`` is copied and hashed headlessly.  Shared by finalize and reduce (#139).
    """
    checkpoint = job_dir / "checkpoint.blend"
    if blend is None:
        if clients.blender is None:
            clients.blender = BlenderSessionClient()
        asset_hash = clients.blender.checkpoint(collection=collection, path=checkpoint)
        return asset_hash, checkpoint
    if not blend.is_file():
        raise PipelineError(
            code="finalize.blend_not_found",
            message=f"The .blend to finalize does not exist: {blend}",
            remediation="Pass the path of a saved .blend with --blend, or omit it to finalize the "
            "open session.",
            stage="finalize",
        )
    job_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(blend, checkpoint)
    return runner.hash(job_dir=job_dir, in_blend=checkpoint), checkpoint


def _run_step(
    run: _Run,
    step: StepName,
    outputs_by_step: dict[str, dict[str, Any]],
    last_blend: Path,
) -> dict[str, Any]:
    if step == "import_godot":
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
    checkpoint: Path,
    *,
    force: bool,
) -> dict[str, Any]:
    if run.request.asset_class == "terrain":
        # A terrain has no rig, so both clip steps are no-ops: no Blender probe, no Godot call.
        if step == "export_anims":
            return {"clips": [], "content_dir": None, "sidecar": None}
        return {"clips": [], "content_dir": None, "stale": [], "compatible": []}
    if step == "export_anims":
        return anims.run_export_anims(
            run.request,
            cache=run.cache,
            job_dir=run.job_dir,
            runner=run.runner,
            in_blend=checkpoint,
            force=force,
            on_progress=_progress_callback(run, step),
        )
    return anims.run_import_anims(
        run.request,
        cache=run.cache,
        job_dir=run.job_dir,
        exported=outputs_by_step["export_anims"]["clips"],
        client=lambda: _godot(run),
        force=force,
    )


def _godot(run: _Run) -> GodotRunner:
    """Return the injected Godot runner, or resolve the binary on first use."""
    from nmg_game_dev.godot import binary as godot_binary
    from nmg_game_dev.godot.runner import SubprocessGodotRunner

    if run.clients.godot is None:
        binary = godot_binary.resolve_godot(default_app=godot_binary.DEFAULT_GODOT_APP_BINARY)
        run.clients.godot = SubprocessGodotRunner(binary)
    return run.clients.godot


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
    from nmg_game_dev.godot.import_asset import import_variants
    from nmg_game_dev.godot.project import find_project
    from nmg_game_dev.godot.terrain import import_terrain

    request = run.request
    runner = _godot(run)
    project = find_project(request.export_root)
    export = outputs_by_step["export"]
    folders = {variant: Path(str(export["variants"][variant]["dir"])) for variant in VARIANTS}
    sidecar = _read_sidecar(Path(str(export["sidecar"])))
    imports: dict[str, dict[str, Any]]
    if request.asset_class == "terrain":
        imports = import_terrain(
            runner, project, name=request.collection, variant_dirs=folders, sidecar=sidecar
        )
    else:
        imports = import_variants(
            runner, project, name=request.collection, variant_dirs=folders, sidecar=sidecar
        )
    return {
        "desktop_resource_path": imports["Desktop"]["resource_path"],
        "mobile_resource_path": imports["Mobile"]["resource_path"],
        "imports": imports,
    }


def _read_sidecar(path: Path) -> dict[str, Any]:
    """Return the export's ``nmg-variants.json``; a missing or unreadable one fails the import."""
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PipelineError(
            code="import_godot.mismatch",
            message=f"The export sidecar {path} cannot be read: {error}",
            remediation="Rerun the export step so nmg-variants.json is written, then rerun "
            "import_godot.",
            stage="import_godot",
        ) from error
    return payload if isinstance(payload, dict) else {}


def _load_back(run: _Run, *, asset_hash: str, result_blend: Path) -> dict[str, Any]:
    if run.clients.blender is None:
        run.clients.blender = BlenderSessionClient()
    _emit(run, state="running", step="import_godot", progress=None, message="loading back")
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


def _resource_paths(outputs_by_step: dict[str, dict[str, Any]]) -> tuple[str | None, str | None]:
    imported = outputs_by_step.get("import_godot")
    if imported is None:
        return None, None
    return str(imported["desktop_resource_path"]), str(imported["mobile_resource_path"])


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
