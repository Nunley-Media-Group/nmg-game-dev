"""Blender fixture for the #106 A-pose tests: the box humanoid of ``tests/meshy_arm_geometry.py``.

``build_humanoid`` writes that humanoid as one GLB mesh object, with its arms dropped ``drop_deg``.
Each arm is a four-sided taper from its pivot to a hand tip on the drop line. The torso, neck, head,
and legs are boxes. Their X and Y extents are symmetric, so the import's recentering moves nothing,
and the returned landmarks hold in the session too.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import bmesh
import bpy

from ..meshy_arm_geometry import (
    ARM_HALF_WIDTH,
    ARM_LENGTH,
    HEIGHT,
    HIP_Z,
    Point,
    arm_directions,
    landmarks,
    side_pivot,
)

# Torso, neck, head, and the two legs. Legs stand at |x| in [0.02, 0.15], under the hips.
_BODY_BOXES: Final = (
    ((-0.15, -0.08, HIP_Z), (0.15, 0.08, 1.5)),
    ((-0.05, -0.05, 1.5), (0.05, 0.05, 1.6)),
    ((-0.1, -0.08, 1.6), (0.1, 0.08, HEIGHT)),
    ((0.02, -0.08, 0.0), (0.15, 0.08, HIP_Z)),
    ((-0.15, -0.08, 0.0), (-0.02, 0.08, HIP_Z)),
)
_DEPTH: Final[Point] = (0.0, 1.0, 0.0)


def _add_box(bm: bmesh.types.BMesh, low: Point, high: Point) -> None:
    (x0, y0, z0), (x1, y1, z1) = low, high
    corners = [
        bm.verts.new(co)
        for co in (
            (x0, y0, z0),
            (x1, y0, z0),
            (x1, y1, z0),
            (x0, y1, z0),
            (x0, y0, z1),
            (x1, y0, z1),
            (x1, y1, z1),
            (x0, y1, z1),
        )
    ]
    quads = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
    for quad in quads:
        bm.faces.new([corners[index] for index in quad])


def _add_arm(bm: bmesh.types.BMesh, sign: float, drop_deg: float) -> None:
    """Add one arm: a square base at the pivot, tapering to a tip on the drop line."""
    pivot = side_pivot(sign)
    along, across = arm_directions(sign, drop_deg)
    base = []
    for a, b in ((1.0, 1.0), (1.0, -1.0), (-1.0, -1.0), (-1.0, 1.0)):
        corner = tuple(
            pivot[axis] + ARM_HALF_WIDTH * (a * across[axis] + b * _DEPTH[axis])
            for axis in range(3)
        )
        base.append(bm.verts.new(corner))
    tip = bm.verts.new(tuple(pivot[axis] + ARM_LENGTH * along[axis] for axis in range(3)))
    bm.faces.new(base)
    for index in range(4):
        bm.faces.new((base[index], base[(index + 1) % 4], tip))


def build_humanoid(path: Path, drop_deg: float = 55.0) -> tuple[Path, dict[str, list[float]]]:
    """Export the box humanoid, arms dropped ``drop_deg``, as one GLB; return it with its landmarks.

    The object is removed from the scene afterwards, so the caller imports the GLB into the session.
    """
    mesh = bpy.data.meshes.new("Humanoid")
    bm = bmesh.new()
    try:
        for low, high in _BODY_BOXES:
            _add_box(bm, low, high)
        for sign in (1.0, -1.0):
            _add_arm(bm, sign, drop_deg)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
        bm.to_mesh(mesh)
    finally:
        bm.free()
    obj = bpy.data.objects.new("Humanoid", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB")
    for item in list(bpy.data.objects):
        bpy.data.objects.remove(item, do_unlink=True)
    return path, landmarks(drop_deg)
