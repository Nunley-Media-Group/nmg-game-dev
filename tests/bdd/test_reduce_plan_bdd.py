"""pytest-bdd bindings for reduce_to_budget.feature: the plan-level scenarios of #139.

The budget split, the per-part bake settings, and the miss check are pure Python in
``reduce_core/plan.py``.  That module has no ``bpy`` import, so it loads by path under CPython, as
``tests/unit/test_blender_budgets.py`` does.  The Blender side of these scenarios (the scene
snapshot, the atlas, and the bake) is covered by ``tests/blender/test_reduce.py``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLAN_PATH = _REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon" / "reduce_core" / "plan.py"
_FEATURE = "reduce_to_budget.feature"


def _load_plan() -> ModuleType:
    spec = importlib.util.spec_from_file_location("nmg_reduce_plan_under_test", _PLAN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def state() -> dict[str, Any]:
    plan = _load_plan()
    return {
        "plan": plan,
        "parts": {
            "Body": plan.PartStats(area_m2=2.0, tris=20000),
            "Trim": plan.PartStats(area_m2=1.0, tris=8000),
            "Strap": plan.PartStats(area_m2=0.001, tris=40),
        },
        "budget": 3000,
        "overrides": {},
        "targets": None,
        "case": None,
        "part_names": ["Body", "Trim"],
        "asset_wide": {},
        "per_part": {},
        "settings": None,
        "shares": {},
        "error": None,
    }


# SCN002 ---------------------------------------------------------------------------------------


@scenario(_FEATURE, "The budget is split by surface area")
def test_budget_is_split_by_area() -> None:
    """SCN002: each part's target is proportional to its area and at least 12 triangles."""


@given("parts with different surface areas and no overrides")
def _areas_no_overrides(state: dict[str, Any]) -> None:
    state["overrides"] = {}


@when("the budget is planned")
def _plan_budget(state: dict[str, Any]) -> None:
    plan = state["plan"]
    try:
        state["targets"] = plan.split_budget(state["parts"], state["budget"], state["overrides"])
    except plan.ReduceError as error:
        state["error"] = error


@then("each part's target is proportional to its area and at least 12 triangles")
def _proportional(state: dict[str, Any]) -> None:
    targets: dict[str, int] = state["targets"]
    assert state["error"] is None
    assert all(target >= 12 for target in targets.values())
    assert sum(targets.values()) <= state["budget"]
    # Body has twice Trim's area, so its target is twice Trim's, to within flooring.
    assert abs(targets["Body"] / targets["Trim"] - 2.0) < 0.01
    # A target never exceeds the part's source triangles.
    for name, target in targets.items():
        assert target <= state["parts"][name].tris


# SCN003 ---------------------------------------------------------------------------------------


@scenario(_FEATURE, "Per-part overrides win and invalid overrides are refused")
def test_overrides_win_and_invalid_ones_are_refused() -> None:
    """SCN003: overridden parts use their values; an override above the budget is refused."""


@given("overrides for some parts")
def _some_overrides(state: dict[str, Any]) -> None:
    state["overrides"] = {"Trim": {"share": 0.5}}


@then("the overridden parts use their values and the rest share the remainder by area")
def _overrides_used(state: dict[str, Any]) -> None:
    assert state["error"] is None
    targets: dict[str, int] = state["targets"]
    assert targets["Trim"] == 1500  # floor(0.5 * 3000)
    assert targets["Body"] > targets["Strap"] >= 12
    assert targets["Body"] + targets["Strap"] <= state["budget"] - targets["Trim"]


@then("overrides above the budget fail with reduce.overrides_exceed_budget before any change")
def _overrides_exceed(state: dict[str, Any]) -> None:
    plan = state["plan"]
    overrides = {"Trim": {"tris": 2900}, "Body": {"tris": 200}}
    with pytest.raises(plan.ReduceError) as raised:
        plan.split_budget(state["parts"], state["budget"], overrides)
    assert raised.value.code == "reduce.overrides_exceed_budget"


# SCN005 ---------------------------------------------------------------------------------------


@scenario(_FEATURE, "Cage and ray distance are configurable per part")
def test_cage_and_ray_are_configurable_per_part() -> None:
    """SCN005: each part reports the cage extrusion and ray distance it used."""


@given("an asset-wide cage and a per-part ray distance")
def _cage_and_ray(state: dict[str, Any]) -> None:
    state["case"] = "cage"
    state["asset_wide"] = {"cage_extrusion": 0.05}
    state["per_part"] = {"Trim": {"max_ray_distance": 0.2}}


# SCN006 ---------------------------------------------------------------------------------------


@scenario(_FEATURE, "Ray misses are reported and fail above the threshold")
def test_ray_misses_fail_above_the_threshold() -> None:
    """SCN006: the failure names the part, its share, and its settings; nothing is applied."""


@given("a part whose unbaked share exceeds the miss threshold")
def _share_above_threshold(state: dict[str, Any]) -> None:
    state["case"] = "misses"
    state["shares"] = {"Trim": 0.04}


@when("the reduce step runs")
def _run_plan_step(state: dict[str, Any]) -> None:
    plan = state["plan"]
    if state["case"] == "cage":
        state["settings"] = plan.bake_settings(
            state["part_names"], state["asset_wide"], state["per_part"]
        )
        return
    settings = plan.bake_settings(state["part_names"], {}, {})
    try:
        plan.check_misses(state["shares"], plan.DEFAULTS["miss_threshold"], settings)
    except plan.ReduceError as error:
        state["error"] = error
    else:
        state["settings"] = settings


@then("each part reports the cage extrusion and ray distance it used")
def _settings_reported(state: dict[str, Any]) -> None:
    plan = state["plan"]
    settings: dict[str, dict[str, float]] = state["settings"]
    assert settings["Body"] == {
        "cage_extrusion": 0.05,
        "max_ray_distance": plan.DEFAULTS["max_ray_distance"],
    }
    assert settings["Trim"] == {
        "cage_extrusion": 0.05,
        "max_ray_distance": 0.2,
    }


@then("it fails with reduce.bake_misses naming the part, its share, and its settings")
def _misses_named(state: dict[str, Any]) -> None:
    error = state["error"]
    assert error is not None, "the miss check should have failed"
    assert error.code == "reduce.bake_misses"
    assert "Trim" in error.message
    assert "4.00%" in error.message
    assert "cage_extrusion" in error.message
    assert "max_ray_distance" in error.message


@then("the scene is unchanged")
def _nothing_applied(state: dict[str, Any]) -> None:
    # The plan has no scene. A failed check returns no settings, so nothing can be applied.
    # The scene snapshot itself is asserted in tests/blender/test_reduce.py.
    assert state["settings"] is None
