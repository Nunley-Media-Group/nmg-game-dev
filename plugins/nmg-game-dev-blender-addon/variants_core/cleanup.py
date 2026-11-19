"""Desktop cleanup: structural fixes only, never decimation or texture changes."""

from __future__ import annotations

from typing import Any

import bpy
from mathutils import Matrix

from ..contract_core.validate import bottom_center, pivot_meshes
from .assets import asset_armature, asset_meshes, require_asset
from .meshes import clean_mesh, evaluated_mesh, replace_mesh, triangle_count
from .rest_pose import rest_pose


def cleanup_desktop(collection_name: str) -> dict[str, Any]:
    """Apply modifiers and clean geometry for every mesh in the asset collection, then re-seat."""
    collection, _root = require_asset(collection_name)
    rig = asset_armature(collection_name)
    objects: list[dict[str, Any]] = []
    for obj in asset_meshes(collection):
        tris_before = triangle_count(obj.data)
        _apply_modifiers(obj, rig)
        clean_mesh(obj.data)
        objects.append(
            {"name": obj.name, "tris_before": tris_before, "tris_after": triangle_count(obj.data)}
        )
    return {
        "collection": collection_name,
        "objects": objects,
        "tris_before": sum(item["tris_before"] for item in objects),
        "tris_after": sum(item["tris_after"] for item in objects),
        "pivot": reseat_desktop(collection_name),
    }


def reseat_desktop(collection_name: str) -> dict[str, Any]:
    """Move a rigged Desktop's mesh data so its bottom center sits on the world origin (#244).

    The offset is measured with bottom_center over the root and its non-LOD parts, the box the
    pivot check reads. Every Desktop mesh then moves by the same world offset, so parts stay
    aligned with the root. Only mesh data moves: origins, transforms, modifiers, vertex groups,
    and bones are unchanged. Static assets (no SK_<Name> armature) are left alone.

    An offset that rounds to zero at the micrometre is treated as exactly zero. Float32 mesh data
    rarely lands on an exact zero after a move, so without this a rigged asset already on the
    origin would be nudged again on every run.
    """
    if asset_armature(collection_name) is None:
        return {"reseated": False, "offset": [0.0, 0.0, 0.0]}
    collection, _root = require_asset(collection_name)
    meshes = asset_meshes(collection)
    bpy.context.view_layer.update()
    # The offset is measured at rest: a leftover pose must not move the rest geometry (#236).
    with rest_pose(meshes):
        offset = bottom_center(pivot_meshes(meshes))
    if all(round(component, 6) == 0.0 for component in offset):
        return {"reseated": False, "offset": [0.0, 0.0, 0.0]}
    for obj in meshes:
        local = obj.matrix_world.inverted().to_3x3() @ -offset
        obj.data.transform(Matrix.Translation(local))
        obj.data.update()
    bpy.context.view_layer.update()
    return {"reseated": True, "offset": [round(component, 6) for component in offset]}


def _apply_modifiers(obj: bpy.types.Object, rig: bpy.types.Object | None) -> None:
    """Apply every modifier except the Armature modifier that skins obj to the rig.

    The skin stays on the mesh with its vertex groups, so the rig reaches export. The rest pose
    is evaluated with those skin modifiers hidden, so the applied geometry is undeformed.
    """
    skins = [modifier for modifier in obj.modifiers if _is_rig_skin(modifier, rig)]
    if len(skins) == len(obj.modifiers):
        return
    shown = [modifier.show_viewport for modifier in skins]
    for modifier in skins:
        modifier.show_viewport = False
    try:
        applied = evaluated_mesh(obj)
    finally:
        for modifier, visible in zip(skins, shown, strict=True):
            modifier.show_viewport = visible
    for modifier in [m for m in obj.modifiers if not _is_rig_skin(m, rig)]:
        obj.modifiers.remove(modifier)
    replace_mesh(obj, applied)


def _is_rig_skin(modifier: bpy.types.Modifier, rig: bpy.types.Object | None) -> bool:
    return rig is not None and modifier.type == "ARMATURE" and modifier.object == rig
