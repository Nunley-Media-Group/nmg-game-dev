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
