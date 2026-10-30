"""Library clip import, rest-relative retargeting, and baking onto SK_<Name>.

Touches Blender data. Every clip is imported, sampled frame by frame, installed as an action
named after the clip, and then removed along with its temporary import.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import Any

import bpy
from mathutils import Matrix, Vector

from .library import REQUIRED_TARGETS, Library, LibraryClip, load, resolve_source_bone
from .outcome import STATUS_FALLBACK, STATUS_SPIKE, RigError, fail, ok
from .skeleton import MANNY_BONE_NAMES

_TEMP_ACTION_PREFIX = "__nmg_tmp_"
_PROVENANCE_KEY = "nmg_animations"


def import_animations(
    collection_name: str,
    library_dir: str,
    clips: Sequence[str] | None = None,
    motion_prompt: str | None = None,
) -> dict[str, Any]:
    """Bake library clips onto SK_<Name>. clips=None (or empty) bakes every library clip."""
    try:
        if motion_prompt and motion_prompt.strip():
            return fail(
                STATUS_SPIKE,
                "anim.text_motion_unsupported",
                "Text-driven motion is not supported.",
                "Pick clips from the animation library by name. Generating motion from text "
                "needs a follow-up spike.",
            )
        armature = bpy.data.objects.get(f"SK_{collection_name}")
        if armature is None or armature.type != "ARMATURE":
            return fail(
                STATUS_FALLBACK,
                "anim.rig_missing",
                f"SK_{collection_name} does not exist.",
                f"Run rig_humanoid for collection {collection_name} first, then import animations.",
            )
        library = load(library_dir)
        selected = _select_clips(library, clips)
        baked = [bake_clip(armature, library, clip) for clip in selected]
        _rest_pose(armature)
        return ok(asset=collection_name, armature=armature.name, clips=baked)
    except RigError as error:
        return error.result


def bake_clip(armature: bpy.types.Object, library: Library, clip: LibraryClip) -> dict[str, Any]:
    """Import one clip, retarget it onto armature, and install it as action clip.name."""
    scene = bpy.context.scene
    view_layer = bpy.context.view_layer
    objects_before = set(bpy.data.objects)
    actions_before = set(bpy.data.actions)

    stashed = view_layer.active_layer_collection
    view_layer.active_layer_collection = view_layer.layer_collection
    try:
        _import_clip(clip)
    finally:
        view_layer.active_layer_collection = stashed
    imported_objects = [obj for obj in bpy.data.objects if obj not in objects_before]
    imported_actions = [action for action in bpy.data.actions if action not in actions_before]

    try:
        source = next((obj for obj in imported_objects if obj.type == "ARMATURE"), None)
        if source is None:
            raise RigError(
                STATUS_FALLBACK,
                "anim.library_invalid",
                f"Clip file {clip.file} contains no armature.",
                "Export the clip from a rig with an armature, then rerun.",
            )
        action, start, end = _sample(armature, source, library, clip)
    finally:
        _discard(imported_objects, imported_actions)

    _install(armature, action, clip.name)
    provenance = {
        "name": clip.name,
        "frame_start": start,
        "frame_end": end,
        "frame_count": end - start + 1,
        "fps": scene.render.fps,
        "source": {
            "library": library.name,
            "file": clip.file,
            "sha256": clip.sha256,
            "skeleton": library.skeleton,
        },
    }
    stored = json.loads(armature.get(_PROVENANCE_KEY, "{}"))
    stored[clip.name] = provenance
    armature[_PROVENANCE_KEY] = json.dumps(stored, sort_keys=True)
    return provenance


def _select_clips(library: Library, names: Sequence[str] | None) -> list[LibraryClip]:
    if not names:
        return list(library.clips)
    selected: list[LibraryClip] = []
    for name in names:
        clip = library.clip(name)
        if clip is None:
            raise RigError(
                STATUS_FALLBACK,
                "anim.clip_not_found",
                f"The library lists no clip named '{name}'.",
                f"Request one of the clips listed in {library.directory / 'library.json'}.",
            )
        selected.append(clip)
    return selected


def _import_clip(clip: LibraryClip) -> None:
    if clip.path.suffix.lower() == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(clip.path), use_anim=True)
    else:
        bpy.ops.import_anim.bvh(filepath=str(clip.path), axis_forward="-Z", axis_up="Y")


def _sample(
    armature: bpy.types.Object,
    source: bpy.types.Object,
    library: Library,
    clip: LibraryClip,
) -> tuple[bpy.types.Action, int, int]:
    source_action = source.animation_data.action if source.animation_data else None
    if source_action is None:
        raise RigError(
            STATUS_FALLBACK,
            "anim.library_invalid",
            f"Clip file {clip.file} holds no animation.",
            "Export the clip with its animation included, then rerun.",
        )
    start, end = _frame_range(clip, source_action)
    pairs = _bone_pairs(source, library, clip)
    pelvis_source = dict(pairs)["pelvis"]
    pelvis_scale = _pelvis_scale(armature, source, pelvis_source)

    scene = bpy.context.scene
    original_frame = scene.frame_current
    action = bpy.data.actions.new(f"{_TEMP_ACTION_PREFIX}{clip.name}")
    anim_data = armature.animation_data_create()
    anim_data.action = action
    _rest_pose(armature)
    try:
        for frame in range(start, end + 1):
            scene.frame_set(frame)
            _retarget_frame(armature, source, pairs, pelvis_scale, frame)
    finally:
        scene.frame_set(original_frame)
    return action, start, end


def _frame_range(clip: LibraryClip, source_action: bpy.types.Action) -> tuple[int, int]:
    low, high = source_action.frame_range
    start = clip.frame_start if clip.frame_start is not None else math.floor(low)
    end = clip.frame_end if clip.frame_end is not None else math.ceil(high)
    return int(start), int(end)


def _bone_pairs(
    source: bpy.types.Object, library: Library, clip: LibraryClip
) -> list[tuple[str, str]]:
    """Return (Manny target, source bone) pairs in Manny hierarchy order."""
    by_target: dict[str, str] = {}
    for bone in source.data.bones:
        target = resolve_source_bone(bone.name, library.bone_map)
        if target is not None:
            by_target.setdefault(target, bone.name)
    missing = [target for target in REQUIRED_TARGETS if target not in by_target]
    if missing:
        raise RigError(
            STATUS_FALLBACK,
            "anim.bone_map_incomplete",
            f"Clip file {clip.file} has no bone for: {', '.join(missing)}.",
            "Export the clip from a skeleton that matches its declared skeleton in "
            "library.json, then rerun.",
        )
    return [(target, by_target[target]) for target in MANNY_BONE_NAMES if target in by_target]


def _pelvis_scale(
    armature: bpy.types.Object, source: bpy.types.Object, source_pelvis: str
) -> float:
    """Scale pelvis translation from source units to target units by rest height."""
    source_height = source.data.bones[source_pelvis].head_local.z
    target_height = armature.data.bones["pelvis"].head_local.z
    if abs(source_height) < 1e-9:
        return 1.0
    return target_height / source_height


def _retarget_frame(
    armature: bpy.types.Object,
    source: bpy.types.Object,
    pairs: list[tuple[str, str]],
    pelvis_scale: float,
    frame: int,
) -> None:
    """Key every mapped bone at frame. Bones are processed parent first."""
    view_layer = bpy.context.view_layer
    depsgraph = bpy.context.evaluated_depsgraph_get()
    posed_source = source.evaluated_get(depsgraph)
    for target_name, source_name in pairs:
        src_pose = posed_source.pose.bones[source_name]
        src_bone = source.data.bones[source_name]
        tgt_pose = armature.pose.bones[target_name]
        tgt_bone = armature.data.bones[target_name]

        # R_t = (R_s · R_s_rest⁻¹) · R_t_rest, in armature space.
        delta = src_pose.matrix.to_3x3() @ src_bone.matrix_local.to_3x3().inverted()
        rotation = (delta @ tgt_bone.matrix_local.to_3x3()).normalized().to_4x4()
        if target_name == "pelvis":
            offset = Vector(src_pose.matrix.to_translation()) - Vector(src_bone.head_local)
            head = Vector(tgt_bone.head_local) + offset * pelvis_scale
        else:
            # A bone's head is set by its parent's pose, so it is read after the update.
            head = tgt_pose.matrix.to_translation()
        tgt_pose.matrix = Matrix.Translation(head) @ rotation
        view_layer.update()
        tgt_pose.keyframe_insert("rotation_quaternion", frame=frame)
        if target_name == "pelvis":
            tgt_pose.keyframe_insert("location", frame=frame)


def _rest_pose(armature: bpy.types.Object) -> None:
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"
        pose_bone.location = (0.0, 0.0, 0.0)
        pose_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pose_bone.scale = (1.0, 1.0, 1.0)


def _install(armature: bpy.types.Object, action: bpy.types.Action, clip_name: str) -> None:
    """Replace any action already named clip_name with the freshly baked one."""
    if armature.animation_data is not None:
        armature.animation_data.action = None
    previous = bpy.data.actions.get(clip_name)
    if previous is not None:
        bpy.data.actions.remove(previous)
    action.name = clip_name
    action.use_fake_user = True


def _discard(objects: list[bpy.types.Object], actions: list[bpy.types.Action]) -> None:
    """Remove the temporary import: its objects, their data, and its actions."""
    for obj in objects:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if isinstance(data, bpy.types.Armature) and data.users == 0:
            bpy.data.armatures.remove(data)
        elif isinstance(data, bpy.types.Mesh) and data.users == 0:
            bpy.data.meshes.remove(data)
    for action in actions:
        bpy.data.actions.remove(action)
