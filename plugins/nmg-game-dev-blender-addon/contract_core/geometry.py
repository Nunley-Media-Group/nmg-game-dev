"""Mesh checks: loose vertices, zero-area faces, duplicate vertices, and inconsistent normals.

The caller passes a mesh it owns (an evaluated copy), so nothing here touches the scene.
"""

from __future__ import annotations

from collections import deque

import bmesh
import bpy

from .report import finding

DUPLICATE_DISTANCE = 1e-5
ZERO_AREA_LIMIT = 1e-8


def geometry_findings(name: str, mesh: bpy.types.Mesh) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.normal_update()
        loose = sum(1 for vert in bm.verts if not vert.link_edges)
        if loose:
            findings.append(
                finding("geometry.loose", name, f"{name} has {loose} loose vertex(es).")
            )
        zero_area = sum(1 for face in bm.faces if face.calc_area() < ZERO_AREA_LIMIT)
        if zero_area:
            findings.append(
                finding("geometry.zero_area", name, f"{name} has {zero_area} zero-area face(s).")
            )
        doubles = bmesh.ops.find_doubles(bm, verts=bm.verts[:], dist=DUPLICATE_DISTANCE)
        if doubles["targetmap"]:
            count = len(doubles["targetmap"])
            findings.append(
                finding("geometry.duplicates", name, f"{name} has {count} duplicate vertex(es).")
            )
        violations = _normal_violations(bm)
        if violations:
            findings.append(
                finding(
                    "geometry.normals",
                    name,
                    f"{name} has {violations} face(s) whose normals are inconsistent or inward.",
                )
            )
    finally:
        bm.free()
    return findings


def _normal_violations(bm: bmesh.types.BMesh) -> int:
    """Count faces that break the normals rule for their island.

    An open island has an edge with one linked face, so it is a sheet: only its winding is checked,
    and nothing about its position or an outside direction matters. A closed island must face
    outward, judged on that island alone so other islands cannot change the answer.
    """
    total = 0
    for island in _islands(bm):
        if any(len(edge.link_faces) == 1 for face in island for edge in face.edges):
            total += _winding_violations(island)
        else:
            total += _outward_violations(bm, island)
    return total


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


def _winding_violations(island: list[bmesh.types.BMFace]) -> int:
    """Count the faces that must flip so neighbours walk every shared edge in opposite directions.

    Propagation runs across edges with exactly two linked faces, from each component's first face.
    A component's answer is its minority, which is the same whichever face seeded it and whichever
    way the sheet faces. Nothing is compared with an outside direction.
    """
    flip: dict[bmesh.types.BMFace, int] = {}
    violations = 0
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
        violations += min(marked, len(component) - marked)
    return violations


def _walk_direction(loop: bmesh.types.BMLoop) -> int:
    """0 when the face walks its edge from the edge's first vertex, 1 when from the second."""
    return 0 if loop.vert == loop.edge.verts[0] else 1


def _loop_on_edge(face: bmesh.types.BMFace, edge: bmesh.types.BMEdge) -> bmesh.types.BMLoop:
    return next(loop for loop in face.loops if loop.edge == edge)


def _outward_violations(bm: bmesh.types.BMesh, island: list[bmesh.types.BMFace]) -> int:
    """Count the faces of a closed island that recalculating its normals outward turns around."""
    before = {face: face.normal.copy() for face in island}
    bmesh.ops.recalc_face_normals(bm, faces=island)
    bm.normal_update()
    return sum(1 for face in island if face.normal.dot(before[face]) < 0)
