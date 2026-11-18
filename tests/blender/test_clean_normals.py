"""clean_mesh settles normals the way geometry.normals judges them: AC1-AC5 of #232 (SCN001-SCN005).

A figure-8 Klein bottle is a closed surface with no consistent orientation. With a fin on one
edge it is an open island whose winding passes the contract. The clean drops the fin, which
closes the island, and before the fix its whole-mesh recalculation left faces the per-island
check flags. SCN005 guards behavior that must not change, so it passes on the pre-fix code too.

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Iterator
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

import bmesh  # noqa: E402
from mathutils import Vector  # noqa: E402

from .contract_fixtures import build_crate, clear_scene  # noqa: E402

NORMALS = "geometry.normals"
KLEIN_RADIUS = 2.0
FIN_HEIGHT = 0.02
#: Bound on the fixture's winding repair; it settles in a pass or two.
WINDING_PASSES = 20
_DECIMALS = 6


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


@pytest.fixture()
def contract(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core")


# ---------------------------------------------------------------------------
# Fixtures: the Klein bottle and the finned Klein bottle
# ---------------------------------------------------------------------------


def _klein_point(u: float, v: float) -> tuple[float, float, float]:
    ring = KLEIN_RADIUS + math.cos(u / 2) * math.sin(v) - math.sin(u / 2) * math.sin(2 * v)
    z = math.sin(u / 2) * math.sin(v) + math.cos(u / 2) * math.sin(2 * v)
    return (ring * math.cos(u), ring * math.sin(u), z)


def _klein_bmesh(nu: int, nv: int) -> Any:
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


def _to_mesh(name: str, bm: Any) -> Any:
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh


def klein(nu: int = 16, nv: int = 8, name: str = "Klein") -> Any:
    return _to_mesh(name, _klein_bmesh(nu, nv))


def fin_klein(geometry: Any, name: str = "Klein") -> Any:
    """The Klein bottle with a fin on face 0's first edge, wound so the winding check passes."""
    bm = _klein_bmesh(16, 8)
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    face = bm.faces[0]
    a, b = face.loops[0].vert, face.loops[1].vert
    tip = (a.co + b.co) / 2 + face.normal * FIN_HEIGHT
    bm.faces.new((b, a, bm.verts.new(tip)))
    for _ in range(WINDING_PASSES):
        bm.faces.index_update()
        flagged = geometry.normal_violations(bm)
        if not flagged:
            break
        bmesh.ops.reverse_faces(bm, faces=flagged)
        bm.normal_update()
    else:
        pytest.fail("the fin_klein winding repair did not settle")
    return _to_mesh(name, bm)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rules(geometry: Any, name: str, mesh: Any) -> list[str]:
    return [item["rule"] for item in geometry.geometry_findings(name, mesh)]


def _corners(mesh: Any, polygon: Any) -> frozenset[tuple[float, ...]]:
    return frozenset(
        tuple(round(c, _DECIMALS) for c in mesh.vertices[index].co) for index in polygon.vertices
    )


def _pre_fix_clean(meshes: Any, mesh: Any) -> None:
    """The steps the pre-fix clean ran on the finned Klein: drop the fin, recalc the whole mesh."""
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        meshes._drop_non_manifold_faces(bm)
        meshes._delete_loose(bm)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()


def _klein_asset(geometry: Any) -> None:
    collection = bpy.data.collections.new("Klein")
    bpy.context.scene.collection.children.link(collection)
    collection.objects.link(bpy.data.objects.new("SM_Klein", fin_klein(geometry, "SM_Klein")))


def _geometry_findings(contract: Any, prefix: str, rules: tuple[str, ...]) -> list[Any]:
    report = contract.validate_asset("Klein", "standard_prop", authored=True)
    return [
        (item["rule"], item["target"])
        for item in report["findings"]
        if item["target"].startswith(prefix) and item["rule"].startswith(rules)
    ]


# ---------------------------------------------------------------------------
# AC1 / SCN001: cleanup output never fails geometry.normals
# ---------------------------------------------------------------------------


def test_scn001_cleanup_output_never_fails_geometry_normals(geometry: Any, meshes: Any) -> None:
    source = fin_klein(geometry)
    assert _rules(geometry, "Klein", source) == [], "the finned Klein must pass validate"

    pre_fix = source.copy()
    _pre_fix_clean(meshes, pre_fix)
    assert NORMALS in _rules(geometry, "Klein", pre_fix), "the fixture must reproduce #232"

    meshes.clean_mesh(source)
    assert NORMALS not in _rules(geometry, "Klein", source)


# ---------------------------------------------------------------------------
# AC2 / SCN002: a mesh that passes validate still passes after Desktop cleanup
# ---------------------------------------------------------------------------


def test_scn002_desktop_cleanup_keeps_validate_passing(
    geometry: Any, core: Any, contract: Any
) -> None:
    _klein_asset(geometry)
    assert _geometry_findings(contract, "SM_Klein", ("geometry.",)) == []

    core.cleanup_desktop("Klein")

    assert _geometry_findings(contract, "SM_Klein", ("geometry.",)) == []


# ---------------------------------------------------------------------------
# AC3 / SCN003: Mobile LODs never introduce geometry.normals failures
# ---------------------------------------------------------------------------


def test_scn003_mobile_lods_have_no_normals_findings(
    geometry: Any, core: Any, contract: Any
) -> None:
    _klein_asset(geometry)
    core.cleanup_desktop("Klein")

    core.optimize_mobile("Klein", "standard_prop")

    mobile = [obj.name for obj in bpy.data.objects if obj.name.startswith("SM_Klein_Mobile")]
    assert mobile, "optimize_mobile must build the Mobile variant"
    assert _geometry_findings(contract, "SM_Klein_Mobile", (NORMALS,)) == []


# ---------------------------------------------------------------------------
# AC4 / SCN004: faces with no consistent orientation are removed deterministically
# ---------------------------------------------------------------------------


def test_scn004_unorientable_faces_are_removed_deterministically(
    geometry: Any, meshes: Any
) -> None:
    source = klein(name="KleinSource")
    source_faces = {_corners(source, polygon) for polygon in source.polygons}
    bm = bmesh.new()
    try:
        bm.from_mesh(source)
        bm.normal_update()
        geometry.recalc_island_normals(bm)
        flagged = {
            frozenset(tuple(round(c, _DECIMALS) for c in vert.co) for vert in face.verts)
            for face in geometry.normal_violations(bm)
        }
    finally:
        bm.free()
    assert flagged, "the Klein bottle must keep flagged faces after the shared recalculation"

    first, second = klein(name="KleinA"), klein(name="KleinB")
    meshes.clean_mesh(first)
    meshes.clean_mesh(second)

    kept = {_corners(first, polygon) for polygon in first.polygons}
    assert kept <= source_faces, "clean_mesh must not add or reshape a face"
    assert not kept & flagged, "every flagged face must be deleted"
    assert NORMALS not in _rules(geometry, "KleinA", first)

    assert [tuple(v.co) for v in first.vertices] == [tuple(v.co) for v in second.vertices]
    assert [tuple(p.vertices) for p in first.polygons] == [
        tuple(p.vertices) for p in second.polygons
    ]
    assert [tuple(p.normal) for p in first.polygons] == [tuple(p.normal) for p in second.polygons]


# ---------------------------------------------------------------------------
# AC5 / SCN005: the normals rule and existing clean behavior are preserved (guard)
# ---------------------------------------------------------------------------


def test_scn005_open_quad_passes(geometry: Any) -> None:
    bm = bmesh.new()
    corners = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
    bm.faces.new([bm.verts.new(co) for co in corners])
    mesh = _to_mesh("Quad", bm)
    assert NORMALS not in _rules(geometry, "Quad", mesh)


def test_scn005_inside_out_cube_is_turned_outward(geometry: Any, meshes: Any) -> None:
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    mesh = _to_mesh("Cube", bm)
    findings = geometry.geometry_findings("Cube", mesh)
    assert [item["count"] for item in findings if item["rule"] == NORMALS] == [6]

    meshes.clean_mesh(mesh)

    assert len(mesh.polygons) == 6
    for polygon in mesh.polygons:
        assert polygon.normal.dot(Vector(polygon.center)) > 0, tuple(polygon.center)
    assert NORMALS not in _rules(geometry, "Cube", mesh)


def test_scn005_clean_crate_keeps_its_triangles(geometry: Any, meshes: Any) -> None:
    build_crate()
    mesh = bpy.data.objects["SM_Crate"].data
    before = meshes.triangle_count(mesh)

    meshes.clean_mesh(mesh)

    assert meshes.triangle_count(mesh) == before
    rules = _rules(geometry, "SM_Crate", mesh)
    assert [rule for rule in rules if rule.startswith("geometry.")] == []
