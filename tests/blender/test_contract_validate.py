"""Contract validation under Blender headless: AC1, AC2, AC7 (SCN001, SCN002, SCN007).

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from mathutils import Vector  # noqa: E402

from .contract_fixtures import DEFECTS, apply_defect, build_crate, clear_scene  # noqa: E402

DEFECT_RULES: dict[str, str] = {
    "root_rotation": "transform.root_applied",
    "origin_off_center": "pivot.bottom_center",
    "no_uv": "uv.single_map",
    "uv_overlap": "uv.overlap",
    "noise_material": "material.node_types",
    "position_coords": "material.uv_coordinates",
    "mobile_lod0_4000_tris": "budget.tris",
    "mobile_name_mismatch": "variants.names_match",
}


@pytest.fixture(autouse=True)
def _isolated_scene() -> Iterator[None]:
    yield
    clear_scene()


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core")


def _scene_state() -> dict[str, Any]:
    return {
        "objects": sorted(
            (
                obj.name,
                obj.type,
                tuple(obj.location),
                tuple(obj.rotation_euler),
                tuple(obj.scale),
                obj.data.name if obj.data is not None else None,
            )
            for obj in bpy.data.objects
        ),
        "collections": sorted(collection.name for collection in bpy.data.collections),
        "meshes": len(bpy.data.meshes),
        "materials": len(bpy.data.materials),
        "images": len(bpy.data.images),
    }


def test_defect_list_matches_the_rule_table() -> None:
    assert set(DEFECTS) == set(DEFECT_RULES)


# ---------------------------------------------------------------------------
# AC1 / SCN001: every checkable rule passes on a compliant asset
# ---------------------------------------------------------------------------


def test_ac1_compliant_crate_passes_with_snapshots(core: Any) -> None:
    build_crate()
    report = core.validate_asset("Crate", "standard_prop")

    assert report["kind"] == "contract"
    assert report["passed"], report["findings"]
    assert report["findings"] == []
    assert {"SM_Crate", "SM_Crate_Mobile", "SM_Crate_Mobile_LOD0"} <= set(report["snapshot"])
    root = report["snapshot"]["SM_Crate"]
    assert root["uv_maps"] == ["UVMap"]
    assert root["variant"] == "desktop"
    assert root["tris"] == 12
    assert report["snapshot"]["SM_Crate_Mobile_LOD0"]["variant"] == "mobile"


def test_ac1_findings_carry_rule_target_message_and_remediation(core: Any) -> None:
    build_crate()
    apply_defect("root_rotation")
    report = core.validate_asset("Crate", "standard_prop")

    assert report["findings"]
    for item in report["findings"]:
        assert set(item) == {"rule", "target", "message", "remediation"}
        assert item["target"] and item["message"] and item["remediation"]


# ---------------------------------------------------------------------------
# AC2 / SCN002: each failure class fails with its rule id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("defect", list(DEFECT_RULES))
def test_ac2_each_failure_class_fails_with_its_rule(core: Any, defect: str) -> None:
    build_crate()
    apply_defect(defect)
    report = core.validate_asset("Crate", "standard_prop")

    assert not report["passed"]
    rule = DEFECT_RULES[defect]
    matches = [item for item in report["findings"] if item["rule"] == rule]
    assert matches, f"{defect}: expected {rule}, got {[i['rule'] for i in report['findings']]}"
    assert all(item["target"] and item["remediation"] for item in matches)


def test_ac2_budget_finding_names_the_mobile_lod0(core: Any) -> None:
    build_crate()
    apply_defect("mobile_lod0_4000_tris")
    report = core.validate_asset("Crate", "standard_prop")

    budget = [item for item in report["findings"] if item["rule"] == "budget.tris"]
    assert budget[0]["target"] == "SM_Crate_Mobile_LOD0"
    assert "4000" in budget[0]["message"]


# ---------------------------------------------------------------------------
# Scene unchanged: checks run on copies only
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("defect", [None, "uv_overlap", "mobile_lod0_4000_tris"])
def test_validation_leaves_the_scene_unchanged(core: Any, defect: str | None) -> None:
    build_crate()
    if defect is not None:
        apply_defect(defect)
    before = _scene_state()
    core.validate_asset("Crate", "standard_prop")
    assert _scene_state() == before


# ---------------------------------------------------------------------------
# AC7 / SCN007: the operator and a direct call write the same report
# ---------------------------------------------------------------------------


def test_ac7_operator_and_direct_call_write_identical_reports(core: Any, tmp_path: Path) -> None:
    build_crate()
    report_path = tmp_path / "report.json"

    result = bpy.ops.nmggamedev.validate_contract(
        collection_name="Crate",
        asset_class="standard_prop",
        report_path=str(report_path),
    )

    direct = core.validate_asset("Crate", "standard_prop")
    assert result == {"FINISHED"}
    assert json.loads(report_path.read_text(encoding="utf-8")) == direct
    assert json.loads(bpy.context.scene.nmg_game_dev.last_result) == direct


def test_ac7_operator_reports_a_failing_report_as_an_error(
    enabled_addon: str, tmp_path: Path
) -> None:
    """Blender raises RuntimeError for an ERROR report run from Python, so a failure is seen here
    as that exception. The operator still stores and writes the failing report first."""
    build_crate()
    apply_defect("no_uv")
    report_path = tmp_path / "report.json"

    with pytest.raises(RuntimeError, match="uv.single_map"):
        bpy.ops.nmggamedev.validate_contract(
            collection_name="Crate",
            asset_class="standard_prop",
            report_path=str(report_path),
        )

    stored = json.loads(bpy.context.scene.nmg_game_dev.last_result)
    assert stored["passed"] is False
    assert any(item["rule"] == "uv.single_map" for item in stored["findings"])
    assert json.loads(report_path.read_text(encoding="utf-8")) == stored


# ---------------------------------------------------------------------------
# #153: geometry findings carry located samples (SCN001-SCN005, SCN007)
# ---------------------------------------------------------------------------

_BOX_FACES: tuple[tuple[int, ...], ...] = (
    (0, 1, 3, 2),
    (4, 6, 7, 5),
    (0, 4, 5, 1),
    (2, 3, 7, 6),
    (0, 2, 6, 4),
    (1, 5, 7, 3),
)


def _box(
    lo: tuple[float, float, float], hi: tuple[float, float, float]
) -> list[tuple[float, float, float]]:
    """The eight corners of an axis-aligned box, in the order _BOX_FACES indexes them."""
    return [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]


def _collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def _mesh_object(
    collection: bpy.types.Collection,
    name: str,
    verts: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    groups: dict[str, list[int]] | None = None,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    for group_name, indices in (groups or {}).items():
        obj.vertex_groups.new(name=group_name).add(indices, 1.0, "REPLACE")
    return obj


def _transform(obj: bpy.types.Object) -> None:
    """Translate, rotate, and scale obj, so its samples must be mapped into world space."""
    obj.location = (2.0, 3.0, 4.0)
    obj.rotation_euler = (0.0, 0.0, 0.3)
    obj.scale = (1.5, 1.2, 1.0)
    bpy.context.view_layer.update()


def _geometry(report: dict[str, Any], target: str) -> dict[str, dict[str, Any]]:
    """The geometry findings one object carries, keyed by rule."""
    return {
        item["rule"]: item
        for item in report["findings"]
        if item["rule"].startswith("geometry.") and item["target"] == target
    }


def _joined_boxes() -> bpy.types.Object:
    """Two closed unit boxes joined into one mesh that share one corner position.

    Lower spans [0, 1]^3 (indices 0-7) and Upper spans [1, 2]^3 (indices 8-15), so the corner
    (1, 1, 1) appears twice: index 7 in Lower and index 8 in Upper.
    """
    clear_scene()
    faces = list(_BOX_FACES) + [tuple(i + 8 for i in face) for face in _BOX_FACES]
    verts = _box((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)) + _box((1.0, 1.0, 1.0), (2.0, 2.0, 2.0))
    obj = _mesh_object(
        _collection("Joined"),
        "SM_Joined",
        verts,
        faces,
        {"Lower": list(range(8)), "Upper": list(range(8, 16))},
    )
    _transform(obj)
    return obj


# ---------------------------------------------------------------------------
# SCN001: a duplicate-vertex sample gives the world position, both indices, and both groups
# ---------------------------------------------------------------------------


def test_scn001_duplicate_samples_locate_the_shared_vertex(core: Any) -> None:
    obj = _joined_boxes()
    report = core.validate_asset("Joined", "standard_prop")

    duplicates = _geometry(report, "SM_Joined")["geometry.duplicates"]
    assert duplicates["count"] == 1
    assert len(duplicates["samples"]) == 1
    sample = duplicates["samples"][0]
    assert sample["index"] == 8
    assert sample["coincides_with"] == 7
    expected = obj.matrix_world @ Vector((1.0, 1.0, 1.0))
    assert sample["position"] == pytest.approx(list(expected), abs=1e-5)
    assert sample["vertex_groups"] == ["Lower", "Upper"]
    x, y, z = sample["position"]
    assert duplicates["message"].endswith(f"first at ({x:.4f}, {y:.4f}, {z:.4f}).")


# ---------------------------------------------------------------------------
# SCN002: zero-area and inward-flipped faces give face-center samples
# ---------------------------------------------------------------------------


def test_scn002_face_samples_locate_zero_area_and_flipped_faces(core: Any) -> None:
    clear_scene()
    collection = _collection("Faces")
    # A zero-area sliver: a triangle over three collinear vertices (8-10), as face 6.
    sliver_verts = _box((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)) + [
        (2.0, 0.0, 0.0),
        (2.5, 0.0, 0.0),
        (3.0, 0.0, 0.0),
    ]
    sliver = _mesh_object(
        collection,
        "SM_Faces_Sliver",
        sliver_verts,
        list(_BOX_FACES) + [(8, 9, 10)],
        {"Box": list(range(8)), "Sliver": [8, 9, 10]},
    )
    _transform(sliver)
    # A closed box whose x-min face (index 0) is wound inward.
    flipped_faces = [tuple(reversed(_BOX_FACES[0]))] + list(_BOX_FACES[1:])
    flipped = _mesh_object(
        collection,
        "SM_Faces_Flipped",
        _box((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
        flipped_faces,
        {"Box": list(range(8))},
    )
    _transform(flipped)
    report = core.validate_asset("Faces", "standard_prop")

    zero_area = _geometry(report, "SM_Faces_Sliver")["geometry.zero_area"]
    assert zero_area["count"] == 1
    sliver_sample = zero_area["samples"][0]
    assert sliver_sample["index"] == 6
    expected_center = sliver.matrix_world @ Vector((2.5, 0.0, 0.0))
    assert sliver_sample["position"] == pytest.approx(list(expected_center), abs=1e-5)
    assert sliver_sample["vertex_groups"] == ["Sliver"]

    normals = _geometry(report, "SM_Faces_Flipped")["geometry.normals"]
    assert normals["count"] == 1
    flipped_sample = normals["samples"][0]
    assert flipped_sample["index"] == 0
    expected_center = flipped.matrix_world @ Vector((0.0, 0.5, 0.5))
    assert flipped_sample["position"] == pytest.approx(list(expected_center), abs=1e-5)
    assert flipped_sample["vertex_groups"] == ["Box"]


# ---------------------------------------------------------------------------
# SCN003: a loose-vertex finding locates each loose vertex
# ---------------------------------------------------------------------------


def test_scn003_loose_samples_locate_the_vertices(core: Any) -> None:
    clear_scene()
    stray_points = [(3.0, 0.0, 0.0), (0.0, 4.0, 0.0)]
    stray = _mesh_object(
        _collection("Loose"),
        "SM_Loose",
        _box((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)) + stray_points,
        list(_BOX_FACES),
        {"Box": list(range(8)), "Stray": [8, 9]},
    )
    _transform(stray)
    report = core.validate_asset("Loose", "standard_prop")

    loose = _geometry(report, "SM_Loose")["geometry.loose"]
    assert loose["count"] == 2
    assert [sample["index"] for sample in loose["samples"]] == [8, 9]
    for sample, point in zip(loose["samples"], stray_points, strict=True):
        assert sample["position"] == pytest.approx(
            list(stray.matrix_world @ Vector(point)), abs=1e-5
        )
        assert sample["vertex_groups"] == ["Stray"]


# ---------------------------------------------------------------------------
# SCN004: more than five offending elements give the full count and the first five indices
# ---------------------------------------------------------------------------


def test_scn004_samples_are_capped_at_the_five_lowest_indices(core: Any) -> None:
    clear_scene()
    extra = [(2.0 + offset, 0.0, 0.0) for offset in range(7)]
    _mesh_object(
        _collection("Capped"),
        "SM_Capped",
        _box((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)) + extra,
        list(_BOX_FACES),
        {"Box": list(range(8))},
    )

    first = core.validate_asset("Capped", "standard_prop")
    second = core.validate_asset("Capped", "standard_prop")

    loose = _geometry(first, "SM_Capped")["geometry.loose"]
    assert loose["count"] == 7
    assert [sample["index"] for sample in loose["samples"]] == [8, 9, 10, 11, 12]
    assert _geometry(second, "SM_Capped")["geometry.loose"]["samples"] == loose["samples"]


# ---------------------------------------------------------------------------
# SCN005: elements outside any vertex group have empty group lists
# ---------------------------------------------------------------------------


def test_scn005_samples_without_vertex_groups_have_empty_group_lists(core: Any) -> None:
    clear_scene()
    _mesh_object(
        _collection("Ungrouped"),
        "SM_Ungrouped",
        _box((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)) + [(3.0, 0.0, 0.0)],
        list(_BOX_FACES),
    )
    report = core.validate_asset("Ungrouped", "standard_prop")

    loose = _geometry(report, "SM_Ungrouped")["geometry.loose"]
    assert loose["count"] == 1
    assert loose["samples"][0]["vertex_groups"] == []
    assert set(loose) == {"rule", "target", "message", "remediation", "count", "samples"}
    assert loose["target"] == "SM_Ungrouped"
    assert loose["message"]
    assert loose["remediation"]


# ---------------------------------------------------------------------------
# SCN007: a clean mesh emits no geometry findings, and pass/fail is unchanged
# ---------------------------------------------------------------------------


def test_scn007_clean_mesh_emits_no_geometry_findings(core: Any) -> None:
    build_crate()
    report = core.validate_asset("Crate", "standard_prop")

    assert report["passed"] is True
    assert [item for item in report["findings"] if item["rule"].startswith("geometry.")] == []
