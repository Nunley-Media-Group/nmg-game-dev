"""Mesh checks: loose vertices, zero-area faces, duplicate vertices, and inconsistent normals.

The caller passes a mesh it owns (an evaluated copy), so nothing here touches the scene.
"""

from __future__ import annotations

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
        flipped = _flipped_faces(bm)
        if flipped:
            findings.append(
                finding(
                    "geometry.normals",
                    name,
                    f"{name} has {flipped} face(s) whose normals are inconsistent or inward.",
                )
            )
    finally:
        bm.free()
    return findings


def _flipped_faces(bm: bmesh.types.BMesh) -> int:
    """Count faces that recalculating normals on this copy turns around."""
    before = [face.normal.copy() for face in bm.faces]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()
    return sum(1 for face, old in zip(bm.faces, before, strict=True) if face.normal.dot(old) < 0)
