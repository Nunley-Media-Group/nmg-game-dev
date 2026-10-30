"""Desktop cleanup: structural fixes only, never decimation or texture changes."""

from __future__ import annotations

from typing import Any

import bmesh
import bpy

from .assets import asset_meshes, require_asset
from .meshes import evaluated_mesh, replace_mesh, triangle_count

DUPLICATE_DISTANCE = 1e-5
DEGENERATE_DISTANCE = 1e-6
ZERO_AREA_LIMIT = 1e-10


def cleanup_desktop(collection_name: str) -> dict[str, Any]:
    """Apply modifiers and clean geometry for every mesh in the asset collection."""
    collection, _root = require_asset(collection_name)
    objects: list[dict[str, Any]] = []
    for obj in asset_meshes(collection):
        tris_before = triangle_count(obj.data)
        _apply_modifiers(obj)
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


def _apply_modifiers(obj: bpy.types.Object) -> None:
    if not obj.modifiers:
        return
    applied = evaluated_mesh(obj)
    obj.modifiers.clear()
    replace_mesh(obj, applied)


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
