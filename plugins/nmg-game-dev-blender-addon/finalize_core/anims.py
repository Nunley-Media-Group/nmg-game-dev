"""Per-clip animation probe and export for the finalize ``export_anims`` step (#138).

``probe`` lists the clips held by ``SK_<Name>`` with a content hash for each, so the host can
decide which clips miss its cache.  ``export_clips`` writes one armature-only GLB per requested
clip, ``A_<Name>_<Clip>.glb``, holding exactly that clip.  Both touch Blender data and run only
inside the headless ``finalize_entry.py`` process.

A clip's name is its action's name minus an optional ``@SK_<Name>`` suffix, so one .blend can hold
several rigs that each have an ``Idle``.  The clip set is the rig's provenance clips that resolve to
actions, plus every action assigned to ``SK_<Name>`` or held in its NLA tracks.  Unrelated actions
in the file are never exported.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import bpy

from ..variants_core.assets import ARMATURE_EXPORT_NAME, asset_armature, require_armature_name_free
from ..variants_core.export import RIG_GLB_OPTIONS

PROVENANCE_KEY: Final = "nmg_animations"
CLIP_NAME_PATTERN: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
ANIMATIONS_DIR: Final = "Animations"

# The rigged mesh export's skeleton and axis settings, so a clip rides the same skeleton as the
# mesh.  Only the animation settings differ: the armature's one assigned action, sampled on every
# frame with every bone kept, and slid so its first key is at time 0: Godot keeps key times as
# written, so its animation length times fps is then frame_end - frame_start.  Imported, never
# copied, so they cannot drift.
ANIM_EXPORT_OPTIONS: Final[dict[str, Any]] = {
    **RIG_GLB_OPTIONS,
    "export_animations": True,
    "export_animation_mode": "ACTIVE_ACTIONS",
    "export_force_sampling": True,
    "export_frame_range": False,
    "export_anim_slide_to_zero": True,
    "export_optimize_animation_size": False,
    "export_optimize_animation_keep_anim_armature": True,
    "export_bake_animation": False,
}


class AnimError(Exception):
    """A clip step failure that becomes a failed envelope with this code and remediation."""

    def __init__(self, code: str, message: str, remediation: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.remediation = remediation


@dataclass(frozen=True)
class ClipResolution:
    """The rig's clips by bare clip name, and the actions that could not become clips.

    ``clips`` maps a clip name to its action.  ``rig_mismatch`` lists, sorted, the rig's actions
    whose ``@`` suffix names another rig.  ``duplicates`` maps each clip name that two distinct
    actions give to those action names, sorted; such a clip is left out of ``clips``.
    """

    clips: dict[str, bpy.types.Action]
    rig_mismatch: list[str]
    duplicates: dict[str, list[str]]


def split_action_name(action_name: str) -> tuple[str, str | None]:
    """Split an action name at its first ``@``: return ``(bare, suffix)``, None when no ``@``."""
    bare, separator, suffix = action_name.partition("@")
    return (bare, suffix if separator else None)


def resolve(collection_name: str) -> ClipResolution:
    """Resolve the rig's actions to clips: provenance clips first, then every action it holds.

    A provenance clip ``<Clip>`` takes the action ``<Clip>@SK_<Name>``, or else one named
    ``<Clip>``.  A held action's clip is its name minus an ``@SK_<Name>`` suffix; an action whose
    suffix names another rig is a mismatch and is not a clip.  One action reached twice is one
    clip; two distinct actions for one clip name are a duplicate.
    """
    rig = asset_armature(collection_name)
    if rig is None:
        return ClipResolution(clips={}, rig_mismatch=[], duplicates={})
    own_suffix = f"SK_{collection_name}"
    offers: dict[str, dict[str, bpy.types.Action]] = {}
    for clip in provenance_of(rig):
        action = bpy.data.actions.get(f"{clip}@{own_suffix}")
        if action is None:
            action = bpy.data.actions.get(clip)
        if action is not None:
            offers.setdefault(clip, {})[action.name] = action
    held: list[bpy.types.Action] = []
    data = rig.animation_data
    if data is not None:
        if data.action is not None:
            held.append(data.action)
        for track in data.nla_tracks:
            for strip in track.strips:
                if strip.action is not None:
                    held.append(strip.action)
    mismatch: set[str] = set()
    for action in held:
        bare, suffix = split_action_name(action.name)
        if suffix is not None and suffix != own_suffix:
            mismatch.add(action.name)
        else:
            offers.setdefault(bare, {})[action.name] = action
    clips: dict[str, bpy.types.Action] = {}
    duplicates: dict[str, list[str]] = {}
    for clip, candidates in offers.items():
        if len(candidates) == 1:
            clips[clip] = next(iter(candidates.values()))
        else:
            duplicates[clip] = sorted(candidates)
    return ClipResolution(clips=clips, rig_mismatch=sorted(mismatch), duplicates=duplicates)


def probe(collection_name: str) -> dict[str, Any]:
    """Return ``{clips, rig_mismatch, duplicates, options}`` for the collection's rig.

    ``clips`` is ``[{name, hash, valid_name}]`` under each clip's bare name.  ``rig_mismatch`` lists
    the actions whose ``@`` suffix names another rig, and ``duplicates`` lists ``{name, actions}``
    for each clip two actions give; the host refuses the export for either.  ``options``
    fingerprints ``ANIM_EXPORT_OPTIONS``; the host folds it into the export cache key.  A collection
    with no rig, or a rig with no clips, gives empty lists.
    """
    rig = asset_armature(collection_name)
    provenance = provenance_of(rig) if rig is not None else {}
    resolution = resolve(collection_name)
    clips: list[dict[str, Any]] = []
    for name in sorted(resolution.clips):
        clips.append(
            {
                "name": name,
                "hash": clip_hash(rig, name, resolution.clips[name], provenance.get(name)),
                "valid_name": valid_clip_name(name),
            }
        )
    duplicates = [
        {"name": name, "actions": actions}
        for name, actions in sorted(resolution.duplicates.items())
    ]
    return {
        "clips": clips,
        "rig_mismatch": resolution.rig_mismatch,
        "duplicates": duplicates,
        "options": options_fingerprint(),
    }


def resolve_clips(collection_name: str) -> list[bpy.types.Action]:
    """Return the rig's clip actions sorted by clip name."""
    clips = resolve(collection_name).clips
    return [clips[name] for name in sorted(clips)]


def provenance_of(rig: bpy.types.Object) -> dict[str, dict[str, Any]]:
    """Return the rig's ``nmg_animations`` provenance keyed by clip name, or ``{}``."""
    raw = rig.get(PROVENANCE_KEY, "{}")
    try:
        data = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(name): entry for name, entry in data.items() if isinstance(entry, dict)}


def valid_clip_name(name: str) -> bool:
    """Return ``True`` when ``name`` may be a clip name: ``^[A-Za-z][A-Za-z0-9_]*$``."""
    return CLIP_NAME_PATTERN.match(name) is not None


def options_fingerprint() -> str:
    """Return the SHA-256 of ``ANIM_EXPORT_OPTIONS`` in canonical form."""
    return _digest(_canonical(ANIM_EXPORT_OPTIONS))


def clip_hash(
    rig: bpy.types.Object | None,
    clip_name: str,
    action: bpy.types.Action,
    provenance: Mapping[str, Any] | None,
) -> str:
    """Return the SHA-256 of everything a clip's exported GLB depends on.

    The payload is the bare clip name, every F-curve through the action's slots (keyframe points,
    handles, interpolation, and modifiers), the rig's bones with parents and rest matrices, the
    provenance entry, and the scene's frame rate.  A change to any of them changes the hash.
    """
    scene = bpy.context.scene
    slot = _slot_of(action, rig)
    payload: dict[str, Any] = {
        "clip": clip_name,
        "curves": _curve_payload(_fcurves(action, slot)),
        "rig": _rig_payload(rig),
        "provenance": dict(provenance) if provenance is not None else None,
        "fps": scene.render.fps,
        "fps_base": scene.render.fps_base,
    }
    return _digest(_canonical(payload))


def export_clips(
    collection_name: str,
    names: Sequence[str],
    out_dir: Path,
) -> list[dict[str, Any]]:
    """Write ``A_<Name>_<Clip>.glb`` for each named clip into ``out_dir`` and describe each one.

    Each record is ``{name, file, frame_start, frame_end, frame_count, fps, source}``.  ``source``
    is the clip's recorded provenance source, or ``"authored"``.  A rig-mismatched action, a clip
    two actions give, or an invalid name raises before anything is written.  The rig's name,
    action, slot, and NLA mute states are restored afterwards, even on failure.
    """
    rig = asset_armature(collection_name)
    if rig is None:
        raise AnimError(
            "export_anims.rig_missing",
            f"SK_{collection_name} is not an armature in {collection_name}.",
            f"Run rig_humanoid for {collection_name} before exporting its clips.",
        )
    resolution = resolve(collection_name)
    if resolution.rig_mismatch:
        raise AnimError(
            "finalize.clip_rig_mismatch",
            f"Actions {', '.join(resolution.rig_mismatch)} on SK_{collection_name} carry an @ "
            "suffix for another rig, so nothing was exported.",
            f"Rename each action to <Clip>@SK_{collection_name} for this rig, or remove the "
            "suffix, then rerun finalize.",
        )
    if resolution.duplicates:
        clauses = "; ".join(
            f"Clip {clip} comes from more than one action on SK_{collection_name} "
            f"({', '.join(sources)})"
            for clip, sources in sorted(resolution.duplicates.items())
        )
        raise AnimError(
            "finalize.clip_name_duplicate",
            f"{clauses}, so nothing was exported.",
            f"Keep one action per clip on SK_{collection_name}: delete or rename the extra "
            "action, then rerun finalize.",
        )
    actions = resolution.clips
    for name in names:
        if name not in actions:
            raise AnimError(
                "export_anims.clip_not_found",
                f"{name} is not a clip on SK_{collection_name}.",
                "Rerun the probe, then export only clips the rig holds.",
            )
        if not valid_clip_name(name):
            raise AnimError(
                "finalize.clip_name_invalid",
                f"The action {name} does not match ^[A-Za-z][A-Za-z0-9_]*$.",
                "Rename the action to start with a letter and use only letters, digits, and "
                "underscores, then rerun.",
            )
    require_armature_name_free(rig)
    provenance = provenance_of(rig)
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for name in names:
        file_name = f"A_{collection_name}_{name}.glb"
        measured = _export_one(rig, actions[name], out_dir / file_name)
        entry = provenance.get(name)
        source = entry.get("source") if entry is not None else None
        records.append(
            {
                "name": name,
                "file": file_name,
                **measured,
                "source": source if isinstance(source, dict) else "authored",
            }
        )
    return records


def _export_one(
    rig: bpy.types.Object,
    action: bpy.types.Action,
    path: Path,
) -> dict[str, Any]:
    """Export one clip from ``rig`` to ``path`` and return its measured frame range and fps."""
    scene = bpy.context.scene
    data = rig.animation_data_create()
    slot = _slot_of(action, rig)
    saved_name = rig.name
    saved_action = data.action
    saved_slot = getattr(data, "action_slot", None)
    saved_mutes = [(track, track.mute) for track in data.nla_tracks]
    saved_pose = [_pose_of(bone) for bone in rig.pose.bones]
    saved_range = (scene.frame_start, scene.frame_end)
    start, end = action.frame_range
    frame_start, frame_end = round(start), round(end)
    try:
        rig.name = ARMATURE_EXPORT_NAME
        for track in data.nla_tracks:
            track.mute = True
        data.action = action
        if slot is not None and hasattr(data, "action_slot"):
            data.action_slot = slot
        scene.frame_start, scene.frame_end = frame_start, frame_end
        _select_only([rig])
        bpy.ops.export_scene.gltf(filepath=str(path), **ANIM_EXPORT_OPTIONS)
    finally:
        scene.frame_start, scene.frame_end = saved_range
        data.action = saved_action
        # A slot can only be set while an action is assigned, so it is restored only then.
        if saved_action is not None and hasattr(data, "action_slot") and saved_slot is not None:
            data.action_slot = saved_slot
        for track, mute in saved_mutes:
            track.mute = mute
        # Sampling the clip leaves the pose bones at its last frame; put each one back (#236).
        for bone, pose in zip(rig.pose.bones, saved_pose, strict=True):
            _set_pose(bone, pose)
        rig.name = saved_name
    return {
        "frame_start": frame_start,
        "frame_end": frame_end,
        "frame_count": frame_end - frame_start + 1,
        "fps": scene.render.fps / scene.render.fps_base,
    }


#: The pose-bone fields a clip export can change, in the order they are restored.
_POSE_FIELDS: Final = (
    "rotation_mode",
    "location",
    "rotation_quaternion",
    "rotation_euler",
    "rotation_axis_angle",
    "scale",
)


def _pose_of(bone: Any) -> dict[str, Any]:
    """A pose bone's rotation mode and transform, copied out as plain values."""
    values = {field: getattr(bone, field) for field in _POSE_FIELDS}
    return {key: value if isinstance(value, str) else tuple(value) for key, value in values.items()}


def _set_pose(bone: Any, pose: Mapping[str, Any]) -> None:
    for field in _POSE_FIELDS:
        setattr(bone, field, pose[field])


def _slot_of(action: bpy.types.Action, rig: bpy.types.Object | None) -> Any:
    """Return the slot the clip plays through: the rig's assigned slot, else the first one."""
    slots = getattr(action, "slots", None)
    if not slots:
        return None
    data = rig.animation_data if rig is not None else None
    if data is not None and data.action == action:
        assigned = getattr(data, "action_slot", None)
        if assigned is not None:
            return assigned
    return slots[0]


def _fcurves(action: bpy.types.Action, slot: Any) -> list[Any]:
    """Return the action's F-curves, through its channelbags for a layered action."""
    curves: list[Any] = []
    for layer in getattr(action, "layers", ()):
        for strip in layer.strips:
            bag = strip.channelbag(slot) if slot is not None else None
            if bag is not None:
                curves.extend(bag.fcurves)
    if not curves:
        curves = list(getattr(action, "fcurves", ()))
    return curves


def _curve_payload(curves: Sequence[Any]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for curve in sorted(curves, key=lambda c: (str(c.data_path), int(c.array_index))):
        payload.append(
            {
                "data_path": str(curve.data_path),
                "index": int(curve.array_index),
                "keys": [
                    {
                        "co": _floats(key.co),
                        "handles": [_floats(key.handle_left), _floats(key.handle_right)],
                        "interpolation": str(key.interpolation),
                    }
                    for key in curve.keyframe_points
                ],
                "modifiers": [str(modifier.type) for modifier in curve.modifiers],
            }
        )
    return payload


def _rig_payload(rig: bpy.types.Object | None) -> list[dict[str, Any]]:
    if rig is None or rig.data is None:
        return []
    return [
        {
            "name": bone.name,
            "parent": bone.parent.name if bone.parent is not None else None,
            "rest": [_floats(row) for row in bone.matrix_local],
        }
        for bone in rig.data.bones
    ]


def _floats(values: Any) -> list[float]:
    return [float(value) for value in values]


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=_jsonable)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    return str(value)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _select_only(objects: list[bpy.types.Object]) -> None:
    view_layer = bpy.context.view_layer
    for obj in view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    view_layer.objects.active = objects[0] if objects else None
