"""Desktop cleanup: structural fixes only, never decimation or texture changes."""

from __future__ import annotations

from typing import Any

import bmesh
import bpy

from .assets import asset_armature, asset_meshes, require_asset
from .meshes import evaluated_mesh, replace_mesh, triangle_count

DUPLICATE_DISTANCE = 1e-5
DEGENERATE_DISTANCE = 1e-6
ZERO_AREA_LIMIT = 1e-10


def cleanup_desktop(collection_name: str) -> dict[str, Any]:
    """Apply modifiers and clean geometry for every mesh in the asset collection."""
    collection, _root = require_asset(collection_name)
    rig = asset_armature(collection_name)
    objects: list[dict[str, Any]] = []
    for obj in asset_meshes(collection):
        tris_before = triangle_count(obj.data)
        _apply_modifiers(obj, rig)
        _clean_mesh(obj.data)
        objects.append(
            {"name": obj.name, "tris_before": tris_before, "tris_after": triangle_count(obj.data)}
        )
    return {
        "collection": collection_name,
        "objects": objects,
        "tris_before": sum(item["tris_before"] for item in objects),
        "tris_after": sum(item["tris_after"] for item in objects),
    }


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


def _clean_mesh(mesh: bpy.types.Mesh) -> None:
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=DUPLICATE_DISTANCE)
        zero_area = [face for face in bm.faces if face.calc_area() <= ZERO_AREA_LIMIT]
        bmesh.ops.delete(bm, geom=zero_area, context="FACES_ONLY")
        _delete_loose(bm)
        bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=DEGENERATE_DISTANCE)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()


def _delete_loose(bm: bmesh.types.BMesh) -> None:
    loose_edges = [edge for edge in bm.edges if not edge.link_faces]
    bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")
    loose_verts = [vert for vert in bm.verts if not vert.link_edges]
    bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")
