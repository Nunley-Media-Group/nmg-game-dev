"""Reduced copies of the source parts: evaluated, fitted to a triangle target, and smoothed (#139).

A copy is built from a source's evaluated geometry and transform, so the source is never edited.
Fitting uses the variants core's decimation and clean-up, so the copy meets the same contract
geometry rules as a Mobile mesh. The copy is then triangulated and shaded smooth by angle.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import bmesh
import bpy

from ..bake_core.bake import select_only
from ..variants_core.meshes import (
    DECIMATE_ATTEMPTS,
    DECIMATE_STEP,
    clean_mesh,
    decimated_copy,
    evaluated_mesh,
    replace_mesh,
    triangle_count,
)
from .plan import DEFAULTS, ReduceError


def make_copy(
    source: bpy.types.Object, collection: bpy.types.Collection, name: str
) -> bpy.types.Object:
    """A new object in collection holding source's evaluated geometry at source's transform."""
    mesh = evaluated_mesh(source)
    mesh.name = name
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.matrix_world = source.matrix_world.copy()
    return obj


def link_parent(
    source: bpy.types.Object,
    copy: bpy.types.Object,
    copy_of: Mapping[int, bpy.types.Object],
) -> None:
    """Parent copy the way source is parented, to the copy of source's parent when it has one.

    A parent that is not a source (an empty, for example) stays the parent. The local transform
    and the parent inverse are copied, so the copy sits exactly where the source sat.
    """
    parent = source.parent
    if parent is not None:
        copy.parent = copy_of.get(parent.as_pointer(), parent)
    copy.matrix_parent_inverse = source.matrix_parent_inverse.copy()
    copy.matrix_basis = source.matrix_basis.copy()


def fit_copy(copy: bpy.types.Object, target: int, label: str) -> int:
    """Clean copy, decimate it to at most target triangles when needed, then triangulate and smooth.

    Returns the final triangle count. A copy already at or below target is not decimated.
    """
    clean_mesh(copy.data)
    if triangle_count(copy.data) > target:
        _decimate_to(copy, target, label)
    _triangulate(copy)
    _smooth(copy)
    return triangle_count(copy.data)


def _decimate_to(copy: bpy.types.Object, target: int, label: str) -> None:
    """Lower the ratio by DECIMATE_STEP per pass until the cleaned copy fits target."""
    total = triangle_count(copy.data)
    if target < 1:
        raise _unreachable(label, total, target)
    ratio = target / total
    for _ in range(DECIMATE_ATTEMPTS):
        candidate = decimated_copy(copy.data, ratio)
        clean_mesh(candidate)
        if triangle_count(candidate) <= target:
            replace_mesh(copy, candidate)
            return
        bpy.data.meshes.remove(candidate)
        ratio *= DECIMATE_STEP
    raise _unreachable(label, total, target)


def _triangulate(copy: bpy.types.Object) -> None:
    bm = bmesh.new()
    try:
        bm.from_mesh(copy.data)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bm.to_mesh(copy.data)
        copy.data.update()
    finally:
        bm.free()


def _smooth(copy: bpy.types.Object) -> None:
    select_only([copy], copy)
    bpy.ops.object.shade_smooth_by_angle(
        angle=math.radians(DEFAULTS["smooth_angle_deg"]), keep_sharp_edges=True
    )


def _unreachable(label: str, total: int, target: int) -> ReduceError:
    return ReduceError(
        "reduce.unreachable_target",
        f"{label} is {total} triangles and could not be decimated to the {target}-triangle target "
        f"in {DECIMATE_ATTEMPTS} passes.",
        "Raise this part's share or tris target, or simplify the source mesh by hand.",
        target=label,
    )
