"""Spatial inspection under Blender headless: AC3-AC6 (SCN003-SCN006).

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .inspect_fixtures import build_clean, build_probe  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "model-asset" / "SKILL.md"


def _one(report: dict[str, Any], rule: str) -> dict[str, Any]:
    matches = [finding for finding in report["findings"] if finding["rule"] == rule]
    assert len(matches) == 1, f"expected one {rule} finding, got {matches}"
    return matches[0]


def _snapshot() -> dict[str, Any]:
    return {
        "objects": sorted(
            (obj.name, tuple(obj.location), tuple(obj.rotation_euler), tuple(obj.scale))
            for obj in bpy.data.objects
        ),
        "counts": {
            name: len(getattr(bpy.data, name))
            for name in ("objects", "meshes", "materials", "collections", "node_groups", "images")
        },
    }


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.inspect_core")


@pytest.fixture()
def contract_error(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core.report").ContractError


# ---------------------------------------------------------------------------
# AC3: a defective collection reports every spatial finding
# ---------------------------------------------------------------------------


def test_defective_collection_reports_every_spatial_finding(core: Any) -> None:
    """SCN003: floating, interpenetration, non_manifold, and over_budget, with their fields."""
    build_probe()
    report = core.inspect_asset("Probe", "small_prop")
    json.dumps(report)

    assert report["kind"] == "inspect"
    assert report["passed"] is False

    floating = _one(report, "floating")
    assert floating["blocking"] is True
    assert floating["parts"] == ["SM_Probe_Floating"]
    assert floating["gap"] == pytest.approx(0.05, abs=1e-6)

    interpenetration = _one(report, "interpenetration")
    assert interpenetration["blocking"] is False
    assert interpenetration["parts"] == ["SM_Probe_Pair_A", "SM_Probe_Pair_B"]

    non_manifold = _one(report, "non_manifold")
    assert non_manifold["blocking"] is True
    assert non_manifold["parts"] == ["SM_Probe_Open"]
    assert non_manifold["edges"] == 4

    over_budget = _one(report, "over_budget")
    assert over_budget["blocking"] is True
    assert over_budget["budget"] == 2000
    assert over_budget["triangles"] == report["triangles"]["total"]
    assert over_budget["triangles"] > 2000

    assert report["triangles"]["headroom"] == 2000 - report["triangles"]["total"]
    for part in report["parts"]:
        assert set(part["bounds"]) == {"min", "max"}
        assert isinstance(part["geometry"], list)


def test_defective_collection_has_no_finding_on_the_body(core: Any) -> None:
    """SCN003: the body and the open box that touches it are not floating."""
    build_probe()
    report = core.inspect_asset("Probe", "small_prop")
    floating_parts = [
        part
        for finding in report["findings"]
        if finding["rule"] == "floating"
        for part in finding["parts"]
    ]
    assert "SM_Probe_Body" not in floating_parts
    assert "SM_Probe_Open" not in floating_parts


# ---------------------------------------------------------------------------
# AC4: a clean asset passes, with headroom
# ---------------------------------------------------------------------------


def test_clean_collection_passes_with_headroom(core: Any) -> None:
    """SCN004: no blocking finding, positive headroom, and the array copy counts as connected."""
    build_clean()
    report = core.inspect_asset("Clean", "small_prop")

    assert report["passed"] is True
    assert [finding for finding in report["findings"] if finding["blocking"]] == []
    assert report["triangles"]["headroom"] > 0

    rail = next(part for part in report["parts"] if part["name"] == "SM_Clean_Rail")
    assert rail["bounds"]["min"][0] == pytest.approx(0.25, abs=1e-5)


def test_flush_contact_is_not_interpenetration(core: Any) -> None:
    """SCN004: a cap that only touches the body's top face is not reported as interpenetrating."""
    build_clean()
    report = core.inspect_asset("Clean", "small_prop")
    pairs = [
        finding["parts"] for finding in report["findings"] if finding["rule"] == "interpenetration"
    ]
    assert ["SM_Clean_Body", "SM_Clean_Top"] not in pairs
    assert ["SM_Clean_Overlap", "SM_Clean_Top"] in pairs


def test_budget_override_changes_the_budget_and_headroom(core: Any, tmp_path: Path) -> None:
    """AC3/FR3: nmg-budgets.json overrides the Desktop tris used for over_budget and headroom."""
    build_probe()
    overrides = tmp_path / "nmg-budgets.json"
    overrides.write_text(json.dumps({"small_prop": {"desktop": {"tris": 5000}}}), encoding="utf-8")
    report = core.inspect_asset("Probe", "small_prop", str(overrides))
    assert report["triangles"]["budget"] == 5000
    assert report["triangles"]["headroom"] == 5000 - report["triangles"]["total"]
    assert all(finding["rule"] != "over_budget" for finding in report["findings"])


# ---------------------------------------------------------------------------
# AC5: bad inputs fail with structured errors and change nothing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("collection", "asset_class", "code"),
    [
        ("Missing", "standard_prop", "inspect.collection_missing"),
        ("Probe", "spaceship", "inspect.unknown_asset_class"),
    ],
)
def test_bad_inputs_raise_structured_errors_and_change_nothing(
    core: Any, contract_error: Any, collection: str, asset_class: str, code: str
) -> None:
    """SCN005: each failure carries code, message, and remediation, and the scene is untouched."""
    build_probe()
    before = _snapshot()
    with pytest.raises(contract_error) as info:
        core.inspect_asset(collection, asset_class)
    assert info.value.code == code
    assert info.value.message
    assert info.value.remediation
    assert _snapshot() == before


def test_collection_without_mesh_parts_returns_an_empty_report(core: Any) -> None:
    """AC5: a collection with no mesh parts returns an empty report instead of crashing."""
    build_probe()
    empty = bpy.data.collections.new("Empty")
    bpy.context.scene.collection.children.link(empty)
    before = _snapshot()
    report = core.inspect_asset("Empty", "small_prop")
    assert report["parts"] == []
    assert report["findings"] == []
    assert report["triangles"]["total"] == 0
    json.dumps(report)
    assert _snapshot() == before


def test_invalid_budget_file_raises_the_budget_code(
    core: Any, contract_error: Any, tmp_path: Path
) -> None:
    """AC5: a malformed nmg-budgets.json raises as a ContractError with its own code."""
    build_probe()
    broken = tmp_path / "nmg-budgets.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(contract_error) as info:
        core.inspect_asset("Probe", "small_prop", str(broken))
    assert info.value.code == "variants.budget_override_invalid"


# ---------------------------------------------------------------------------
# AC6: the live-session snippet and the operator return the report
# ---------------------------------------------------------------------------


def _skill_snippet() -> str:
    match = re.search(r"```python\n(.*?)```", SKILL.read_text(encoding="utf-8"), re.DOTALL)
    assert match is not None, "SKILL.md has no fenced python block"
    return match.group(1)


def test_skill_snippet_and_operator_return_the_same_report(enabled_addon: str) -> None:
    """SCN006: the SKILL.md snippet and nmggamedev.inspect_spatial agree and change no scene."""
    build_probe()
    before = _snapshot()

    code = _skill_snippet().replace("<Name>", "Probe").replace("<asset_class>", "small_prop")
    namespace: dict[str, Any] = {}
    exec(compile(code, str(SKILL), "exec"), namespace)  # noqa: S102 - the documented snippet
    report = namespace["report"]
    assert report["kind"] == "inspect"
    assert _snapshot() == before

    assert bpy.ops.nmggamedev.inspect_spatial(
        collection_name="Probe", asset_class="small_prop"
    ) == {"FINISHED"}
    stored = json.loads(bpy.context.scene.nmg_game_dev.last_result)
    assert stored == json.loads(json.dumps(report))
    assert _snapshot() == before


def test_operator_reports_an_error_and_stores_no_report_on_a_missing_collection(
    enabled_addon: str,
) -> None:
    """AC6: a ContractError is an ERROR report (RuntimeError under bpy.ops) and stores nothing."""
    build_probe()
    bpy.context.scene.nmg_game_dev.last_result = ""
    with pytest.raises(RuntimeError, match="inspect.collection_missing"):
        bpy.ops.nmggamedev.inspect_spatial(collection_name="Missing", asset_class="small_prop")
    assert bpy.context.scene.nmg_game_dev.last_result == ""
