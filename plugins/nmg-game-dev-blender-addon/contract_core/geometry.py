"""Mesh checks: loose vertices, zero-area faces, duplicate vertices, and inconsistent normals.

The caller passes a mesh it owns (an evaluated copy), so nothing here touches the scene. Each
finding counts every offending element and carries located samples: the lowest SAMPLE_LIMIT
element indices, each with its world-space position and vertex-group names (#153).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import bmesh
import bpy
from mathutils import Matrix, Vector

from .report import finding

DUPLICATE_DISTANCE = 1e-5
ZERO_AREA_LIMIT = 1e-8
SAMPLE_LIMIT = 5
_POSITION_DECIMALS = 6
_MESSAGE_DECIMALS = 4


def geometry_findings(
    name: str,
    mesh: bpy.types.Mesh,
    matrix_world: Matrix | None = None,
    group_names: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Return one finding per geometry rule that has offending elements.

    ``matrix_world`` is the source object's world matrix (identity when None), and
    ``group_names`` lists the source object's vertex-group names in index order.
    """
    world = Matrix.Identity(4) if matrix_world is None else matrix_world
    names = list(group_names)
    findings: list[dict[str, Any]] = []
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.normal_update()
        deform = bm.verts.layers.deform.active
        loose = [vert for vert in bm.verts if not vert.link_edges]
        if loose:
            samples = [_vertex_sample(vert, world, deform, names) for vert in loose[:SAMPLE_LIMIT]]
            findings.append(
                _located(
                    "geometry.loose",
                    name,
                    f"{name} has {len(loose)} loose vertex(es)",
                    len(loose),
                    samples,
                )
            )
        zero_area = [face for face in bm.faces if face.calc_area() < ZERO_AREA_LIMIT]
        if zero_area:
            samples = [
                _face_sample(face, world, deform, names) for face in zero_area[:SAMPLE_LIMIT]
            ]
            findings.append(
                _located(
                    "geometry.zero_area",
                    name,
                    f"{name} has {len(zero_area)} zero-area face(s)",
                    len(zero_area),
                    samples,
                )
            )
        doubles = bmesh.ops.find_doubles(bm, verts=bm.verts[:], dist=DUPLICATE_DISTANCE)
        pairs = sorted(doubles["targetmap"].items(), key=lambda pair: pair[0].index)
        if pairs:
            samples = [
                _duplicate_sample(dup, target, world, deform, names)
                for dup, target in pairs[:SAMPLE_LIMIT]
            ]
            findings.append(
                _located(
                    "geometry.duplicates",
                    name,
                    f"{name} has {len(pairs)} duplicate vertex(es)",
                    len(pairs),
                    samples,
                )
            )
        flipped = _flipped_faces(bm)
        if flipped:
            samples = [_face_sample(face, world, deform, names) for face in flipped[:SAMPLE_LIMIT]]
            findings.append(
                _located(
                    "geometry.normals",
                    name,
                    f"{name} has {len(flipped)} face(s) whose normals are inconsistent or inward",
                    len(flipped),
                    samples,
                )
            )
    finally:
        bm.free()
    return findings


def _flipped_faces(bm: bmesh.types.BMesh) -> list[bmesh.types.BMFace]:
    """Return, in index order, the faces that recalculating normals on this copy turns around."""
    before = [face.normal.copy() for face in bm.faces]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()
    return [face for face, old in zip(bm.faces, before, strict=True) if face.normal.dot(old) < 0]


def _located(
    rule: str, name: str, text: str, total: int, samples: list[dict[str, Any]]
) -> dict[str, Any]:
    """One finding: the count-bearing message, the full total, and the capped samples."""
    x, y, z = (f"{coord:.{_MESSAGE_DECIMALS}f}" for coord in samples[0]["position"])
    message = f"{text}; first at ({x}, {y}, {z})."
    return finding(rule, name, message) | {"count": total, "samples": samples}


def _vertex_sample(
    vert: bmesh.types.BMVert,
    world: Matrix,
    deform: bmesh.types.BMLayerItem | None,
    names: Sequence[str],
) -> dict[str, Any]:
    return {
        "index": vert.index,
        "position": _position(world @ vert.co),
        "vertex_groups": _group_names([vert], deform, names),
    }


def _duplicate_sample(
    dup: bmesh.types.BMVert,
    target: bmesh.types.BMVert,
    world: Matrix,
    deform: bmesh.types.BMLayerItem | None,
    names: Sequence[str],
) -> dict[str, Any]:
    return {
        "index": dup.index,
        "position": _position(world @ dup.co),
        "vertex_groups": _group_names([dup, target], deform, names),
        "coincides_with": target.index,
    }


def _face_sample(
    face: bmesh.types.BMFace,
    world: Matrix,
    deform: bmesh.types.BMLayerItem | None,
    names: Sequence[str],
) -> dict[str, Any]:
    return {
        "index": face.index,
        "position": _position(world @ face.calc_center_median()),
        "vertex_groups": _group_names(face.verts, deform, names),
    }


def _position(point: Vector) -> list[float]:
    return [round(float(coord), _POSITION_DECIMALS) for coord in point]


def _group_names(
    verts: Iterable[bmesh.types.BMVert],
    deform: bmesh.types.BMLayerItem | None,
    names: Sequence[str],
) -> list[str]:
    """Sorted unique vertex-group names of the verts; empty without a deform layer or groups."""
    if deform is None:
        return []
    indices = {index for vert in verts for index in vert[deform].keys()}
    return sorted({names[index] for index in indices if index < len(names)})
