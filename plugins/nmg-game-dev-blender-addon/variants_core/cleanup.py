"""Desktop cleanup: structural fixes only, never decimation or texture changes."""

from __future__ import annotations

from typing import Any

import bpy
from mathutils import Vector

from ..contract_core.geometry import SAMPLE_LIMIT
from .assets import asset_armature, asset_meshes, require_asset
from .meshes import TwistRepair, clean_mesh, evaluated_mesh, replace_mesh, triangle_count

_POSITION_DECIMALS = 6


def cleanup_desktop(collection_name: str) -> dict[str, Any]:
    """Apply modifiers and clean geometry for every mesh in the asset collection."""
    collection, _root = require_asset(collection_name)
    rig = asset_armature(collection_name)
    objects: list[dict[str, Any]] = []
    for obj in asset_meshes(collection):
        tris_before = triangle_count(obj.data)
        _apply_modifiers(obj, rig)
        repair = clean_mesh(obj.data)
        objects.append(
            {
                "name": obj.name,
                "tris_before": tris_before,
                "tris_after": triangle_count(obj.data),
                "twist_repair": _twist_report(obj, repair),
            }
        )
    return {
        "collection": collection_name,
        "objects": objects,
        "tris_before": sum(item["tris_before"] for item in objects),
        "tris_after": sum(item["tris_after"] for item in objects),
    }


def _twist_report(obj: bpy.types.Object, repair: TwistRepair) -> dict[str, Any]:
    """The twist repair clean_mesh made, with up to SAMPLE_LIMIT seam midpoints in world space."""
    samples = [
        [round(float(coord), _POSITION_DECIMALS) for coord in obj.matrix_world @ Vector(point)]
        for point in repair["midpoints"][:SAMPLE_LIMIT]
    ]
    return {"faces": repair["faces"], "edges": repair["edges"], "samples": samples}


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
