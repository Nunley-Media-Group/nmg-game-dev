"""Mesh-level helpers: triangle counts, evaluated copies, and budget-fitting decimation."""

from __future__ import annotations

from collections.abc import Sequence

import bmesh
import bpy

from .errors import VariantError

# Each pass lowers the collapse ratio by this factor until the triangle target is met.
DECIMATE_STEP = 0.95
DECIMATE_ATTEMPTS = 20


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
        result = evaluated_mesh(scratch)
        _drop_duplicate_faces(result)
        return result
    finally:
        scene_collection.objects.unlink(scratch)
        bpy.data.objects.remove(scratch)
        bpy.data.meshes.remove(scratch_mesh)


def _drop_duplicate_faces(mesh: bpy.types.Mesh) -> None:
    """Delete faces that repeat another face's vertex set, in place.

    Collapse decimation can leave two coincident faces with opposite winding (a zero-volume sliver,
    seen on a 12-triangle cube's LOD2). An FBX export and re-import keeps only one of them, so the
    re-import count would differ from the budget count. Removing the duplicate here keeps the two
    counts equal (#69: finalize re-imports every variant).
    """
    seen: set[frozenset[int]] = set()
    duplicates: list[int] = []
    for polygon in mesh.polygons:
        key = frozenset(polygon.vertices)
        if key in seen:
            duplicates.append(polygon.index)
        seen.add(key)
    if not duplicates:
        return
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.faces[index] for index in duplicates], context="FACES_ONLY")
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()


def fit_meshes(sources: Sequence[bpy.types.Mesh], target: int, label: str) -> list[bpy.types.Mesh]:
    """Return fresh copies of sources whose triangles total at most target.

    Starts at ratio target/total and lowers the ratio by DECIMATE_STEP per pass, for at
    most DECIMATE_ATTEMPTS passes. Identical input always takes the same passes.
    """
    total = sum(triangle_count(mesh) for mesh in sources)
    if total <= target:
        return [mesh.copy() for mesh in sources]
    if target < 1:
        raise _unreachable(label, total, target)

    ratio = target / total
    for _ in range(DECIMATE_ATTEMPTS):
        candidates = [decimated_copy(mesh, ratio) for mesh in sources]
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
