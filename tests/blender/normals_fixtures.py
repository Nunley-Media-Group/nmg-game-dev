"""Shared normals fixtures: the figure-8 Klein bottle (#232, #243).

A figure-8 Klein bottle is a closed surface with no consistent orientation. Its last row of quads
closes onto row 0 with reversed winding, so after recalculation it keeps a twist seam.

Imported only under Blender (``bpy`` and ``bmesh`` are Blender modules).
"""

from __future__ import annotations

import math
from typing import Any

import bmesh
import bpy

KLEIN_RADIUS = 2.0


def _klein_point(u: float, v: float) -> tuple[float, float, float]:
    ring = KLEIN_RADIUS + math.cos(u / 2) * math.sin(v) - math.sin(u / 2) * math.sin(2 * v)
    z = math.sin(u / 2) * math.sin(v) + math.cos(u / 2) * math.sin(2 * v)
    return (ring * math.cos(u), ring * math.sin(u), z)


def klein_bmesh(nu: int, nv: int) -> Any:
    """Figure-8 Klein bottle as a quad grid; row nu - 1 closes onto row 0 with a twisted seam."""
    bm = bmesh.new()
    grid = [
        [
            bm.verts.new(_klein_point(2 * math.pi * i / nu, 2 * math.pi * (j + 0.5) / nv))
            for j in range(nv)
        ]
        for i in range(nu)
    ]

    def vert(i: int, j: int) -> Any:
        if i == nu:
            return grid[0][(-j) % nv]
        return grid[i][j % nv]

    for i in range(nu):
        for j in range(nv):
            bm.faces.new((vert(i, j), vert(i + 1, j), vert(i + 1, j + 1), vert(i, j + 1)))
    return bm


def to_mesh(name: str, bm: Any) -> Any:
    """Write bm to a new mesh named name, free bm, and return the mesh."""
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh


def klein(nu: int = 16, nv: int = 8, name: str = "Klein") -> Any:
    """A new mesh holding the nu x nv figure-8 Klein bottle."""
    return to_mesh(name, klein_bmesh(nu, nv))
