"""Reduce plan under plain CPython: the budget split, overrides, bake settings, and misses (#139).

reduce_core/plan.py is loaded by file path because the add-on is a Blender package that cannot be
imported under CPython. The module must stay free of bpy, which this file also checks. Covers
AC3 (area split and the 12-triangle minimum), AC4 (override errors), AC7 (cage and ray settings),
AC8 (unbaked share), and AC9 (miss threshold).
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLAN_PATH = _REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon" / "reduce_core" / "plan.py"


def _load_plan() -> ModuleType:
    spec = importlib.util.spec_from_file_location("nmg_reduce_plan_under_test", _PLAN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plan = _load_plan()
PartStats = plan.PartStats
ReduceError = plan.ReduceError


def _parts(**areas_and_tris: tuple[float, int]) -> dict[str, Any]:
    return {
        name: PartStats(area_m2=area, tris=tris) for name, (area, tris) in areas_and_tris.items()
    }


def _code(callable_: Any, *args: Any) -> str:
    with pytest.raises(ReduceError) as caught:
        callable_(*args)
    return str(caught.value.code)


def test_plan_module_has_no_bpy_import() -> None:
    """The plan loads under CPython only because no import reaches bpy or a relative module."""
    tree = ast.parse(_PLAN_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] != "bpy" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert (node.module or "").split(".")[0] != "bpy"


def test_defaults_match_the_design() -> None:
    assert plan.DEFAULTS["cage_extrusion"] == 0.03
    assert plan.DEFAULTS["max_ray_distance"] == 0.10
    assert plan.DEFAULTS["miss_threshold"] == 0.01
    assert plan.DEFAULTS["min_part_tris"] == 12
    assert plan.DEFAULTS["samples"] == {"BC": 4, "R": 4, "M": 4, "N": 8, "AO": 48}


def test_budget_is_split_by_area_ac3() -> None:
    parts = _parts(Lower=(1.0, 5000), Upper=(3.0, 5000))
    targets = plan.split_budget(parts, 1200, {})
    assert targets == {"Lower": 300, "Upper": 900}
    assert sum(targets.values()) <= 1200


def test_each_part_keeps_at_least_twelve_triangles_ac3() -> None:
    parts = _parts(Tiny=(0.0001, 5000), Big=(10.0, 5000))
    targets = plan.split_budget(parts, 1000, {})
    assert targets["Tiny"] == 12
    assert targets["Big"] >= 12
    assert sum(targets.values()) <= 1000


def test_target_never_exceeds_source_triangles_ac3() -> None:
    parts = _parts(Small=(1.0, 40), Large=(1.0, 5000))
    targets = plan.split_budget(parts, 1000, {})
    assert targets["Small"] == 40
    assert sum(targets.values()) <= 1000


def test_overrides_fix_their_parts_and_the_rest_share_the_remainder_ac4() -> None:
    parts = _parts(Hero=(2.0, 5000), A=(1.0, 5000), B=(3.0, 5000))
    targets = plan.split_budget(parts, 1000, {"Hero": {"share": 0.5}})
    assert targets["Hero"] == 500
    assert targets["A"] == 125
    assert targets["B"] == 375


def test_tris_override_is_used_as_given_ac4() -> None:
    parts = _parts(Hero=(1.0, 5000), Other=(1.0, 5000))
    targets = plan.split_budget(parts, 1000, {"Hero": {"tris": 200}})
    assert targets == {"Hero": 200, "Other": 800}


def test_overrides_exceeding_the_budget_are_refused_ac4() -> None:
    parts = _parts(A=(1.0, 5000), B=(1.0, 5000))
    overrides = {"A": {"tris": 800}, "B": {"tris": 400}}
    assert _code(plan.split_budget, parts, 1000, overrides) == "reduce.overrides_exceed_budget"


def test_overrides_leaving_too_few_triangles_for_other_parts_are_refused_ac4() -> None:
    parts = _parts(A=(1.0, 5000), B=(1.0, 5000), C=(1.0, 5000))
    overrides = {"A": {"share": 0.99}}
    assert _code(plan.split_budget, parts, 1000, overrides) == "reduce.overrides_exceed_budget"


def test_unknown_part_override_is_refused_ac4() -> None:
    parts = _parts(A=(1.0, 5000))
    assert _code(plan.split_budget, parts, 1000, {"Missing": {"share": 0.5}}) == (
        "reduce.unknown_part"
    )


@pytest.mark.parametrize(
    "override",
    [
        {"share": 0.5, "tris": 100},
        {"share": 1.5},
        {"share": 0.0},
        {"tris": 0},
        {"tris": True},
        {"tris": 100, "colour": "red"},
    ],
)
def test_invalid_overrides_are_refused_ac4(override: dict[str, Any]) -> None:
    parts = _parts(A=(1.0, 5000), B=(1.0, 5000))
    assert _code(plan.split_budget, parts, 1000, {"A": override}) == "reduce.invalid_override"


def test_bake_settings_default_when_unset_ac7() -> None:
    settings = plan.bake_settings(["A", "B"], {}, {})
    assert settings == {
        "A": {"cage_extrusion": 0.03, "max_ray_distance": 0.10},
        "B": {"cage_extrusion": 0.03, "max_ray_distance": 0.10},
    }


def test_asset_wide_then_per_part_settings_win_ac7() -> None:
    settings = plan.bake_settings(
        ["A", "B"],
        {"cage_extrusion": 0.05, "max_ray_distance": None},
        {"B": {"max_ray_distance": 0.2}},
    )
    assert settings["A"] == {"cage_extrusion": 0.05, "max_ray_distance": 0.10}
    assert settings["B"] == {"cage_extrusion": 0.05, "max_ray_distance": 0.2}


def test_bake_settings_reject_unknown_part_and_non_positive_values_ac7() -> None:
    assert _code(plan.bake_settings, ["A"], {}, {"Z": {"cage_extrusion": 0.1}}) == (
        "reduce.unknown_part"
    )
    assert _code(plan.bake_settings, ["A"], {"cage_extrusion": 0.0}, {}) == (
        "reduce.invalid_override"
    )
    assert _code(plan.bake_settings, ["A"], {}, {"A": {"max_ray_distance": -1.0}}) == (
        "reduce.invalid_override"
    )


def test_unbaked_share_is_missed_over_island_texels_ac8() -> None:
    assert plan.unbaked_share(100, 10) == pytest.approx(0.1)
    assert plan.unbaked_share(0, 0) == 0.0


def test_check_misses_passes_at_or_below_threshold_ac9() -> None:
    settings = {"A": {"cage_extrusion": 0.03, "max_ray_distance": 0.1}}
    plan.check_misses({"A": 0.01}, 0.01, settings)


def test_check_misses_names_the_first_part_above_threshold_ac9() -> None:
    settings = {
        "A": {"cage_extrusion": 0.03, "max_ray_distance": 0.1},
        "B": {"cage_extrusion": 0.05, "max_ray_distance": 0.0001},
    }
    with pytest.raises(ReduceError) as caught:
        plan.check_misses({"A": 0.005, "B": 0.2}, 0.01, settings)
    error = caught.value
    assert error.code == "reduce.bake_misses"
    assert error.target == "B"
    assert "'B'" in error.message and "20.00%" in error.message
    assert "0.05" in error.message and "0.0001" in error.message


def test_error_as_dict_has_the_envelope_keys() -> None:
    error = ReduceError("reduce.rigged", "Rigged.", "Reduce before rigging.", target="Crate")
    assert error.as_dict() == {
        "code": "reduce.rigged",
        "message": "Rigged.",
        "remediation": "Reduce before rigging.",
        "target": "Crate",
    }
