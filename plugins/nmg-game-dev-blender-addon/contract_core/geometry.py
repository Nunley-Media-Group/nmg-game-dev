"""Mesh checks: loose vertices, zero-area faces, duplicate vertices, inconsistent normals, and
twist seams.

The caller passes a mesh it owns (an evaluated copy), so nothing here touches the scene. Each
finding counts every offending element and carries located samples: the lowest SAMPLE_LIMIT
element indices, each with its world-space position and vertex-group names (#153).
"""

from __future__ import annotations

from collections import deque
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
        flagged, seam_edges = normal_violations(bm)
        if flagged:
            samples = [_face_sample(face, world, deform, names) for face in flagged[:SAMPLE_LIMIT]]
            findings.append(
                _located(
                    "geometry.normals",
                    name,
                    f"{name} has {len(flagged)} face(s) whose normals are inconsistent or inward",
                    len(flagged),
                    samples,
                )
            )
        if seam_edges:
            samples = [
                _edge_sample(edge, world, deform, names) for edge in seam_edges[:SAMPLE_LIMIT]
            ]
            findings.append(
                _located(
                    "geometry.twist_seam",
                    name,
                    f"{name} has {len(seam_edges)} twist seam edge(s) "
                    "where no winding is consistent",
                    len(seam_edges),
                    samples,
                )
            )
    finally:
        bm.free()
    return findings


def recalc_island_normals(bm: bmesh.types.BMesh) -> None:
    """Recalculate normals once per edge-connected island, in the order ``_islands`` gives.

    The clean in variants_core/meshes.py calls this, so it recalculates normals with the same
    island grouping and face order as the ``geometry.normals`` rule (#232).
    """
    for island in _islands(bm):
        bmesh.ops.recalc_face_normals(bm, faces=island)


def normal_violations(
    bm: bmesh.types.BMesh,
) -> tuple[list[bmesh.types.BMFace], list[bmesh.types.BMEdge]]:
    """Return, in index order, the faces that break the normals rule and the twist seam edges.

    An open island has an edge with one linked face, so it is a sheet: only its winding is checked,
    and nothing about its position or an outside direction matters. A closed island must face
    outward, judged on that island alone so other islands cannot change the answer. A closed island
    that still has twist seam edges after its recalculation has no consistent winding at all, so it
    contributes those edges and none of its faces (#243).
    """
    flagged: list[bmesh.types.BMFace] = []
    seams: list[bmesh.types.BMEdge] = []
    for island in _islands(bm):
        if any(len(edge.link_faces) == 1 for face in island for edge in face.edges):
            flagged.extend(_winding_violations(island))
            continue
        outward = _outward_violations(bm, island)
        island_seams = twist_seam_edges(island)
        if island_seams:
            seams.extend(island_seams)
        else:
            flagged.extend(outward)
    return sorted(flagged, key=lambda face: face.index), sorted(seams, key=lambda edge: edge.index)


def twist_seam_edges(faces: Iterable[bmesh.types.BMFace]) -> list[bmesh.types.BMEdge]:
    """Return, in edge-index order, the edges whose two linked faces walk them the same way.

    Only edges with exactly two linked faces, both in ``faces``, count. After its normals are
    recalculated an orientable island has no such edge, and an island that joins itself with
    reversed winding always has one; those edges are its twist seam (#243).
    """
    members = set(faces)
    seams: set[bmesh.types.BMEdge] = set()
    for face in members:
        for loop in face.loops:
            edge = loop.edge
            if edge in seams or len(edge.link_faces) != 2:
                continue
            other = next(linked for linked in edge.link_faces if linked != face)
            if other not in members:
                continue
            if _walk_direction(loop) == _walk_direction(_loop_on_edge(other, edge)):
                seams.add(edge)
    return sorted(seams, key=lambda edge: edge.index)


def _islands(bm: bmesh.types.BMesh) -> list[list[bmesh.types.BMFace]]:
    """Group faces into edge-connected islands; faces that touch only at a vertex stay apart."""
    islands: list[list[bmesh.types.BMFace]] = []
    seen: set[bmesh.types.BMFace] = set()
    for seed in bm.faces:
        if seed in seen:
            continue
        seen.add(seed)
        island = [seed]
        queue = deque([seed])
        while queue:
            face = queue.popleft()
            for edge in face.edges:
                for other in edge.link_faces:
                    if other not in seen:
                        seen.add(other)
                        island.append(other)
                        queue.append(other)
        islands.append(island)
    return islands


def _winding_violations(island: list[bmesh.types.BMFace]) -> list[bmesh.types.BMFace]:
    """Return the faces that must flip so neighbours walk every shared edge in opposite directions.

    Propagation runs across edges with exactly two linked faces, from each component's first face.
    A component's answer is its minority, which is the same whichever face seeded it and whichever
    way the sheet faces. Nothing is compared with an outside direction.
    """
    flip: dict[bmesh.types.BMFace, int] = {}
    violations: list[bmesh.types.BMFace] = []
    for seed in island:
        if seed in flip:
            continue
        flip[seed] = 0
        component = [seed]
        queue = deque([seed])
        while queue:
            face = queue.popleft()
            for loop in face.loops:
                edge = loop.edge
                if len(edge.link_faces) != 2:
                    continue
                other = next(linked for linked in edge.link_faces if linked != face)
                if other in flip:
                    continue
                same_walk = _walk_direction(loop) == _walk_direction(_loop_on_edge(other, edge))
                flip[other] = flip[face] ^ int(same_walk)
                component.append(other)
                queue.append(other)
        marked = sum(flip[member] for member in component)
        minority = 1 if marked <= len(component) - marked else 0
        violations.extend(member for member in component if flip[member] == minority)
    return violations


def _walk_direction(loop: bmesh.types.BMLoop) -> int:
    """0 when the face walks its edge from the edge's first vertex, 1 when from the second."""
    return 0 if loop.vert == loop.edge.verts[0] else 1


def _loop_on_edge(face: bmesh.types.BMFace, edge: bmesh.types.BMEdge) -> bmesh.types.BMLoop:
    return next(loop for loop in face.loops if loop.edge == edge)


def _outward_violations(
    bm: bmesh.types.BMesh, island: list[bmesh.types.BMFace]
) -> list[bmesh.types.BMFace]:
    """Return the faces of a closed island that recalculating its normals outward turns around."""
    before = {face: face.normal.copy() for face in island}
    bmesh.ops.recalc_face_normals(bm, faces=island)
    bm.normal_update()
    return [face for face in island if face.normal.dot(before[face]) < 0]


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


def _edge_sample(
    edge: bmesh.types.BMEdge,
    world: Matrix,
    deform: bmesh.types.BMLayerItem | None,
    names: Sequence[str],
) -> dict[str, Any]:
    first, second = edge.verts
    return {
        "index": edge.index,
        "position": _position(world @ ((first.co + second.co) / 2)),
        "vertex_groups": _group_names(edge.verts, deform, names),
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
