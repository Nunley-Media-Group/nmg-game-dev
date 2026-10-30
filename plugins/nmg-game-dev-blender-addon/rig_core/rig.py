"""Deform-only UE5 Mannequin armature build and automatic skinning. Touches Blender data.

A rebuild is transactional. The previous SK_<Name> and its vertex groups are set aside,
not removed, while the new attempt is skinned and weight-checked. Only a passing attempt
commits. A failing attempt is rolled back, and the previous rig is restored as it was.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import bpy
from mathutils import Matrix, Vector

from .landmarks import validate
from .outcome import STATUS_FALLBACK, RigError, ok
from .skeleton import LANDMARK_KEYS, MANNY_BONE_NAMES, MANNY_BONES, Vec3, bone_layout

_ORIGIN = (0.0, 0.0, 0.0)
_SET_ASIDE = "__nmg_prev_"
_ARMATURE_MODIFIER = "Armature"


@dataclass(frozen=True)
class _MeshState:
    """Everything a rebuild can change on one skinned mesh, captured before it changes."""

    mesh: bpy.types.Object
    parent: bpy.types.Object | None
    parent_type: str
    parent_bone: str
    parent_inverse: Matrix
    basis: Matrix
    group_names: tuple[str, ...]
    active_group: int


def rig_humanoid(
    collection_name: str, body_type: str, landmarks: Mapping[str, Any]
) -> dict[str, Any]:
    """Build SK_<Name> from agent-supplied landmarks and skin every mesh in the collection.

    Validation runs before any scene change. A failed build leaves the scene as it was,
    including any rig built by an earlier call.
    """
    failure = validate(body_type, landmarks, _mesh_bounds(collection_name))
    if failure is not None:
        return failure
    points = {key: _point(landmarks[key]) for key in LANDMARK_KEYS}
    try:
        _build(collection_name, body_type, points)
    except RigError as error:
        return error.result
    return ok(
        asset=collection_name,
        armature=f"SK_{collection_name}",
        body_type=body_type,
        bones=list(MANNY_BONE_NAMES),
        bone_count=len(MANNY_BONE_NAMES),
    )


def _point(value: Any) -> Vec3:
    return (float(value[0]), float(value[1]), float(value[2]))


def _mesh_bounds(collection_name: str) -> tuple[Vec3, Vec3] | None:
    """World bounding box of SM_<Name>, or None when the collection or root mesh is missing."""
    collection = bpy.data.collections.get(collection_name)
    root = bpy.data.objects.get(f"SM_{collection_name}")
    if collection is None or root is None or root.type != "MESH":
        return None
    if root.name not in collection.objects:
        return None
    corners = [root.matrix_world @ Vector(corner) for corner in root.bound_box]
    low = tuple(min(corner[axis] for corner in corners) for axis in range(3))
    high = tuple(max(corner[axis] for corner in corners) for axis in range(3))
    return (low[0], low[1], low[2]), (high[0], high[1], high[2])


def _build(collection_name: str, body_type: str, points: Mapping[str, Vec3]) -> None:
    collection = bpy.data.collections[collection_name]
    meshes = sorted(
        (obj for obj in collection.objects if obj.type == "MESH"), key=lambda obj: obj.name
    )
    roots = [mesh for mesh in meshes if mesh.parent is None or mesh.parent not in meshes]
    rig_name = f"SK_{collection_name}"
    previous = bpy.data.objects.get(rig_name)
    states = [_capture(mesh) for mesh in roots]

    _ensure_object_mode()
    armature: bpy.types.Object | None = None
    try:
        if previous is not None:
            _set_aside(previous, roots)
        armature = _create_armature(collection, points)
        _select_only([*roots, armature], armature)
        bpy.ops.object.parent_set(type="ARMATURE_AUTO", keep_transform=True)

        unweighted = _unweighted_vertices(armature, roots)
        if unweighted:
            raise RigError(
                STATUS_FALLBACK,
                "rig.weights_failed",
                f"{unweighted} vertices of SM_{collection_name} have no deform-bone weight.",
                "Make SM_<Name> a single manifold mesh, or merge its separate parts into one "
                "object, then rerun.",
            )
    except Exception:
        _roll_back(rig_name, states, previous, armature)
        raise

    _commit(meshes, previous, armature)
    armature["nmg_body_type"] = body_type
    armature["nmg_landmarks"] = json.dumps(
        {key: list(points[key]) for key in sorted(points)}, sort_keys=True
    )


def _capture(mesh: bpy.types.Object) -> _MeshState:
    return _MeshState(
        mesh=mesh,
        parent=mesh.parent,
        parent_type=mesh.parent_type,
        parent_bone=mesh.parent_bone,
        parent_inverse=mesh.matrix_parent_inverse.copy(),
        basis=mesh.matrix_basis.copy(),
        group_names=tuple(group.name for group in mesh.vertex_groups),
        active_group=mesh.vertex_groups.active_index,
    )


def _set_aside(previous: bpy.types.Object, roots: list[bpy.types.Object]) -> None:
    """Rename the previous rig and its bone-named vertex groups so the new rig can take the names.

    The renamed groups keep their weights, so a rollback can restore them unchanged.
    """
    previous.name = _SET_ASIDE + previous.name
    if previous.data is not None:
        previous.data.name = _SET_ASIDE + previous.data.name
    for mesh in roots:
        for group in mesh.vertex_groups:
            if group.name in MANNY_BONE_NAMES:
                group.name = _SET_ASIDE + group.name


def _roll_back(
    rig_name: str,
    states: list[_MeshState],
    previous: bpy.types.Object | None,
    armature: bpy.types.Object | None,
) -> None:
    """Undo a failed attempt: remove the new rig and restore every captured mesh and the old rig."""
    for state in states:
        mesh = state.mesh
        if armature is not None:
            for modifier in list(mesh.modifiers):
                if modifier.type == "ARMATURE" and modifier.object is armature:
                    mesh.modifiers.remove(modifier)
        mesh.parent = state.parent
        mesh.parent_type = state.parent_type
        mesh.parent_bone = state.parent_bone
        mesh.matrix_parent_inverse = state.parent_inverse
        mesh.matrix_basis = state.basis
        for group in list(mesh.vertex_groups)[len(state.group_names) :]:
            mesh.vertex_groups.remove(group)
        for group, name in zip(mesh.vertex_groups, state.group_names, strict=True):
            group.name = name
        if state.group_names:
            mesh.vertex_groups.active_index = state.active_group

    if armature is not None:
        _remove_armature(armature)
    if previous is not None:
        previous.name = rig_name
        if previous.data is not None:
            previous.data.name = rig_name


def _commit(
    meshes: list[bpy.types.Object],
    previous: bpy.types.Object | None,
    armature: bpy.types.Object,
) -> None:
    """Retire the set-aside rig after a passing attempt and name the new modifiers as usual."""
    if previous is not None:
        for mesh in meshes:
            for modifier in list(mesh.modifiers):
                if modifier.type == "ARMATURE" and modifier.object is previous:
                    mesh.modifiers.remove(modifier)
            for group in list(mesh.vertex_groups):
                if group.name.startswith(_SET_ASIDE):
                    mesh.vertex_groups.remove(group)
        _remove_armature(previous)
    for mesh in meshes:
        for modifier in mesh.modifiers:
            if modifier.type == "ARMATURE" and modifier.object is armature:
                modifier.name = _ARMATURE_MODIFIER


def _remove_armature(obj: bpy.types.Object) -> None:
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if data is not None and data.users == 0:
        bpy.data.armatures.remove(data)


def _create_armature(
    collection: bpy.types.Collection, points: Mapping[str, Vec3]
) -> bpy.types.Object:
    name = f"SK_{collection.name}"
    data = bpy.data.armatures.new(name)
    armature = bpy.data.objects.new(name, data)
    armature.location = _ORIGIN
    collection.objects.link(armature)

    layout = bone_layout(points)
    _ensure_object_mode()
    _select_only([armature], armature)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        edit_bones = data.edit_bones
        for bone_name, parent_name in MANNY_BONES:
            head, tail = layout[bone_name]
            bone = edit_bones.new(bone_name)
            bone.head = head
            bone.tail = tail
            bone.roll = 0.0
            bone.use_deform = True
            if parent_name is not None:
                bone.parent = edit_bones[parent_name]
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def _unweighted_vertices(armature: bpy.types.Object, roots: list[bpy.types.Object]) -> int:
    bone_names = {bone.name for bone in armature.data.bones}
    count = 0
    for mesh in roots:
        group_names = {group.index: group.name for group in mesh.vertex_groups}
        for vertex in mesh.data.vertices:
            weighted = any(
                entry.weight > 0 and group_names.get(entry.group) in bone_names
                for entry in vertex.groups
            )
            if not weighted:
                count += 1
    return count


def _select_only(objects: list[bpy.types.Object], active: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active


def _ensure_object_mode() -> None:
    active = bpy.context.view_layer.objects.active
    if active is not None and active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
