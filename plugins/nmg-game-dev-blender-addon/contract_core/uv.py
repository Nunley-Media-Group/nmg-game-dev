"""UV checks: exactly one map named UVMap, and no overlapping islands for unique-bake classes.

Overlap is measured by sampling every UV triangle at the texel centers of a GRID x GRID texel grid.
A texel is covered when a triangle contains its center, and shared when two or more faces cover
it. Overlap fails when more than OVERLAP_LIMIT of the covered texels are shared.

Rasterization runs in numpy over batches of whole triangles. Covered texels never exceed
GRID * GRID, so once the shared count exceeds OVERLAP_LIMIT * GRID * GRID the fraction stays above
the limit whatever the rest of the layout does. Rasterization then stops and the result is a lower
bound (exact=False) with the same pass/fail outcome as a full run (#133).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import NamedTuple

import bpy
import numpy as np

from .report import finding

GRID = 512
OVERLAP_LIMIT = 0.005
_NO_FACE = -1
_UV_MAP = "UVMap"
_BATCH_TEXELS = 1 << 20
_MIN_TWICE_AREA = 1e-12

Point = tuple[float, float]


@dataclass(frozen=True)
class OverlapResult:
    """The shared share of covered texels for one set of UV faces.

    exact is False when rasterization stopped early. The fraction is then a lower bound on the full
    fraction, and it is above OVERLAP_LIMIT. triangles_rasterized counts the triangles processed.
    """

    fraction: float
    exact: bool
    triangles_rasterized: int
    triangles_total: int


class _Triangles(NamedTuple):
    """Triangles in texel units with the per-triangle values each batch reads."""

    corners: np.ndarray  # (T, 3, 2) float64
    faces: np.ndarray  # (T,) int64, the owning face id
    sign: np.ndarray  # (T,) float64, +1 or -1 from the winding
    x0: np.ndarray  # (T,) int64, clamped bounding box
    y0: np.ndarray  # (T,) int64
    width: np.ndarray  # (T,) int64, 0 when the box covers no texel center
    height: np.ndarray  # (T,) int64


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
        result = mesh_overlap(mesh, layers[0].data)
        if result.fraction > OVERLAP_LIMIT:
            findings.append(finding("uv.overlap", name, _overlap_message(name, result)))
    return findings


def _overlap_message(name: str, result: OverlapResult) -> str:
    bound = "" if result.exact else "at least "
    return (
        f"{name}: {bound}{result.fraction:.1%} of covered UV texels are shared by two or more "
        f"faces; the limit is {OVERLAP_LIMIT:.1%}."
    )


def overlap_fraction(mesh: bpy.types.Mesh, uv_data: bpy.types.bpy_prop_collection) -> float:
    """Return the share of covered texels that two or more faces both cover."""
    return mesh_overlap(mesh, uv_data).fraction


def mesh_overlap(mesh: bpy.types.Mesh, uv_data: bpy.types.bpy_prop_collection) -> OverlapResult:
    """Rasterize every polygon of mesh, fan-triangulated, with its face id as the polygon index.

    The UVs and the polygon loop ranges are read in bulk, not per loop.
    """
    polygon_count = len(mesh.polygons)
    if polygon_count == 0:
        return _overlap_core(np.empty((0, 3, 2)), np.empty(0, dtype=np.int64))
    uv = np.empty(2 * len(uv_data), dtype=np.float32)
    uv_data.foreach_get("uv", uv)
    starts = np.empty(polygon_count, dtype=np.int32)
    mesh.polygons.foreach_get("loop_start", starts)
    totals = np.empty(polygon_count, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", totals)

    uv = uv.astype(np.float64).reshape(-1, 2) * GRID
    counts = np.maximum(totals.astype(np.int64) - 2, 0)
    faces = np.repeat(np.arange(polygon_count, dtype=np.int64), counts)
    within = np.arange(faces.size, dtype=np.int64) - np.repeat(np.cumsum(counts) - counts, counts)
    first = np.repeat(starts.astype(np.int64), counts)
    # Fan triangle k of a polygon is (corner 0, corner k, corner k + 1), with k from 1 to n - 2.
    corners = np.stack((uv[first], uv[first + within + 1], uv[first + within + 2]), axis=1)
    return _overlap_core(corners, faces)


def polygon_overlap(faces: Iterable[tuple[int, Sequence[Point]]]) -> OverlapResult:
    """Rasterize faces given as (face id, UV corners). Face ids must be unique across everything.

    The bake core checks several meshes together, which the single-mesh overlap_fraction cannot.
    """
    corner_parts: list[np.ndarray] = []
    face_parts: list[np.ndarray] = []
    for face, uv_points in faces:
        if len(uv_points) < 3:
            continue
        points = np.asarray(uv_points, dtype=np.float64).reshape(-1, 2) * GRID
        count = points.shape[0] - 2
        corner_parts.append(
            np.stack(
                (np.repeat(points[:1], count, axis=0), points[1:-1], points[2:]),
                axis=1,
            )
        )
        face_parts.append(np.full(count, face, dtype=np.int64))
    if not corner_parts:
        return _overlap_core(np.empty((0, 3, 2)), np.empty(0, dtype=np.int64))
    return _overlap_core(np.concatenate(corner_parts), np.concatenate(face_parts))


def polygon_overlap_fraction(faces: Iterable[tuple[int, Sequence[Point]]]) -> float:
    """Return the shared share of covered texels for faces given as (face id, UV corners)."""
    return polygon_overlap(faces).fraction


def _overlap_core(corners: np.ndarray, faces: np.ndarray) -> OverlapResult:
    """Rasterize triangles (T, 3, 2) in texel units, owned by faces (T,), and stop once decided."""
    tris = _prepare(corners, faces)
    total = int(faces.shape[0])
    candidates = tris.width * tris.height
    cumulative = np.zeros(total + 1, dtype=np.int64)
    np.cumsum(candidates, out=cumulative[1:])
    owner = np.full(GRID * GRID, _NO_FACE, dtype=np.int64)
    shared = np.zeros(GRID * GRID, dtype=bool)
    limit = OVERLAP_LIMIT * GRID * GRID
    shared_count = 0
    start = 0
    while start < total:
        # The largest end whose batch holds at most _BATCH_TEXELS candidates. A triangle that
        # alone exceeds the bound is a batch of its own.
        end = int(np.searchsorted(cumulative, cumulative[start] + _BATCH_TEXELS, side="right")) - 1
        end = max(end, start + 1)
        shared_count += _rasterize_batch(tris, candidates, start, end, owner, shared)
        start = end
        if shared_count > limit:
            return OverlapResult(shared_count / (GRID * GRID), False, end, total)
    covered = int(np.count_nonzero(owner != _NO_FACE))
    fraction = shared_count / covered if covered else 0.0
    return OverlapResult(fraction, True, total, total)


def _prepare(corners: np.ndarray, faces: np.ndarray) -> _Triangles:
    ab = corners[:, 1] - corners[:, 0]
    ac = corners[:, 2] - corners[:, 0]
    twice_area = ab[:, 0] * ac[:, 1] - ab[:, 1] * ac[:, 0]
    x0, x1 = _clamped_span(corners[:, :, 0])
    y0, y1 = _clamped_span(corners[:, :, 1])
    live = (np.abs(twice_area) >= _MIN_TWICE_AREA) & (x0 <= x1) & (y0 <= y1)
    return _Triangles(
        corners=corners,
        faces=faces.astype(np.int64),
        sign=np.where(twice_area > 0, 1.0, -1.0),
        x0=x0,
        y0=y0,
        width=np.where(live, x1 - x0 + 1, 0),
        height=np.where(live, y1 - y0 + 1, 0),
    )


def _clamped_span(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The inclusive texel range [floor(min), ceil(max)] of each triangle, clamped to the grid.

    Clamping to [0, GRID] and [-1, GRID - 1] keeps an empty range empty, and keeps huge UVs from
    overflowing the integer cast.
    """
    low = np.clip(np.floor(values.min(axis=1)), 0, GRID).astype(np.int64)
    high = np.clip(np.ceil(values.max(axis=1)), -1, GRID - 1).astype(np.int64)
    return low, high


def _rasterize_batch(
    tris: _Triangles,
    candidates: np.ndarray,
    start: int,
    end: int,
    owner: np.ndarray,
    shared: np.ndarray,
) -> int:
    """Rasterize triangles [start, end) and return how many texels became shared."""
    live = np.flatnonzero(candidates[start:end]) + start
    if live.size == 0:
        return 0
    counts = candidates[live]
    tri = np.repeat(live, counts)
    within = np.arange(tri.size, dtype=np.int64) - np.repeat(np.cumsum(counts) - counts, counts)
    col = tris.x0[tri] + within % tris.width[tri]
    row = tris.y0[tri] + within // tris.width[tri]
    px = col + 0.5
    py = row + 0.5
    a = tris.corners[tri, 0]
    b = tris.corners[tri, 1]
    c = tris.corners[tri, 2]
    sign = tris.sign[tri]
    w0 = sign * ((c[:, 0] - b[:, 0]) * (py - b[:, 1]) - (c[:, 1] - b[:, 1]) * (px - b[:, 0]))
    w1 = sign * ((a[:, 0] - c[:, 0]) * (py - c[:, 1]) - (a[:, 1] - c[:, 1]) * (px - c[:, 0]))
    w2 = sign * ((b[:, 0] - a[:, 0]) * (py - a[:, 1]) - (b[:, 1] - a[:, 1]) * (px - a[:, 0]))
    inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
    if not inside.any():
        return 0
    texels = row[inside] * GRID + col[inside]
    return _record_hits(owner, shared, texels, tris.faces[tri[inside]])


def _record_hits(
    owner: np.ndarray, shared: np.ndarray, texels: np.ndarray, faces: np.ndarray
) -> int:
    """Fold one batch of (texel, face) hits into owner and shared; return the newly shared count.

    A texel is shared once two distinct faces cover it. Within the batch, the lowest and highest
    face per texel decide that; a texel already owned by another face is shared too.
    """
    order = np.lexsort((faces, texels))
    texels = texels[order]
    faces = faces[order]
    starts = np.flatnonzero(np.r_[True, texels[1:] != texels[:-1]])
    ends = np.r_[starts[1:], texels.size] - 1
    cells = texels[starts]
    low = faces[starts]
    high = faces[ends]
    prior = owner[cells]
    became_shared = (low != high) | ((prior != _NO_FACE) & (prior != low))
    newly = int(np.count_nonzero(became_shared & ~shared[cells]))
    shared[cells[became_shared]] = True
    uncovered = prior == _NO_FACE
    owner[cells[uncovered]] = low[uncovered]
    return newly
