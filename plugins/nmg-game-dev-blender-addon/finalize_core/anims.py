"""Per-clip animation probe and export for the finalize ``export_anims`` step (#138).

``probe`` lists the clips held by ``SK_<Name>`` with a content hash for each, so the host can
decide which clips miss its cache.  ``export_clips`` writes one armature-only FBX per requested
clip, ``A_<Name>_<Clip>.fbx``, holding exactly that clip.  Both touch Blender data and run only
inside the headless ``finalize_entry.py`` process.

The clip set is the rig's provenance clips that resolve to actions, plus every action assigned to
``SK_<Name>`` or held in its NLA tracks.  Unrelated actions in the file are never exported.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import bpy

from ..variants_core.assets import ARMATURE_EXPORT_NAME, asset_armature, require_armature_name_free
from ..variants_core.export import _RIG_FBX_OPTIONS

PROVENANCE_KEY: Final = "nmg_animations"
CLIP_NAME_PATTERN: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
ANIMATIONS_DIR: Final = "Animations"

# The rigged mesh export's armature and axis settings, so a clip rides the same skeleton as the
# mesh.  Only the baking and the object types differ.  Imported, never copied, so they cannot drift.
ANIM_EXPORT_OPTIONS: Final[dict[str, Any]] = {
    **_RIG_FBX_OPTIONS,
    "object_types": {"ARMATURE"},
    "bake_anim": True,
    "bake_anim_use_all_actions": False,
    "bake_anim_use_nla_strips": False,
    "bake_anim_use_all_bones": True,
    "bake_anim_force_startend_keying": True,
    "bake_anim_simplify_factor": 0.0,
}


class AnimError(Exception):
    """A clip step failure that becomes a failed envelope with this code and remediation."""

    def __init__(self, code: str, message: str, remediation: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.remediation = remediation


def probe(collection_name: str) -> dict[str, Any]:
    """Return ``{clips: [{name, hash, valid_name}], options}`` for the collection's rig.

    ``options`` fingerprints ``ANIM_EXPORT_OPTIONS``; the host folds it into the export cache key.
    A collection with no rig, or a rig with no clips, gives an empty list.
    """
    rig = asset_armature(collection_name)
    provenance = provenance_of(rig) if rig is not None else {}
    clips: list[dict[str, Any]] = []
    for action in resolve_clips(collection_name):
        clips.append(
            {
                "name": action.name,
                "hash": clip_hash(rig, action, provenance.get(action.name)),
                "valid_name": valid_clip_name(action.name),
            }
        )
    return {"clips": clips, "options": options_fingerprint()}


def resolve_clips(collection_name: str) -> list[bpy.types.Action]:
    """Return the rig's clips sorted by name: provenance clips and every action the rig holds."""
    rig = asset_armature(collection_name)
    if rig is None:
        return []
    actions: dict[str, bpy.types.Action] = {}
    for name in provenance_of(rig):
        action = bpy.data.actions.get(name)
        if action is not None:
            actions[name] = action
    data = rig.animation_data
    if data is not None:
        if data.action is not None:
            actions[data.action.name] = data.action
        for track in data.nla_tracks:
            for strip in track.strips:
                if strip.action is not None:
                    actions[strip.action.name] = strip.action
    return [actions[name] for name in sorted(actions)]


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
    action: bpy.types.Action,
    provenance: Mapping[str, Any] | None,
) -> str:
    """Return the SHA-256 of everything a clip's exported FBX depends on.

    The payload is the clip name, every F-curve through the action's slots (keyframe points,
    handles, interpolation, and modifiers), the rig's bones with parents and rest matrices, the
    provenance entry, and the scene's frame rate.  A change to any of them changes the hash.
    """
    scene = bpy.context.scene
    slot = _slot_of(action, rig)
    payload: dict[str, Any] = {
        "clip": action.name,
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
    """Write ``A_<Name>_<Clip>.fbx`` for each named clip into ``out_dir`` and describe each one.

    Each record is ``{name, file, frame_start, frame_end, frame_count, fps, source}``.  ``source``
    is the clip's recorded provenance source, or ``"authored"``.  An invalid name raises before
    anything is written.  The rig's name, action, slot, and NLA mute states are restored
    afterwards, even on failure.
    """
    rig = asset_armature(collection_name)
    if rig is None:
        raise AnimError(
            "export_anims.rig_missing",
            f"SK_{collection_name} is not an armature in {collection_name}.",
            f"Run rig_humanoid for {collection_name} before exporting its clips.",
        )
    actions = {action.name: action for action in resolve_clips(collection_name)}
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
        file_name = f"A_{collection_name}_{name}.fbx"
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
        bpy.ops.export_scene.fbx(filepath=str(path), **ANIM_EXPORT_OPTIONS)
    finally:
        scene.frame_start, scene.frame_end = saved_range
        data.action = saved_action
        # A slot can only be set while an action is assigned, so it is restored only then.
        if saved_action is not None and hasattr(data, "action_slot") and saved_slot is not None:
            data.action_slot = saved_slot
        for track, mute in saved_mutes:
            track.mute = mute
        rig.name = saved_name
    return {
        "frame_start": frame_start,
        "frame_end": frame_end,
        "frame_count": frame_end - frame_start + 1,
        "fps": scene.render.fps / scene.render.fps_base,
    }


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
