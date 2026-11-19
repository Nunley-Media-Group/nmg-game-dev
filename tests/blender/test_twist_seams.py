"""Twist seams are repaired by cleanup and named by the validator: AC1-AC6 of #243 (SCN001-SCN006).

The fixture is a figure-8 Klein bottle with a three-edge tube, ``klein(32, 3)``: a closed island
that joins itself with reversed winding, so after recalculation five edges are walked the same way
by both of their faces. Those edges are its twist seam, and the six faces linked to them are all
cleanup has to delete. SCN005 guards meshes without a seam, so it passes on the pre-fix code too.

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

import bmesh  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from .contract_fixtures import build_crate, clear_scene  # noqa: E402
from .normals_fixtures import klein, to_mesh  # noqa: E402

NORMALS = "geometry.normals"
TWIST = "geometry.twist_seam"
NU, NV = 32, 3
SEAM_FACES = 6
SEAM_EDGES = 5
REPEATS = 3
TWIST_LOCATION = (1.5, -2.0, 0.75)
_DECIMALS = 6
#: Positions are compared after rounding to 6 decimals, so allow one rounding step either way.
_TOLERANCE = 2e-6

Corners = frozenset[tuple[float, ...]]


@pytest.fixture(autouse=True)
def _isolated_scene() -> Iterator[None]:
    yield
    clear_scene()


@pytest.fixture()
def geometry(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core.geometry")


@pytest.fixture()
def meshes(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.variants_core.meshes")


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.variants_core")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _twisted(name: str = "Twist") -> Any:
    return klein(NU, NV, name)


def _corners(mesh: Any, polygon: Any) -> Corners:
    return frozenset(
        tuple(round(c, _DECIMALS) for c in mesh.vertices[index].co) for index in polygon.vertices
    )


def _bm_corners(face: Any) -> Corners:
    return frozenset(tuple(round(c, _DECIMALS) for c in vert.co) for vert in face.verts)


def _seam(geometry: Any, mesh: Any) -> tuple[set[Corners], list[Vector]]:
    """The faces linked to the twist seam edges after the shared recalculation, and the edges'
    mesh-space midpoints, from a copy so mesh is unchanged."""
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.normal_update()
        geometry.recalc_island_normals(bm)
        edges = geometry.twist_seam_edges(bm.faces)
        faces = {_bm_corners(face) for edge in edges for face in edge.link_faces}
        midpoints = [(edge.verts[0].co + edge.verts[1].co) / 2 for edge in edges]
    finally:
        bm.free()
    return faces, midpoints


def _findings(geometry: Any, name: str, mesh: Any) -> dict[str, dict[str, Any]]:
    return {item["rule"]: item for item in geometry.geometry_findings(name, mesh)}


def _snapshot(mesh: Any) -> tuple[list[tuple[float, ...]], list[tuple[int, ...]]]:
    return [tuple(v.co) for v in mesh.vertices], [tuple(p.vertices) for p in mesh.polygons]


def _near(position: Any, points: list[Vector]) -> bool:
    return any((Vector(position) - point).length <= _TOLERANCE for point in points)


def _twist_faces(repair: Any) -> int:
    """Faces the twist repair deleted. The pre-fix clean_mesh returns None and repairs nothing."""
    return 0 if repair is None else int(repair["faces"])


# ---------------------------------------------------------------------------
# AC1 / SCN001: cleanup repairs a twist seam with a minimal deletion
# ---------------------------------------------------------------------------


def test_scn001_cleanup_deletes_only_the_twist_seam_faces(geometry: Any, meshes: Any) -> None:
    source = _twisted()
    before = {_corners(source, polygon) for polygon in source.polygons}
    seam_faces, _midpoints = _seam(geometry, source)
    assert len(seam_faces) == SEAM_FACES, "the fixture must have 6 faces at its twist seam"

    meshes.clean_mesh(source)

    after = {_corners(source, polygon) for polygon in source.polygons}
    assert after <= before, "clean_mesh must not add or reshape a face"
    assert before - after == seam_faces
    findings = _findings(geometry, "Twist", source)
    assert NORMALS not in findings
    assert TWIST not in findings


# ---------------------------------------------------------------------------
# AC2 / SCN002: the repaired mesh is stable
# ---------------------------------------------------------------------------


def test_scn002_repaired_mesh_is_stable(geometry: Any, meshes: Any) -> None:
    mesh = _twisted()
    meshes.clean_mesh(mesh)
    settled = _snapshot(mesh)

    for _ in range(REPEATS):
        meshes.clean_mesh(mesh)
        assert _snapshot(mesh) == settled
        findings = _findings(geometry, "Twist", mesh)
        assert NORMALS not in findings
        assert TWIST not in findings


# ---------------------------------------------------------------------------
# AC3 / SCN003: the validator names the seam
# ---------------------------------------------------------------------------


def test_scn003_validator_reports_the_twist_seam(geometry: Any) -> None:
    mesh = _twisted()
    _faces, midpoints = _seam(geometry, mesh)

    findings = _findings(geometry, "Twist", mesh)

    assert NORMALS not in findings
    twist = findings[TWIST]
    assert twist["count"] == SEAM_EDGES
    assert twist["samples"], "the finding must carry located samples"
    for sample in twist["samples"]:
        edge = mesh.edges[sample["index"]]
        a, b = (mesh.vertices[index].co for index in edge.vertices)
        assert _near(sample["position"], [(a + b) / 2]), "a sample is its edge's midpoint"
        assert _near(sample["position"], midpoints), "a sample sits on a seam edge"


# ---------------------------------------------------------------------------
# AC4 / SCN004: the repair is deterministic
# ---------------------------------------------------------------------------


def test_scn004_twist_repair_is_deterministic(meshes: Any) -> None:
    first, second = _twisted("TwistA"), _twisted("TwistB")

    meshes.clean_mesh(first)
    meshes.clean_mesh(second)

    assert _snapshot(first) == _snapshot(second)
    assert [tuple(p.normal) for p in first.polygons] == [tuple(p.normal) for p in second.polygons]


# ---------------------------------------------------------------------------
# AC5 / SCN005: meshes without a twist seam are unaffected (guard)
# ---------------------------------------------------------------------------


def test_scn005_open_quad_is_unaffected(geometry: Any, meshes: Any) -> None:
    bm = bmesh.new()
    corners = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
    bm.faces.new([bm.verts.new(co) for co in corners])
    mesh = to_mesh("Quad", bm)
    assert _findings(geometry, "Quad", mesh) == {}

    repair = meshes.clean_mesh(mesh)

    assert _twist_faces(repair) == 0
    assert len(mesh.polygons) == 1
    assert _findings(geometry, "Quad", mesh) == {}


def test_scn005_inside_out_cube_is_unaffected(geometry: Any, meshes: Any) -> None:
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    mesh = to_mesh("Cube", bm)
    findings = _findings(geometry, "Cube", mesh)
    assert TWIST not in findings
    assert findings[NORMALS]["count"] == 6

    repair = meshes.clean_mesh(mesh)

    assert _twist_faces(repair) == 0
    assert len(mesh.polygons) == 6
    findings = _findings(geometry, "Cube", mesh)
    assert TWIST not in findings
    assert NORMALS not in findings


def test_scn005_clean_crate_is_unaffected(geometry: Any, meshes: Any) -> None:
    build_crate()
    mesh = bpy.data.objects["SM_Crate"].data
    before = meshes.triangle_count(mesh)
    assert TWIST not in _findings(geometry, "SM_Crate", mesh)

    repair = meshes.clean_mesh(mesh)

    assert _twist_faces(repair) == 0
    assert meshes.triangle_count(mesh) == before
    assert [
        rule for rule in _findings(geometry, "SM_Crate", mesh) if rule.startswith("geometry.")
    ] == []


# ---------------------------------------------------------------------------
# AC6 / SCN006: cleanup reports the twist repair
# ---------------------------------------------------------------------------


def test_scn006_cleanup_desktop_reports_the_twist_repair(geometry: Any, core: Any) -> None:
    build_crate()
    collection = bpy.data.collections.new("Twist")
    bpy.context.scene.collection.children.link(collection)
    mesh = _twisted("SM_Twist")
    _faces, midpoints = _seam(geometry, mesh)
    obj = bpy.data.objects.new("SM_Twist", mesh)
    obj.location = TWIST_LOCATION
    collection.objects.link(obj)
    bpy.context.view_layer.update()
    world: Matrix = obj.matrix_world.copy()
    world_midpoints = [world @ point for point in midpoints]

    twist = core.cleanup_desktop("Twist")["objects"]
    crate = core.cleanup_desktop("Crate")["objects"]

    (entry,) = twist
    repair = entry["twist_repair"]
    assert repair["faces"] == SEAM_FACES
    assert repair["edges"] == SEAM_EDGES
    assert 0 < len(repair["samples"]) <= 5
    for sample in repair["samples"]:
        assert sample == [round(coord, _DECIMALS) for coord in sample], "samples are rounded"
        assert _near(sample, world_midpoints), "a sample is a world-space seam midpoint"

    (crate_entry,) = crate
    assert crate_entry["twist_repair"] == {"faces": 0, "edges": 0, "samples": []}
