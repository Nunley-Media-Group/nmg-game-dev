"""Fixtures for the spatial inspection tests (#127).

Probe is a defective small_prop: a dense body, one part 0.05 m away, an interpenetrating pair,
an open box that touches the body, and more than 2000 triangles. Clean is a compliant small_prop:
a box with a flush-touching cap, an overlapping cap, and a rail that reaches the body only
through an Array modifier. Offsets are deliberately generic so no two faces are coplanar, except
where a fixture means to touch.
"""

from __future__ import annotations

import bmesh
import bpy
from mathutils import Vector

from .contract_fixtures import clear_scene

BODY_HALF = 0.25
BODY_CUTS = 15  # 6 faces x 16 x 16 grid cells x 2 triangles = 3072 triangles


def _object(
    collection: bpy.types.Collection,
    name: str,
    size: float,
    location: tuple[float, float, float],
    *,
    cuts: int = 0,
    open_plus_x: bool = False,
) -> bpy.types.Object:
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    if cuts:
        bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=cuts, use_grid_fill=True)
    if open_plus_x:
        open_faces = [face for face in bm.faces if face.normal.x > 0.5]
        bmesh.ops.delete(bm, geom=open_faces, context="FACES_ONLY")
    bmesh.ops.translate(bm, verts=bm.verts[:], vec=Vector(location))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def _fresh_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def build_probe() -> bpy.types.Collection:
    """The defective collection Probe: floating, interpenetration, non_manifold, and budget."""
    clear_scene()
    collection = _fresh_collection("Probe")
    _object(
        collection,
        "SM_Probe_Body",
        2 * BODY_HALF,
        (0.0, 0.0, 0.0),
        cuts=BODY_CUTS,
    )
    # 0.05 m between this part's nearest face (x = 0.30) and the body's +X face (x = 0.25).
    _object(collection, "SM_Probe_Floating", 0.1, (0.35, 0.0, 0.0))
    # Pair A sits on the body's top; pair B crosses it at generic offsets (no coplanar faces).
    _object(collection, "SM_Probe_Pair_A", 0.1, (0.0, 0.0, 0.3))
    _object(collection, "SM_Probe_Pair_B", 0.1, (0.04, 0.03, 0.31))
    # Open box: the +X face is missing, so its four boundary edges are non-manifold.
    _object(collection, "SM_Probe_Open", 0.1, (-0.30, 0.0, 0.0), open_plus_x=True)
    return collection


def build_clean() -> bpy.types.Collection:
    """The compliant collection Clean: touching, overlapping, and array-connected parts."""
    clear_scene()
    collection = _fresh_collection("Clean")
    _object(collection, "SM_Clean_Body", 2 * BODY_HALF, (0.0, 0.0, 0.0))
    # Touches the body's top face exactly (z = 0.25).
    _object(collection, "SM_Clean_Top", 0.2, (0.0, 0.0, 0.35))
    # Overlaps the cap and floats 0.02 m above the body; connected through the cap.
    _object(collection, "SM_Clean_Overlap", 0.2, (0.13, 0.04, 0.37))
    rail = _object(collection, "SM_Clean_Rail", 0.02, (0.28, 0.0, 0.0))
    # The base sits 0.02 m from the body; the Array copy lands on the body's +X face.
    modifier = rail.modifiers.new("Array", "ARRAY")
    modifier.count = 2
    modifier.use_relative_offset = True
    modifier.relative_offset_displace = (-1.0, 0.0, 0.0)
    return collection
