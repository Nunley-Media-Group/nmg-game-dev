"""Mesh-level helpers: triangle counts, evaluated copies, and budget-fitting decimation."""

from __future__ import annotations

from collections.abc import Sequence

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
        return evaluated_mesh(scratch)
    finally:
        scene_collection.objects.unlink(scratch)
        bpy.data.objects.remove(scratch)
        bpy.data.meshes.remove(scratch_mesh)


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
