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

from .contract_fixtures import (  # noqa: E402
    DEFECTS,
    add_trim_material,
    apply_defect,
    build_crate,
    clear_scene,
    replace_mesh_with_grid,
)
from .texel_fixtures import (  # noqa: E402
    Strip,
    build_piece,
    slot_material,
    snapshot_texel,
    texel_findings,
)

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


def test_uv_overlap_defect_reports_the_lower_bound_form(core: Any) -> None:
    """#133 AC3 / T005: six faces that each cover the full square stop the overlap check early,
    so the finding says "at least" and still names the limit."""
    build_crate()
    apply_defect("uv_overlap")
    report = core.validate_asset("Crate", "standard_prop")

    (overlap,) = [item for item in report["findings"] if item["rule"] == "uv.overlap"]
    assert "at least" in overlap["message"]
    assert "0.5%" in overlap["message"]


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
# #134 / SCN001-SCN005: nmg-budgets.json Desktop overrides reach validate_asset
# ---------------------------------------------------------------------------

DESKTOP_TRIS_OVERRIDES: dict[str, Any] = {"hero_prop": {"tris": 40000, "desktop": {"tris": 300000}}}


def _overrides_file(tmp_path: Path, payload: dict[str, Any]) -> str:
    path = tmp_path / "nmg-budgets.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _findings(report: dict[str, Any], rule: str) -> list[dict[str, str]]:
    return [item for item in report["findings"] if item["rule"] == rule]


def _budget_tris_findings(report: dict[str, Any], variant: str) -> list[dict[str, str]]:
    """The budget.tris findings whose target object belongs to the given variant."""
    snapshot = report["snapshot"]
    return [
        item
        for item in _findings(report, "budget.tris")
        if snapshot[item["target"]]["variant"] == variant
    ]


@pytest.mark.parametrize("authored", [True, False], ids=["finalize_validate", "export_precheck"])
def test_scn001_desktop_tris_override_lets_a_larger_desktop_variant_pass(
    core: Any, tmp_path: Path, authored: bool
) -> None:
    build_crate()
    replace_mesh_with_grid("SM_Crate", 50_000)
    path = _overrides_file(tmp_path, DESKTOP_TRIS_OVERRIDES)

    report = core.validate_asset("Crate", "hero_prop", path, authored=authored)

    assert report["snapshot"]["SM_Crate"]["tris"] == 50_000
    assert _budget_tris_findings(report, "desktop") == []


def test_scn002_desktop_override_still_enforces_its_own_limit(core: Any, tmp_path: Path) -> None:
    build_crate()
    replace_mesh_with_grid("SM_Crate", 320_000)
    path = _overrides_file(tmp_path, DESKTOP_TRIS_OVERRIDES)

    report = core.validate_asset("Crate", "hero_prop", path)

    findings = _budget_tris_findings(report, "desktop")
    assert [item["target"] for item in findings] == ["SM_Crate"]
    assert "300000" in findings[0]["message"]


def test_scn003_desktop_texture_size_override_is_used_by_the_full_contract(
    core: Any, tmp_path: Path
) -> None:
    build_crate()
    path = _overrides_file(tmp_path, {"standard_prop": {"desktop": {"max_texture_px": 256}}})

    report = core.validate_asset("Crate", "standard_prop", path)

    findings = _findings(report, "budget.texture_size")
    assert [item["target"] for item in findings] == ["T_Crate_Body_BC"]
    assert "256" in findings[0]["message"]
    default = core.validate_asset("Crate", "standard_prop")
    assert _findings(default, "budget.texture_size") == []


def test_scn003_desktop_materials_override_is_used_by_the_full_contract(
    core: Any, tmp_path: Path
) -> None:
    build_crate()
    add_trim_material("SM_Crate")
    path = _overrides_file(tmp_path, {"standard_prop": {"desktop": {"materials": 1}}})

    report = core.validate_asset("Crate", "standard_prop", path)

    findings = _findings(report, "budget.materials")
    assert [item["target"] for item in findings] == ["SM_Crate"]
    assert "limit is 1" in findings[0]["message"]
    default = core.validate_asset("Crate", "standard_prop")
    assert _findings(default, "budget.materials") == []


def test_scn004_without_overrides_the_desktop_budget_is_the_contract_default(core: Any) -> None:
    build_crate()
    replace_mesh_with_grid("SM_Crate", 50_000)

    report = core.validate_asset("Crate", "hero_prop")

    findings = _budget_tris_findings(report, "desktop")
    assert [item["target"] for item in findings] == ["SM_Crate"]
    assert "40000" in findings[0]["message"]


def test_scn004_mobile_top_level_override_still_applies_to_mobile_only(
    core: Any, tmp_path: Path
) -> None:
    build_crate()
    apply_defect("mobile_lod0_4000_tris")
    path = _overrides_file(tmp_path, {"standard_prop": {"tris": 3000}})

    report = core.validate_asset("Crate", "standard_prop", path)

    findings = _budget_tris_findings(report, "mobile")
    assert [item["target"] for item in findings] == ["SM_Crate_Mobile_LOD0"]
    assert "3000" in findings[0]["message"]
    assert _budget_tris_findings(report, "desktop") == []


@pytest.mark.parametrize(
    "desktop_override",
    [{"polys": 10}, {"tris": 0}],
    ids=["unknown_metric", "non_positive_value"],
)
def test_scn005_invalid_desktop_override_raises_the_existing_error(
    core: Any, tmp_path: Path, desktop_override: dict[str, Any]
) -> None:
    build_crate()
    path = _overrides_file(tmp_path, {"standard_prop": {"desktop": desktop_override}})

    with pytest.raises(core.ContractError) as raised:
        core.validate_asset("Crate", "standard_prop", path)

    assert raised.value.code == "variants.budget_override_invalid"
    assert raised.value.message
    assert raised.value.remediation


# ---------------------------------------------------------------------------
# #151: texel density per material slot (SCN001-SCN007, SCN009)
# ---------------------------------------------------------------------------

_PIECE = "Piece"


def _validate_piece(core: Any, strips: list[Strip]) -> dict[str, Any]:
    build_piece(_PIECE, strips)
    return core.validate_asset(_PIECE, "environment_piece")


def _entry(report: dict[str, Any], material: str) -> dict[str, Any]:
    return next(item for item in snapshot_texel(report, "SM_Piece") if item["material"] == material)


def test_scn001_each_slot_is_measured_from_its_own_faces(core: Any) -> None:
    """SCN001 (AC1): each slot's density comes from its own faces and is compared on its own."""
    report = _validate_piece(
        core,
        [
            (slot_material("M_Piece_Full", 256), 1.2, 0.4),  # 307 px/m
            (slot_material("M_Piece_Half", 256), 0.5, 0.3),  # 128 px/m
            (slot_material("M_Piece_Mid", 256), 1.05, 0.3),  # 268.8 px/m
        ],
    )

    assert _entry(report, "M_Piece_Full")["desktop"] == pytest.approx(307.2, abs=0.05)
    assert _entry(report, "M_Piece_Half")["desktop"] == pytest.approx(128.0, abs=0.05)
    assert _entry(report, "M_Piece_Mid")["desktop"] == pytest.approx(268.8, abs=0.05)
    findings = texel_findings(report)
    assert [item["target"] for item in findings] == ["SM_Piece"]
    assert "M_Piece_Half" in findings[0]["message"]
    assert "M_Piece_Full" not in findings[0]["message"]


def test_scn002_dense_tiling_slot_passes_beside_atlas_and_flat_faces(core: Any) -> None:
    """SCN002 (AC2, FR12): the whole-mesh aggregate is below 256, but no finding is raised."""
    report = _validate_piece(
        core,
        [
            (slot_material("M_Piece_Tile", 256), 1.2, 0.1),
            (slot_material("M_Piece_Atlas", 256, trim=True), 0.1, 0.45),
            (slot_material("M_Piece_Paint", 256), None, 0.45),
        ],
    )

    # The aggregate the old whole-mesh check measured: sqrt(UV area / world area) at 256 px.
    aggregate = 256.0 * (1.2**2 * 0.1 + 0.1**2 * 0.45) ** 0.5
    assert aggregate < 256.0
    assert texel_findings(report) == []
    assert _entry(report, "M_Piece_Tile")["desktop"] == pytest.approx(307.2, abs=0.05)


def test_scn003_failing_slot_is_named_with_its_numbers(core: Any) -> None:
    """SCN003 (AC3): one finding names the mesh, the failing material, px/m, minimum, variant."""
    report = _validate_piece(
        core,
        [
            (slot_material("M_Piece_Good", 256), 1.2, 0.5),
            (slot_material("M_Piece_Low", 256), 0.5, 0.5),
        ],
    )

    findings = texel_findings(report)
    assert len(findings) == 1
    assert findings[0]["target"] == "SM_Piece"
    message = findings[0]["message"]
    for fragment in ("SM_Piece", "M_Piece_Low", "128 px/m", "at least 256 px/m", "on desktop"):
        assert fragment in message
    assert "M_Piece_Good" not in message


def test_scn004_collapsed_slot_is_flat_colour_without_any_marker(core: Any) -> None:
    """SCN004 (AC4, FR3): a slot whose UVs collapse to a point is exempt, with no marker set."""
    report = _validate_piece(
        core,
        [
            (slot_material("M_Piece_Tile", 256), 1.2, 0.5),
            (slot_material("M_Piece_Flat", 128), None, 0.5),
        ],
    )

    assert texel_findings(report) == []
    assert _entry(report, "M_Piece_Flat") == {
        "slot": 1,
        "material": "M_Piece_Flat",
        "exempt": "flat_colour",
    }


def test_scn005_marked_low_density_slot_is_exempt_as_trim_atlas(core: Any) -> None:
    """SCN005 (AC5): a declared trim atlas is exempt, however dense it measures."""
    report = _validate_piece(
        core,
        [
            (slot_material("M_Piece_Tile", 256), 1.2, 0.5),
            (slot_material("M_Piece_Atlas", 256, trim=True), 0.5, 0.5),  # 128 px/m, marked
        ],
    )

    assert texel_findings(report) == []
    assert _entry(report, "M_Piece_Atlas") == {
        "slot": 1,
        "material": "M_Piece_Atlas",
        "exempt": "trim_atlas",
    }


def test_scn006_undeclared_low_density_slot_fails_with_both_remedies(core: Any) -> None:
    """SCN006 (AC6): a surface mapped once across 0 to 1 fails; the remedy names both paths."""
    report = _validate_piece(core, [(slot_material("M_Piece_Wall", 128), 1.0, 1.0)])

    findings = texel_findings(report)
    assert len(findings) == 1
    remediation = findings[0]["remediation"]
    assert "Raise the slot" in remediation
    assert "nmg_trim_atlas" in remediation
    assert "trim atlas" in remediation


def test_scn007_snapshot_lists_every_slot_with_densities_or_reasons(core: Any) -> None:
    """SCN007 (AC7, FR7): every slot appears in the snapshot, measured or with its exemption."""
    report = _validate_piece(
        core,
        [
            (slot_material("M_Piece_Tile", 256), 1.2, 0.4),
            (slot_material("M_Piece_Atlas", 256, trim=True), 0.1, 0.3),
            (slot_material("M_Piece_Paint", 256), None, 0.3),
        ],
    )

    entries = snapshot_texel(report, "SM_Piece")
    assert [item["slot"] for item in entries] == [0, 1, 2]
    assert set(entries[0]) == {"slot", "material", "desktop"}
    assert entries[1] == {"slot": 1, "material": "M_Piece_Atlas", "exempt": "trim_atlas"}
    assert entries[2] == {"slot": 2, "material": "M_Piece_Paint", "exempt": "flat_colour"}


@pytest.mark.parametrize(
    ("span", "failing"),
    [(1.2, 0), (0.5, 1)],
    ids=["dense_passes", "sparse_fails"],
)
def test_scn009_single_undeclared_slot_keeps_its_code_and_reason(
    core: Any, span: float, failing: int
) -> None:
    """SCN009 (AC9, FR13): a single undeclared slot passes or fails as before, same code."""
    report = _validate_piece(core, [(slot_material("M_Piece_Only", 256), span, 1.0)])

    found = texel_findings(report)
    assert len(found) == failing
    assert _entry(report, "M_Piece_Only")["desktop"] == pytest.approx(256.0 * span, abs=0.05)
    if failing:
        assert found[0]["rule"] == "texel.density"
        assert "128 px/m" in found[0]["message"]
        assert "on desktop" in found[0]["message"]
