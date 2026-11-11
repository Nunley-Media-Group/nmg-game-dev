"""Mesh-level helpers: triangle counts, evaluated copies, the shared geometry clean, and
budget-fitting decimation."""

from __future__ import annotations

from collections.abc import Sequence

import bmesh
import bpy

from .errors import VariantError

# Each pass lowers the collapse ratio by this factor until the triangle target is met.
DECIMATE_STEP = 0.95
DECIMATE_ATTEMPTS = 20
# Merge distance for coincident vertices, the same distance the contract's duplicate check uses.
DUPLICATE_DISTANCE = 1e-5
DEGENERATE_DISTANCE = 1e-6
# Faces at or below this area are deleted. contract_core/geometry.py flags faces under this limit.
ZERO_AREA_LIMIT = 1e-8


def triangle_count(mesh: bpy.types.Mesh) -> int:
    return sum(max(len(polygon.vertices) - 2, 0) for polygon in mesh.polygons)


def evaluated_mesh(obj: bpy.types.Object) -> bpy.types.Mesh:
    """Return a new mesh holding obj's geometry with its modifiers applied."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), depsgraph=depsgraph)


def replace_mesh(obj: bpy.types.Object, mesh: bpy.types.Mesh) -> None:
    """Point obj at mesh and delete the previous mesh if nothing else uses it."""
    old = obj.data
    obj.data = mesh
    if old is not None and old.users == 0:
        bpy.data.meshes.remove(old)


def clean_mesh(mesh: bpy.types.Mesh) -> None:
    """Clean mesh in place so it passes the contract's geometry rules.

    Desktop cleanup and every fitted Mobile mesh run this routine. It runs, in order: merge
    doubles, dissolve degenerate edges, delete zero-area faces, delete the faces past the two
    largest on each non-manifold edge, delete repeated faces, delete loose geometry, and
    recalculate normals. Every step is deterministic, so identical input gives identical output.
    """
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=DUPLICATE_DISTANCE)
        bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=DEGENERATE_DISTANCE)
        zero_area = [face for face in bm.faces if face.calc_area() < ZERO_AREA_LIMIT]
        bmesh.ops.delete(bm, geom=zero_area, context="FACES_ONLY")
        _drop_non_manifold_faces(bm)
        _delete_repeated_faces(bm)
        _delete_loose(bm)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()


def _drop_non_manifold_faces(bm: bmesh.types.BMesh) -> None:
    """Delete the faces past the two largest on every edge that more than two faces share.

    Such a face makes the recalculated normals depend on the order faces are visited, so the
    contract flags it. This repeats until no edge has more than two faces, because deleting one
    face can leave another edge over the limit. Ties keep the lower face index.
    """
    while True:
        bm.faces.index_update()
        doomed: dict[int, bmesh.types.BMFace] = {}
        for edge in bm.edges:
            if len(edge.link_faces) <= 2:
                continue
            ranked = sorted(edge.link_faces, key=lambda face: (-face.calc_area(), face.index))
            for face in ranked[2:]:
                doomed[face.index] = face
        if not doomed:
            return
        bmesh.ops.delete(bm, geom=list(doomed.values()), context="FACES_ONLY")


def _delete_repeated_faces(bm: bmesh.types.BMesh) -> None:
    """Delete faces whose vertex set repeats an earlier face's set, keeping the first by index.

    Collapse decimation can leave two coincident faces with opposite winding (a zero-volume sliver,
    seen on a 12-triangle cube's LOD2). An FBX export and re-import keeps only one of them, so the
    re-import count would differ from the budget count (#69: finalize re-imports every variant).
    """
    bm.faces.index_update()
    bm.verts.index_update()
    seen: set[frozenset[int]] = set()
    doomed: list[bmesh.types.BMFace] = []
    for face in bm.faces:
        key = frozenset(vert.index for vert in face.verts)
        if key in seen:
            doomed.append(face)
        seen.add(key)
    if doomed:
        bmesh.ops.delete(bm, geom=doomed, context="FACES_ONLY")


def _delete_loose(bm: bmesh.types.BMesh) -> None:
    loose_edges = [edge for edge in bm.edges if not edge.link_faces]
    bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")
    loose_verts = [vert for vert in bm.verts if not vert.link_edges]
    bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")


def decimated_copy(source: bpy.types.Mesh, ratio: float) -> bpy.types.Mesh:
    """Collapse-decimate a copy of source to ratio, triangulated, and return the result."""
    scratch_mesh = source.copy()
    scratch = bpy.data.objects.new("nmg_decimate_scratch", scratch_mesh)
    scene_collection = bpy.context.scene.collection
    scene_collection.objects.link(scratch)
    try:
        modifier = scratch.modifiers.new("Decimate", "DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = ratio
        modifier.use_collapse_triangulate = True
        return evaluated_mesh(scratch)
    finally:
        scene_collection.objects.unlink(scratch)
        bpy.data.objects.remove(scratch)
        bpy.data.meshes.remove(scratch_mesh)


def _cleaned(mesh: bpy.types.Mesh) -> bpy.types.Mesh:
    clean_mesh(mesh)
    return mesh


def fit_meshes(sources: Sequence[bpy.types.Mesh], target: int, label: str) -> list[bpy.types.Mesh]:
    """Return fresh, cleaned copies of sources whose triangles total at most target.

    Every candidate is cleaned before its triangle total is compared with target, so the budget
    counts the geometry the variant keeps. The decimation starts at ratio target/total of the
    cleaned sources and lowers the ratio by DECIMATE_STEP per pass, for at most DECIMATE_ATTEMPTS
    passes. Identical input always takes the same passes.
    """
    copies = [_cleaned(mesh.copy()) for mesh in sources]
    total = sum(triangle_count(copy) for copy in copies)
    if total <= target:
        return copies
    for copy in copies:
        bpy.data.meshes.remove(copy)
    if target < 1:
        raise _unreachable(label, total, target)

    ratio = target / total
    for _ in range(DECIMATE_ATTEMPTS):
        candidates = [_cleaned(decimated_copy(mesh, ratio)) for mesh in sources]
        if sum(triangle_count(candidate) for candidate in candidates) <= target:
            return candidates
        for candidate in candidates:
            bpy.data.meshes.remove(candidate)
        ratio *= DECIMATE_STEP
    raise _unreachable(label, total, target)


def _unreachable(label: str, total: int, target: int) -> VariantError:
    return VariantError(
        "variants.budget_unreachable",
        f"{label} is {total} triangles and could not be decimated to the {target}-triangle "
        f"budget in {DECIMATE_ATTEMPTS} passes.",
        "Simplify the Desktop mesh by hand, or raise the Mobile tris budget in nmg-budgets.json.",
    )
