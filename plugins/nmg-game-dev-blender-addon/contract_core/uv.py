"""UV checks: exactly one map named UVMap, and no overlapping islands for unique-bake classes.

Overlap is measured by rasterizing every UV triangle onto a GRID x GRID texel grid. A texel is
shared when two or more faces cover it. Overlap fails when more than OVERLAP_LIMIT of the covered
texels are shared.
"""

from __future__ import annotations

import math
from array import array
from collections.abc import Iterator, Sequence

import bpy

from .report import finding

GRID = 512
OVERLAP_LIMIT = 0.005
_NO_FACE = -1
_UV_MAP = "UVMap"

Point = tuple[float, float]


def uv_findings(name: str, mesh: bpy.types.Mesh, check_overlap: bool) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    layers = mesh.uv_layers
    if len(layers) != 1 or layers[0].name != _UV_MAP:
        found = ", ".join(layer.name for layer in layers) or "none"
        findings.append(
            finding(
                "uv.single_map",
                name,
                f"{name} has UV map(s): {found}. The contract needs exactly one, named UVMap.",
            )
        )
    if check_overlap and len(layers) >= 1:
        fraction = overlap_fraction(mesh, layers[0].data)
        if fraction > OVERLAP_LIMIT:
            findings.append(
                finding(
                    "uv.overlap",
                    name,
                    f"{name}: {fraction:.1%} of covered UV texels are shared by two or more "
                    f"faces; the limit is {OVERLAP_LIMIT:.1%}.",
                )
            )
    return findings


def overlap_fraction(mesh: bpy.types.Mesh, uv_data: bpy.types.bpy_prop_collection) -> float:
    """Return the share of covered texels that two or more faces both cover."""
    owner = array("i", [_NO_FACE]) * (GRID * GRID)
    shared = bytearray(GRID * GRID)
    for poly in mesh.polygons:
        indices = range(poly.loop_start, poly.loop_start + poly.loop_total)
        points = [(uv_data[index].uv.x * GRID, uv_data[index].uv.y * GRID) for index in indices]
        for corners in _fan(points):
            _rasterize(corners, poly.index, owner, shared)
    covered = sum(1 for value in owner if value != _NO_FACE)
    if covered == 0:
        return 0.0
    return sum(shared) / covered


def _fan(points: Sequence[Point]) -> Iterator[tuple[Point, Point, Point]]:
    for index in range(1, len(points) - 1):
        yield points[0], points[index], points[index + 1]


def _rasterize(
    corners: tuple[Point, Point, Point],
    face: int,
    owner: array,
    shared: bytearray,
) -> None:
    a, b, c = corners
    twice_area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(twice_area) < 1e-12:
        return
    sign = 1.0 if twice_area > 0 else -1.0
    x0 = max(0, math.floor(min(a[0], b[0], c[0])))
    x1 = min(GRID - 1, math.ceil(max(a[0], b[0], c[0])))
    y0 = max(0, math.floor(min(a[1], b[1], c[1])))
    y1 = min(GRID - 1, math.ceil(max(a[1], b[1], c[1])))
    for row in range(y0, y1 + 1):
        py = row + 0.5
        for col in range(x0, x1 + 1):
            px = col + 0.5
            w0 = sign * ((c[0] - b[0]) * (py - b[1]) - (c[1] - b[1]) * (px - b[0]))
            w1 = sign * ((a[0] - c[0]) * (py - c[1]) - (a[1] - c[1]) * (px - c[0]))
            w2 = sign * ((b[0] - a[0]) * (py - a[1]) - (b[1] - a[1]) * (px - a[0]))
            if w0 < 0 or w1 < 0 or w2 < 0:
                continue
            index = row * GRID + col
            prior = owner[index]
            if prior == _NO_FACE:
                owner[index] = face
            elif prior != face:
                shared[index] = 1
