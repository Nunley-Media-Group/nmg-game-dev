"""Per-clip export and import for the finalize steps ``export_anims`` and ``import_anims`` (#138).

Each step is cached per clip, not as a whole. A clip's export key is
``cache.key("export_anims", clip hash, clip_settings_hash)``. Its import key is
``cache.key("import_anims", export output hash, clip_settings_hash)``. Changing one clip therefore
re-exports and re-imports only that clip, and the mesh steps' keys do not move.

``run_export_anims`` probes the rig in one Blender run, serves the clips it can from the cache,
exports the rest in one more Blender run, and writes ``nmg-animations.json`` beside the FBX files.
``run_import_anims`` sends one UE Python call. It imports the clips that missed the cache, verifies
every clip against the sidecar, lists stale sequences, and registers compatible skeletons. A call
with no clips and no ``compatible_with`` makes no Unreal call at all.

Failures raise ``PipelineError`` with a stable code. A clip's cache entry is written only after the
clip has passed its checks.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from nmg_game_dev.unreal.import_anims import build_anim_import_code
from nmg_game_dev.unreal.import_asset import UnrealPythonClient, parse_nmg_result

from .blender_proc import StepRunner
from .cache import ArtifactCache
from .errors import PipelineError
from .request import FinalizeRequest
from .steps import (
    StepName,
    clip_settings_hash,
    desktop_skeleton_path,
    envelope_outputs,
    output_hash,
)

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
_IMPORT_REMEDIATION: Final = (
    "Read the UE error in the message, confirm the clip FBX files exist in the Animations folder "
    "and that the editor is idle, then rerun import_anims."
)
_MISMATCH_REMEDIATION: Final = (
    "Re-export the clip and rerun import_anims with force, so the AnimSequence is rebuilt from "
    "the current FBX."
)

UnrealClientFactory = Callable[[], UnrealPythonClient]
_ImportPlan = tuple[Mapping[str, Any], str, bool]


def animations_dir(request: FinalizeRequest) -> Path:
    """Return the clip FBX folder: ``<export_root>/<Category>/<Name>/Animations``."""
    return request.export_root / request.category / request.collection / ANIMATIONS_DIR


def content_path(request: FinalizeRequest) -> str:
    """Return the UE folder for the clip AnimSequences: ``/Game/<Category>/<Name>/Animations``."""
    return f"/Game/{request.category}/{request.collection}/{ANIMATIONS_DIR}"


def clip_asset_name(request: FinalizeRequest, clip: str) -> str:
    """Return the AnimSequence name for ``clip``: ``A_<Name>_<Clip>``."""
    return f"A_{request.collection}_{clip}"


def clip_asset_path(request: FinalizeRequest, clip: str) -> str:
    """Return the AnimSequence path for ``clip``: ``/Game/<Category>/<Name>/Animations/A_..``."""
    return f"{content_path(request)}/{clip_asset_name(request, clip)}"


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
    client: UnrealClientFactory,
    force: bool,
) -> dict[str, Any]:
    """Import the clips that missed the cache, verify every clip, and register compatible skeletons.

    The outputs are ``{clips, content_dir, stale, compatible}``. Each clip is ``{name, asset_path,
    cache_hit}``. ``stale`` lists AnimSequences that are no longer clips, and it never deletes them.
    ``compatible`` lists the registered skeletons. ``client`` is called only when there is work.
    """
    compatible = list(request.compatible_with)
    if not exported and not compatible:
        return {"clips": [], "content_dir": None, "stale": [], "compatible": []}

    settings = clip_settings_hash(_IMPORT, request)
    plans: list[_ImportPlan] = []
    for clip in exported:
        key = cache.key(_IMPORT, str(clip["output_hash"]), settings)
        hit = not force and cache.get(key, job_dir=job_dir) is not None
        plans.append((clip, key, hit))

    code = build_anim_import_code(_params(request, plans, compatible))
    output = client().execute_python_code(code)
    result = _parse(output)
    _raise_blocked(request, result)
    if result.get("error"):
        raise PipelineError(
            code="import_anims.failed",
            message=f"UE import of the {request.collection} clips failed: {result['error']}",
            remediation=_IMPORT_REMEDIATION,
            stage=_IMPORT,
        )
    reported = result.get("clips")
    measured: dict[str, Any] = reported if isinstance(reported, dict) else {}
    _verify(request, plans, measured)

    clips: list[dict[str, Any]] = []
    for clip, key, hit in plans:
        name = str(clip["name"])
        if not hit:
            outputs = {"name": name, "asset_path": clip_asset_path(request, name)}
            digest = output_hash(_IMPORT, outputs, {}, job_dir=job_dir)
            cache.put(
                key, step=_IMPORT, output_hash=digest, outputs=outputs, blobs={}, job_dir=job_dir
            )
        clips.append({"name": name, "asset_path": clip_asset_path(request, name), "cache_hit": hit})
    return {
        "clips": clips,
        "content_dir": content_path(request) if clips else None,
        "stale": [str(path) for path in _list(result.get("stale"))],
        "compatible": [str(path) for path in _list(result.get("compatible"))],
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
        "asset_path": clip_asset_path(request, name),
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
        "skeleton": desktop_skeleton_path(request),
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


def _params(
    request: FinalizeRequest,
    plans: Sequence[_ImportPlan],
    compatible: Sequence[str],
) -> dict[str, Any]:
    clips = []
    for clip, _key, hit in plans:
        name = str(clip["name"])
        clips.append(
            {
                "name": name,
                "asset_name": clip_asset_name(request, name),
                "asset_path": clip_asset_path(request, name),
                "file": str(animations_dir(request) / str(clip["file"])),
                "import": not hit,
                "expected_frame_count": int(clip["frame_count"]),
            }
        )
    targets = []
    for item in compatible:
        category, name = item.split("/", 1)
        targets.append(
            {"name": item, "skeleton": f"/Game/{category}/{name}/Desktop/SM_{name}_Skeleton"}
        )
    return {
        "name": request.collection,
        "anim_dir": content_path(request),
        "skeleton": desktop_skeleton_path(request),
        "prefix": f"A_{request.collection}_",
        "clips": clips,
        "compatible": targets,
    }


def _parse(output: str) -> dict[str, Any]:
    try:
        return parse_nmg_result(output)
    except PipelineError as error:
        raise PipelineError(
            code="import_anims.failed",
            message=error.message,
            remediation=_IMPORT_REMEDIATION,
            stage=_IMPORT,
        ) from error


def _raise_blocked(request: FinalizeRequest, result: Mapping[str, Any]) -> None:
    blocked = result.get("blocked")
    if not isinstance(blocked, dict):
        return
    own = desktop_skeleton_path(request)
    target = str(blocked.get("target", ""))
    if blocked.get("code") == "skeleton_mismatch":
        bones = ", ".join(str(bone) for bone in _list(blocked.get("bones")))
        raise PipelineError(
            code="finalize.skeleton_mismatch",
            message=f"{target} has different bone names from {own}: {bones}.",
            remediation="Only register characters rigged with the same bone names.",
            stage=_IMPORT,
        )
    if target == own:
        remediation = (
            f"Run import_ue for {request.category}/{request.collection} first, then rerun "
            "import_anims."
        )
    else:
        remediation = (
            f"Finalize {target} first so its Desktop skeleton exists, or remove it from "
            "compatible_with, then rerun import_anims."
        )
    raise PipelineError(
        code="finalize.skeleton_not_found",
        message=f"The skeleton {blocked.get('path', target)} does not exist in the project.",
        remediation=remediation,
        stage=_IMPORT,
    )


def _verify(
    request: FinalizeRequest,
    plans: Sequence[_ImportPlan],
    measured: Mapping[str, Any],
) -> None:
    """Compare each clip's measured skeleton and key count with the sidecar values."""
    expected_skeleton = desktop_skeleton_path(request)
    for clip, _key, _hit in plans:
        name = str(clip["name"])
        seen = measured.get(name)
        if not isinstance(seen, dict):
            raise PipelineError(
                code="import_anims.clip_mismatch",
                message=f"Clip {name} has no measured AnimSequence after import_anims.",
                remediation=_MISMATCH_REMEDIATION,
                stage=_IMPORT,
            )
        checks = (
            ("frame count", int(clip["frame_count"]), seen.get("frame_count")),
            ("skeleton", expected_skeleton, seen.get("skeleton")),
        )
        for field, expected, actual in checks:
            if actual != expected:
                raise PipelineError(
                    code="import_anims.clip_mismatch",
                    message=f"Clip {name} {field}: expected {expected}, measured {actual}.",
                    remediation=_MISMATCH_REMEDIATION,
                    stage=_IMPORT,
                )


def _list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []
