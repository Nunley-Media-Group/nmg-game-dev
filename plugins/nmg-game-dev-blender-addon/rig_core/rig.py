"""Deform-only UE5 Mannequin armature build and automatic skinning. Touches Blender data."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import bpy
from mathutils import Vector

from .landmarks import validate
from .outcome import STATUS_FALLBACK, RigError, ok
from .skeleton import LANDMARK_KEYS, MANNY_BONE_NAMES, MANNY_BONES, Vec3, bone_layout

_ORIGIN = (0.0, 0.0, 0.0)


def rig_humanoid(
    collection_name: str, body_type: str, landmarks: Mapping[str, Any]
) -> dict[str, Any]:
    """Build SK_<Name> from agent-supplied landmarks and skin every mesh in the collection.

    Validation runs before any scene change. A failed skinning removes the new armature.
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
    _remove_rig(collection_name, meshes)

    armature = _create_armature(collection, points)
    roots = [mesh for mesh in meshes if mesh.parent is None or mesh.parent not in meshes]
    _select_only([*roots, armature], armature)
    bpy.ops.object.parent_set(type="ARMATURE_AUTO", keep_transform=True)

    unweighted = _unweighted_vertices(armature, roots)
    if unweighted:
        _remove_rig(collection_name, meshes)
        raise RigError(
            STATUS_FALLBACK,
            "rig.weights_failed",
            f"{unweighted} vertices of SM_{collection_name} have no deform-bone weight.",
            "Make SM_<Name> a single manifold mesh, or merge its separate parts into one "
            "object, then rerun.",
        )

    armature["nmg_body_type"] = body_type
    armature["nmg_landmarks"] = json.dumps(
        {key: list(points[key]) for key in sorted(points)}, sort_keys=True
    )


def _remove_rig(collection_name: str, meshes: list[bpy.types.Object]) -> None:
    """Remove SK_<Name>, its armature data, and the Armature modifiers left on the meshes."""
    rig_name = f"SK_{collection_name}"
    for mesh in meshes:
        for modifier in list(mesh.modifiers):
            if (
                modifier.type == "ARMATURE"
                and modifier.object is not None
                and modifier.object.name == rig_name
            ):
                mesh.modifiers.remove(modifier)

    old = bpy.data.objects.get(rig_name)
    if old is None:
        return
    for mesh in meshes:
        if mesh.parent is old:
            _unparent_keep_transform(mesh)
    data = old.data
    bpy.data.objects.remove(old, do_unlink=True)
    if data is not None and data.users == 0:
        bpy.data.armatures.remove(data)


def _unparent_keep_transform(obj: bpy.types.Object) -> None:
    world = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = world


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
