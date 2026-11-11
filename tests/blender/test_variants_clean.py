"""Variants clean and Mobile re-seat under Blender headless: AC1-AC7 of #140 (SCN001-SCN007).

Each scenario builds the defect that the Desktop cleanup or the variants step must handle, then
checks the result with the contract validator, the same rules the export gate applies. AC6 and
AC7 guard behavior that must not change, so they pass on the pre-fix code as well.

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

import bmesh  # noqa: E402
from mathutils import Vector  # noqa: E402

from .contract_fixtures import build_crate as build_contract_crate  # noqa: E402
from .contract_fixtures import clear_scene  # noqa: E402
from .rig_fixtures import add_baked_hero_material, build_hero, reset_scene  # noqa: E402

_CATEGORY = "Props"
#: 6 faces x 32 x 32 cells x 2 triangles: the grid-filled cube from _dense_crate.
DENSE_TRIS = 12 * 32 * 32
#: The standard_prop Mobile triangle budget.
STANDARD_TRIS = 3000
#: Mobile budget for the pivot scenario, tight enough that decimation removes the sphere's pole.
TIGHT_TRIS = 200
#: Tip of the sliver face, 1e-3 off the top-front edge of the unit cube. The edge then has three
#: faces, and the sliver decimated into a Mobile LOD fails geometry.normals before the fix.
SLIVER_TIP = (0.0, -0.5 - 1e-3, 1.0 + 1e-3)
#: Vertices of the two coincident triangles that share one vertex set.
PAIR = ((0.1, -0.2, 0.5), (0.2, -0.2, 0.5), (0.15, 0.1, 0.6))
PIVOT_TOLERANCE = 1e-3
_DEGENERATE_RULES = ("geometry.zero_area", "geometry.loose")


@pytest.fixture(autouse=True)
def _isolated_scene() -> Iterator[None]:
    yield
    clear_scene()


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.variants_core")


@pytest.fixture()
def contract(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core")


@pytest.fixture()
def rigged_hero(enabled_addon: str) -> Iterator[None]:
    """Collection Hero: SM_Hero skinned to SK_Hero, with a baked surface."""
    reset_scene()
    rig_core = importlib.import_module(f"{enabled_addon}.rig_core")
    assert rig_core.rig_humanoid("Hero", "humanoid", build_hero())["status"] == "ok"
    add_baked_hero_material()
    yield
    reset_scene()


@pytest.fixture()
def decimation_leaks_zero_area(enabled_addon: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every decimated candidate carry a zero-area face.

    Collapse decimation does not reliably produce one on these meshes, so the fixture adds the
    defect to decimated_copy's output. The fit must clean it out before it compares the triangle
    total with the target, so the test passes only when fit_meshes runs clean_mesh.
    """
    meshes = importlib.import_module(f"{enabled_addon}.variants_core.meshes")
    decimate = meshes.decimated_copy

    def leaking(source: bpy.types.Mesh, ratio: float) -> bpy.types.Mesh:
        result = decimate(source, ratio)
        _append_zero_area_face(result)
        return result

    monkeypatch.setattr(meshes, "decimated_copy", leaking)


# ---------------------------------------------------------------------------
# Scene builders
# ---------------------------------------------------------------------------


def _new_asset(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def _pydata_asset(name: str, verts: list[tuple[float, ...]], faces: list[tuple[int, ...]]) -> None:
    mesh = bpy.data.meshes.new(f"SM_{name}")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    _new_asset(name).objects.link(bpy.data.objects.new(f"SM_{name}", mesh))


def _unit_cube() -> tuple[list[tuple[float, ...]], list[tuple[int, ...]]]:
    """Unit cube on z = 0 to 1, centred on the origin in x and y, so it meets the pivot contract."""
    verts: list[tuple[float, ...]] = [
        (-0.5, -0.5, 0.0),
        (0.5, -0.5, 0.0),
        (0.5, 0.5, 0.0),
        (-0.5, 0.5, 0.0),
        (-0.5, -0.5, 1.0),
        (0.5, -0.5, 1.0),
        (0.5, 0.5, 1.0),
        (-0.5, 0.5, 1.0),
    ]
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return verts, faces


def _fin_asset(name: str, *, duplicates: bool) -> None:
    """Unit cube with a sliver on the top-front edge, which then has three faces.

    With duplicates, a second triangle shares the first one's vertex set with the opposite
    winding, so the mesh holds two faces that repeat one vertex set.
    """
    verts, faces = _unit_cube()
    apex = len(verts)
    verts.append(SLIVER_TIP)
    faces.append((4, 5, apex))
    if duplicates:
        base = len(verts)
        verts.extend(PAIR)
        faces.append((base, base + 1, base + 2))
        faces.append((base, base + 2, base + 1))
    _pydata_asset(name, verts, faces)


def _dense_crate(name: str) -> bpy.types.Collection:
    """Grid-filled unit cube resting on z = 0 with 12,288 triangles, above the standard budget."""
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=31, use_grid_fill=True)
        bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0.0, 0.0, 0.5))
        mesh = bpy.data.meshes.new(f"SM_{name}")
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()
    collection = _new_asset(name)
    collection.objects.link(bpy.data.objects.new(f"SM_{name}", mesh))
    return collection


def _uv_sphere(name: str) -> None:
    """UV sphere of radius 0.5 resting on z = 0, so its south pole is the lowest vertex."""
    bm = bmesh.new()
    try:
        bmesh.ops.create_uvsphere(bm, u_segments=128, v_segments=64, radius=0.5)
        bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0.0, 0.0, 0.5))
        mesh = bpy.data.meshes.new(f"SM_{name}")
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()
    _new_asset(name).objects.link(bpy.data.objects.new(f"SM_{name}", mesh))


def _add_trim_part(collection: bpy.types.Collection) -> None:
    """A small child part SM_Crate_Trim beside the crate root, parented to it."""
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=0.2)
        bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0.6, 0.0, 0.1))
        mesh = bpy.data.meshes.new("SM_Crate_Trim")
        bm.to_mesh(mesh)
    finally:
        bm.free()
    part = bpy.data.objects.new("SM_Crate_Trim", mesh)
    collection.objects.link(part)
    part.parent = bpy.data.objects["SM_Crate"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _budget(tris: int) -> dict[str, int]:
    return {"tris": tris, "max_texture_px": 1024, "materials": 1}


def _triangles(mesh: bpy.types.Mesh) -> int:
    return sum(max(len(polygon.vertices) - 2, 0) for polygon in mesh.polygons)


def _rounded(co: Any) -> tuple[float, ...]:
    return tuple(round(component, 6) for component in co)


def _polygon_corners(mesh: bpy.types.Mesh, polygon: Any) -> frozenset[tuple[float, ...]]:
    return frozenset(_rounded(mesh.vertices[index].co) for index in polygon.vertices)


def _append_zero_area_face(mesh: bpy.types.Mesh) -> None:
    """Add a triangle whose three vertices are collinear, far from the body, so its area is zero."""
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        a = bm.verts.new((3.0, 0.0, 0.0))
        b = bm.verts.new((3.1, 0.0, 0.0))
        c = bm.verts.new((3.2, 0.0, 0.0))
        bm.faces.new((a, b, c))
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()


def _findings(contract: Any) -> list[tuple[str, str, str]]:
    report = contract.validate_asset("Crate", "standard_prop", authored=True)
    return [(item["rule"], item["target"], item["message"]) for item in report["findings"]]


# ---------------------------------------------------------------------------
# AC1 / SCN001: decimated Mobile LODs have no zero-area or loose geometry
# ---------------------------------------------------------------------------


def test_scn001_decimated_lods_have_no_zero_area_or_loose_geometry(
    rigged_hero: None,
    decimation_leaks_zero_area: None,
    core: Any,
    contract: Any,
    enabled_addon: str,
) -> None:
    budget = importlib.import_module(f"{enabled_addon}.utils.budgets").resolve_budget(
        "character", None
    )
    cleaned = core.cleanup_desktop("Hero")
    assert cleaned["tris_after"] > budget["tris"], "the Desktop mesh must exceed the Mobile budget"

    core.optimize_mobile("Hero", "character")

    report = contract.validate_asset("Hero", "character", authored=True)
    flagged = [
        item
        for item in report["findings"]
        if item["rule"] in _DEGENERATE_RULES and item["target"].startswith("SM_Hero_Mobile")
    ]
    assert flagged == [], flagged


# ---------------------------------------------------------------------------
# AC2 / SCN002: the non-manifold sliver does not destabilise normals
# ---------------------------------------------------------------------------


def test_scn002_normals_are_stable_on_desktop_and_every_mobile_lod(
    core: Any, contract: Any
) -> None:
    _fin_asset("Crate", duplicates=False)
    core.cleanup_desktop("Crate")
    core.optimize_mobile("Crate", "standard_prop")

    first = _findings(contract)
    normals = [finding for finding in first if finding[0] == "geometry.normals"]
    assert normals == [], normals
    assert _findings(contract) == first, "repeating the validation must give the same result"


# ---------------------------------------------------------------------------
# AC3 / SCN003: the Mobile root is re-seated after decimation
# ---------------------------------------------------------------------------


def test_scn003_mobile_root_is_reseated_after_decimation(core: Any, contract: Any) -> None:
    _uv_sphere("Ball")
    core.cleanup_desktop("Ball")
    core.build_mobile("Ball", _budget(TIGHT_TRIS))

    root = bpy.data.objects["SM_Ball_Mobile"]
    lod0 = bpy.data.objects["SM_Ball_Mobile_LOD0"]
    origin = root.matrix_world.translation
    world = [lod0.matrix_world @ vert.co for vert in lod0.data.vertices]
    xs = [point.x for point in world]
    ys = [point.y for point in world]
    bottom_centre = (
        (min(xs) + max(xs)) / 2,
        (min(ys) + max(ys)) / 2,
        min(point.z for point in world),
    )
    for value in (*origin, *bottom_centre):
        assert abs(value) <= PIVOT_TOLERANCE, (tuple(origin), bottom_centre)

    report = contract.validate_asset("Ball", "standard_prop", authored=True)
    pivots = [item for item in report["findings"] if item["rule"] == "pivot.bottom_center"]
    assert pivots == [], pivots


# ---------------------------------------------------------------------------
# AC4 / SCN004: Desktop cleanup removes non-manifold and duplicate faces
# ---------------------------------------------------------------------------


def test_scn004_cleanup_removes_non_manifold_and_duplicate_faces(core: Any) -> None:
    _fin_asset("Crate", duplicates=True)
    report = core.cleanup_desktop("Crate")

    # 12 cube triangles, the sliver, and the two coincident triangles.
    assert report["tris_before"] == 12 + 1 + 2
    assert report["tris_after"] == 12 + 1, "the sliver and one of the coincident pair must go"

    mesh = bpy.data.objects["SM_Crate"].data
    assert _triangles(mesh) == report["tris_after"]
    pair = frozenset(_rounded(co) for co in PAIR)
    sharing = [polygon for polygon in mesh.polygons if _polygon_corners(mesh, polygon) == pair]
    assert len(sharing) == 1, "one face must remain for the shared vertex set"
    assert not any(_rounded(vert.co) == _rounded(SLIVER_TIP) for vert in mesh.vertices)


# ---------------------------------------------------------------------------
# AC5 / SCN005: re-import triangle counts match for Desktop and Mobile
# ---------------------------------------------------------------------------


def test_scn005_reimport_triangle_counts_match(core: Any, contract: Any, tmp_path: Path) -> None:
    _fin_asset("Crate", duplicates=True)
    core.cleanup_desktop("Crate")
    core.optimize_mobile("Crate", "standard_prop")
    pre_report = contract.validate_asset("Crate", "standard_prop")
    core.export_variants("Crate", _CATEGORY, str(tmp_path))

    variant_root = tmp_path / _CATEGORY / "Crate"
    for variant in ("Desktop", "Mobile"):
        report = contract.run_isolated(variant_root / variant, pre_report)
        mismatches = [item for item in report["findings"] if item["rule"] == "reimport.tris"]
        assert mismatches == [], (variant, mismatches)


# ---------------------------------------------------------------------------
# AC6 / SCN006: budgets, skinning and layout are preserved (guard)
# ---------------------------------------------------------------------------


def test_scn006_rigged_chain_keeps_budget_skin_and_layout(rigged_hero: None, core: Any) -> None:
    core.cleanup_desktop("Hero")
    result = core.optimize_mobile("Hero", "character")

    assert result["rigged"] is True
    assert result["lod_levels"] == 3
    names = ("SM_Hero_Mobile", "SM_Hero_Mobile_LOD1", "SM_Hero_Mobile_LOD2")
    lods = [bpy.data.objects[name] for name in names]
    counts = [_triangles(obj.data) for obj in lods]
    assert result["lod_tris"] == counts
    assert counts[0] <= result["budget"]["tris"]
    assert counts[1] <= 0.5 * counts[0]
    assert counts[2] <= 0.25 * counts[0]
    for obj in lods:
        assert obj.parent is not None and obj.parent.name == "SK_Hero"
        skins = [m for m in obj.modifiers if m.type == "ARMATURE" and m.object is not None]
        assert len(skins) == 1 and skins[0].object.name == "SK_Hero"
        assert len(obj.vertex_groups) > 0


def test_scn006_unrigged_lod_group_keeps_its_layout(core: Any) -> None:
    _dense_crate("Crate")
    core.cleanup_desktop("Crate")
    result = core.optimize_mobile("Crate", "standard_prop")

    group = bpy.data.objects["SM_Crate_Mobile"]
    assert group.type == "EMPTY" and group["fbx_type"] == "LodGroup"
    lods = [bpy.data.objects[f"SM_Crate_Mobile_LOD{level}"] for level in range(3)]
    for lod in lods:
        assert lod.parent is not None and lod.parent.name == group.name
    counts = [_triangles(obj.data) for obj in lods]
    assert result["rigged"] is False
    assert result["lod_tris"] == counts
    assert counts[0] <= STANDARD_TRIS
    assert counts[1] <= 0.5 * counts[0]
    assert counts[2] <= 0.25 * counts[0]


def test_scn006_multi_part_asset_keeps_lod0_only(core: Any) -> None:
    _add_trim_part(_dense_crate("Crate"))
    core.cleanup_desktop("Crate")
    result = core.optimize_mobile("Crate", "standard_prop")

    parts = [bpy.data.objects["SM_Crate_Mobile"], bpy.data.objects["SM_Crate_Trim_Mobile"]]
    total = sum(_triangles(obj.data) for obj in parts)
    assert result["lod_levels"] == 1
    assert result["lod_tris"] == [total]
    assert total <= STANDARD_TRIS
    assert bpy.data.objects["SM_Crate_Trim_Mobile"].parent.name == "SM_Crate_Mobile"


# ---------------------------------------------------------------------------
# AC7 / SCN007: clean meshes are unchanged (guard)
# ---------------------------------------------------------------------------


def test_scn007_clean_asset_keeps_triangles_and_is_deterministic(
    build_crate: Any, core: Any
) -> None:
    def run() -> tuple[list[int], list[list[tuple[float, ...]]]]:
        build_crate()
        cleaned = core.cleanup_desktop("Crate")
        assert cleaned["tris_after"] == DENSE_TRIS
        result = core.optimize_mobile("Crate", "standard_prop")
        positions = [
            sorted(
                _rounded(vert.co)
                for vert in bpy.data.objects[f"SM_Crate_Mobile_LOD{level}"].data.vertices
            )
            for level in range(3)
        ]
        return result["lod_tris"], positions

    first = run()
    second = run()
    assert first == second, "identical input must give identical triangle counts and vertices"

    lod0, lod1, lod2 = first[0]
    assert lod0 <= STANDARD_TRIS
    assert lod1 <= 0.5 * lod0
    assert lod2 <= 0.25 * lod0
    assert bpy.data.objects["SM_Crate_Mobile"].matrix_world.translation == Vector((0.0, 0.0, 0.0))


def test_scn007_mobile_already_on_origin_is_not_translated(core: Any) -> None:
    build_contract_crate()
    core.cleanup_desktop("Crate")
    desktop = sorted(_rounded(vert.co) for vert in bpy.data.objects["SM_Crate"].data.vertices)

    core.optimize_mobile("Crate", "standard_prop")

    lod0 = bpy.data.objects["SM_Crate_Mobile_LOD0"]
    mobile = sorted(_rounded(vert.co) for vert in lod0.data.vertices)
    assert mobile == desktop
