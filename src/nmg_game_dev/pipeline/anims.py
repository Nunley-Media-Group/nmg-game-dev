"""Per-clip export and import for the finalize steps ``export_anims`` and ``import_anims`` (#138).

Each step is cached per clip, not as a whole. A clip's export key is
``cache.key("export_anims", clip hash, clip_settings_hash)``. Its import key is
``cache.key("import_anims", export output hash, clip_settings_hash)``. Changing one clip therefore
re-exports and re-imports only that clip, and the mesh steps' keys do not move.

``run_export_anims`` probes the rig in one Blender run, serves the clips it can from the cache,
exports the rest in one more Blender run, and writes ``nmg-animations.json`` beside the clip
``.glb`` files. ``run_import_anims`` hands the clips that missed the cache to
``nmg_game_dev.godot.anims``: it writes their ``animation_library`` import settings, runs one
headless ``--import``, and probes only those clips, so one changed clip re-imports only that clip.
It lists stale clip files and checks each ``compatible_with`` Desktop skeleton. A call with no
clips and no ``compatible_with`` runs no Godot at all.

Failures raise ``PipelineError`` with a stable code. A clip's cache entry is written only after the
clip has passed its checks.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from .blender_proc import StepRunner
from .cache import ArtifactCache, CacheEntry
from .errors import PipelineError
from .request import FinalizeRequest
from .steps import (
    StepName,
    clip_settings_hash,
    envelope_outputs,
    glb_path,
    output_hash,
)

if TYPE_CHECKING:
    from nmg_game_dev.godot.runner import GodotRunner

# nmg_game_dev.godot is imported where it is used: it imports nmg_game_dev.pipeline.errors, so a
# module-level import here would be circular while the pipeline package initializes.

ANIMATIONS_DIR: Final = "Animations"
SIDECAR_NAME: Final = "nmg-animations.json"
ARMATURE_NAME: Final = "Armature"
_EXPORT: Final = "export_anims"
_IMPORT: Final = "import_anims"
_SIDECAR_CLIP_FIELDS: Final = (
    "name",
    "file",
    "frame_start",
    "frame_end",
    "frame_count",
    "fps",
    "source",
)
GodotRunnerFactory = Callable[[], "GodotRunner"]
_ImportPlan = tuple[Mapping[str, Any], str, CacheEntry | None]


def animations_dir(request: FinalizeRequest) -> Path:
    """Return the clip folder: ``<export_root>/<Category>/<Name>/Animations``."""
    return request.export_root / request.category / request.collection / ANIMATIONS_DIR


def resource_path(request: FinalizeRequest, path: Path) -> str:
    """Return ``path`` as a ``res://`` path, or as a plain path when no Godot project holds it."""
    from nmg_game_dev.godot.project import find_project, res_path

    try:
        return res_path(find_project(request.export_root), path)
    except (PipelineError, ValueError):
        return path.as_posix()


def content_path(request: FinalizeRequest) -> str:
    """Return the Animations folder as a resource path: ``res://.../<Category>/<Name>/Animations``."""
    return resource_path(request, animations_dir(request))


def clip_file_name(request: FinalizeRequest, clip: str) -> str:
    """Return the clip file the add-on writes: ``A_<Name>_<Clip>.glb``."""
    return f"A_{request.collection}_{clip}.glb"


def clip_asset_path(request: FinalizeRequest, clip: str, file: str | None = None) -> str:
    """Return the clip's resource path: ``res://.../Animations/A_<Name>_<Clip>.glb``."""
    return resource_path(request, animations_dir(request) / (file or clip_file_name(request, clip)))


def _compatible_scene(request: FinalizeRequest, item: str) -> Path:
    """Return the Desktop scene of a ``<Category>/<Name>`` compatible character."""
    category, name = item.split("/", 1)
    return request.export_root / category / name / "Desktop" / f"{name}.glb"


def run_export_anims(
    request: FinalizeRequest,
    *,
    cache: ArtifactCache,
    job_dir: Path,
    runner: StepRunner,
    in_blend: Path,
    force: bool,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Probe, cache-check, and export the rig's clips, then write the sidecar. Return the outputs.

    The outputs are ``{clips, content_dir, sidecar}``. Each clip is ``{name, file, asset_path,
    frame_start, frame_end, frame_count, fps, source, output_hash, cache_hit}``. With no clips,
    ``content_dir`` and ``sidecar`` are ``None``, and nothing is written.
    """
    probe = _blender(runner, _EXPORT, job_dir, in_blend, {"mode": "probe"}, on_progress)
    probed = [dict(clip) for clip in _list(probe.get("clips"))]
    invalid = sorted(str(clip["name"]) for clip in probed if clip.get("valid_name") is not True)
    if invalid:
        raise PipelineError(
            code="finalize.clip_name_invalid",
            message=f"Clip names {', '.join(invalid)} do not match ^[A-Za-z][A-Za-z0-9_]*$, so "
            "nothing was exported.",
            remediation="Rename each action to start with a letter and use only letters, digits, "
            "and underscores, then rerun finalize.",
            stage=_EXPORT,
        )
    if not probed:
        return {"clips": [], "content_dir": None, "sidecar": None}

    settings = clip_settings_hash(_EXPORT, request, options=str(probe.get("options", "")))
    folder = animations_dir(request)
    done: dict[str, dict[str, Any]] = {}
    missing: dict[str, str] = {}
    for clip in sorted(probed, key=lambda item: str(item["name"])):
        name = str(clip["name"])
        key = cache.key(_EXPORT, str(clip["hash"]), settings)
        entry = None if force else cache.get(key, job_dir=job_dir)
        if entry is None:
            missing[name] = key
            continue
        file_name = str(entry.outputs["file"])
        if not (folder / file_name).exists():
            cache.restore(key, file_name, folder / file_name)
        done[name] = {**entry.outputs, "output_hash": entry.output_hash, "cache_hit": True}

    if missing:
        exported = _blender(
            runner,
            _EXPORT,
            job_dir,
            in_blend,
            {"mode": "export", "clips": sorted(missing)},
            on_progress,
        )
        records = {str(record.get("name")): dict(record) for record in _list(exported.get("clips"))}
        for name, key in missing.items():
            record = records.get(name)
            if record is None or any(field not in record for field in _SIDECAR_CLIP_FIELDS):
                raise PipelineError(
                    code="export_anims.bad_envelope",
                    message=f"The export step returned no complete record for clip {name}.",
                    remediation="Read the Blender log for the export_anims step and rerun.",
                    stage=_EXPORT,
                )
            outputs = {field: record[field] for field in _SIDECAR_CLIP_FIELDS}
            blobs = {str(outputs["file"]): folder / str(outputs["file"])}
            digest = output_hash(_EXPORT, outputs, blobs, job_dir=job_dir)
            cache.put(
                key, step=_EXPORT, output_hash=digest, outputs=outputs, blobs=blobs, job_dir=job_dir
            )
            done[name] = {**outputs, "output_hash": digest, "cache_hit": False}

    clips = [_clip_record(request, done[name]) for name in sorted(done)]
    sidecar = _write_sidecar(request, clips)
    return {"clips": clips, "content_dir": content_path(request), "sidecar": str(sidecar)}


def run_import_anims(
    request: FinalizeRequest,
    *,
    cache: ArtifactCache,
    job_dir: Path,
    exported: Sequence[Mapping[str, Any]],
    client: GodotRunnerFactory,
    force: bool,
) -> dict[str, Any]:
    """Import the clips that changed, verify them, and check the compatible skeletons.

    The outputs are ``{clips, content_dir, stale, compatible}``. Each clip is ``{name, asset_path,
    cache_hit}``. ``stale`` lists clip ``.glb`` files that are no longer clips; they are never
    deleted. ``compatible`` lists the compatible Desktop scenes whose skeletons hold every bone the
    clips animate. ``client`` is called only when there is Godot work: a changed clip or a
    ``compatible_with`` check.
    """
    from nmg_game_dev.godot.anims import (
        ClipPlan,
        check_compatible,
        has_library_importer,
        import_clips,
        skeleton_not_found,
        verify_clips,
    )
    from nmg_game_dev.godot.project import find_project

    targets = [(item, _compatible_scene(request, item)) for item in request.compatible_with]
    if not exported and not targets:
        return {"clips": [], "content_dir": None, "stale": [], "compatible": []}

    own = glb_path(request, "Desktop")
    if not own.is_file():
        raise skeleton_not_found(f"{request.category}/{request.collection}", str(own), own=True)
    for label, scene in targets:
        if not scene.is_file():
            raise skeleton_not_found(label, str(scene))

    settings = clip_settings_hash(_IMPORT, request)
    folder = animations_dir(request)
    plans: list[_ImportPlan] = []
    for clip in exported:
        key = cache.key(_IMPORT, str(clip["output_hash"]), settings)
        entry = None if force else cache.get(key, job_dir=job_dir)
        file = folder / str(clip["file"])
        if entry is not None and not has_library_importer(file):
            # The .import was lost, so Godot would import the clip as a scene: import it again.
            entry = None
        plans.append((clip, key, entry))

    changed = [
        ClipPlan(
            name=str(clip["name"]),
            file=folder / str(clip["file"]),
            fps=float(clip["fps"]),
            expected_frames=int(clip["frame_end"]) - int(clip["frame_start"]),
        )
        for clip, _key, entry in plans
        if entry is None
    ]
    project = find_project(request.export_root)
    bones: dict[str, list[str]] = {}
    compatible: list[str] = []
    if changed or targets:
        probe = import_clips(
            client(), project, clips=changed, skeletons=[scene for _label, scene in targets]
        )
        bones = verify_clips(changed, probe["clips"])
        required = set(chain.from_iterable(bones.values()))
        for _clip, _key, entry in plans:
            if entry is not None:
                required.update(str(bone) for bone in _list(entry.outputs.get("bones")))
        compatible = check_compatible(project, sorted(required), targets, probe["skeletons"])

    clips: list[dict[str, Any]] = []
    for clip, key, entry in plans:
        name = str(clip["name"])
        asset_path = clip_asset_path(request, name, str(clip["file"]))
        if entry is None:
            outputs = {"name": name, "asset_path": asset_path, "bones": bones.get(name, [])}
            digest = output_hash(_IMPORT, outputs, {}, job_dir=job_dir)
            cache.put(
                key, step=_IMPORT, output_hash=digest, outputs=outputs, blobs={}, job_dir=job_dir
            )
        clips.append({"name": name, "asset_path": asset_path, "cache_hit": entry is not None})
    current = {str(clip["file"]) for clip in exported}
    stale = [
        resource_path(request, path)
        for path in sorted(folder.glob(f"A_{request.collection}_*.glb"))
        if path.name not in current
    ]
    return {
        "clips": clips,
        "content_dir": content_path(request) if clips else None,
        "stale": stale,
        "compatible": compatible,
    }


def clips_all_cached(outputs: Mapping[str, Any]) -> bool:
    """Return ``True`` only when every clip was served from the cache.  Vacuously true with none."""
    return all(clip.get("cache_hit") is True for clip in _list(outputs.get("clips")))


def _blender(
    runner: StepRunner,
    step: StepName,
    job_dir: Path,
    in_blend: Path,
    inputs: Mapping[str, Any],
    on_progress: Callable[[dict[str, Any]], None] | None,
) -> dict[str, Any]:
    envelope = runner.run_step(
        step,
        job_dir=job_dir,
        in_blend=in_blend,
        inputs=dict(inputs),
        on_progress=on_progress,
    )
    return envelope_outputs(step, envelope)


def _clip_record(request: FinalizeRequest, item: Mapping[str, Any]) -> dict[str, Any]:
    name = str(item["name"])
    return {
        "name": name,
        "file": str(item["file"]),
        "asset_path": clip_asset_path(request, name, str(item["file"])),
        "frame_start": int(item["frame_start"]),
        "frame_end": int(item["frame_end"]),
        "frame_count": int(item["frame_count"]),
        "fps": float(item["fps"]),
        "source": item["source"],
        "output_hash": str(item["output_hash"]),
        "cache_hit": bool(item["cache_hit"]),
    }


def _write_sidecar(request: FinalizeRequest, clips: Sequence[Mapping[str, Any]]) -> Path:
    folder = animations_dir(request)
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "asset": request.collection,
        "armature": ARMATURE_NAME,
        "skeleton": resource_path(request, glb_path(request, "Desktop")),
        "clips": [
            {
                "name": clip["name"],
                "file": clip["file"],
                "asset_path": clip["asset_path"],
                "frame_start": clip["frame_start"],
                "frame_end": clip["frame_end"],
                "frame_count": clip["frame_count"],
                "fps": clip["fps"],
                "source": clip["source"],
            }
            for clip in clips
        ],
    }
    path = folder / SIDECAR_NAME
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []
