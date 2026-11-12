"""Blender add-on budget table stays in sync with docs/asset-contract.md section 6 (FR6, FR8, AC6).

budgets.py is loaded by file path because the add-on is a Blender package that cannot be
imported under plain CPython; the module is kept free of bpy for exactly this reason.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUDGETS_PATH = _REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon" / "utils" / "budgets.py"
_CONTRACT_PATH = _REPO_ROOT / "docs" / "asset-contract.md"

_CLASS_ROWS = {
    "Small prop": "small_prop",
    "Standard prop": "standard_prop",
    "Hero prop": "hero_prop",
    "Character": "character",
    "Environment piece": "environment_piece",
}


def _load_budgets() -> ModuleType:
    spec = importlib.util.spec_from_file_location("nmg_budgets_under_test", _BUDGETS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _section_6() -> str:
    text = _CONTRACT_PATH.read_text(encoding="utf-8")
    return text.split("## 6. Budgets", 1)[1].split("\n## ", 1)[0]


def _parse_contract_budgets() -> dict[str, dict[str, dict[str, int]]]:
    """Read the section 6 table: Desktop/Mobile tris, max texture px, and D/M materials."""
    section = _section_6()
    parsed: dict[str, dict[str, dict[str, int]]] = {}
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] not in _CLASS_ROWS:
            continue
        numbers = [
            [int(token.replace(",", "")) for token in re.findall(r"\d[\d,]*", cell)]
            for cell in cells[2:]
        ]
        desktop_tris, mobile_tris = numbers[0][0], numbers[1][0]
        desktop_px, mobile_px = numbers[2][0], numbers[3][0]
        desktop_mats, mobile_mats = numbers[4][0], numbers[4][1]
        parsed[_CLASS_ROWS[cells[0]]] = {
            "desktop": {
                "tris": desktop_tris,
                "max_texture_px": desktop_px,
                "materials": desktop_mats,
            },
            "mobile": {"tris": mobile_tris, "max_texture_px": mobile_px, "materials": mobile_mats},
        }
    return parsed


def test_contract_table_lists_all_five_classes() -> None:
    assert set(_parse_contract_budgets()) == {
        "small_prop",
        "standard_prop",
        "hero_prop",
        "character",
        "environment_piece",
    }


@pytest.mark.parametrize(
    "asset_class",
    ["small_prop", "standard_prop", "hero_prop", "character", "environment_piece"],
)
def test_budget_table_matches_contract(asset_class: str) -> None:
    budgets = _load_budgets()
    expected = _parse_contract_budgets()[asset_class]
    assert budgets.CONTRACT_BUDGETS[asset_class] == expected


def test_resolve_budget_returns_contract_mobile_defaults() -> None:
    budgets = _load_budgets()
    assert budgets.resolve_budget("standard_prop") == {
        "tris": 3000,
        "max_texture_px": 1024,
        "materials": 1,
    }


def test_resolve_budget_returns_a_fresh_copy() -> None:
    budgets = _load_budgets()
    budget = budgets.resolve_budget("standard_prop")
    budget["tris"] = 1
    assert budgets.resolve_budget("standard_prop")["tris"] == 3000


def test_mobile_override_merges_over_contract_default(tmp_path: Path) -> None:
    budgets = _load_budgets()
    overrides = tmp_path / "nmg-budgets.json"
    overrides.write_text(json.dumps({"standard_prop": {"tris": 5000}}), encoding="utf-8")

    budget = budgets.resolve_budget("standard_prop", overrides)

    assert budget == {"tris": 5000, "max_texture_px": 1024, "materials": 1}


def test_override_only_changes_the_named_class(tmp_path: Path) -> None:
    budgets = _load_budgets()
    overrides = tmp_path / "nmg-budgets.json"
    overrides.write_text(json.dumps({"hero_prop": {"materials": 3}}), encoding="utf-8")

    assert budgets.resolve_budget("standard_prop", overrides)["tris"] == 3000
    assert budgets.resolve_budget("hero_prop", overrides)["materials"] == 3


def _expect_override_error(
    budgets: ModuleType, path: Path | None, asset_class: str = "standard_prop"
) -> Any:
    with pytest.raises(budgets.BudgetOverrideError) as info:
        budgets.resolve_budget(asset_class, path)
    assert info.value.code == "variants.budget_override_invalid"
    assert info.value.remediation
    return info.value


@pytest.mark.parametrize(
    "payload",
    [
        {"tiny_prop": {"tris": 100}},
        {"standard_prop": {"polygons": 100}},
        {"standard_prop": {"tris": 0}},
        {"standard_prop": {"tris": -5}},
        {"standard_prop": {"tris": "5000"}},
        {"standard_prop": {"tris": True}},
        {"standard_prop": 5000},
        [["standard_prop", {"tris": 5000}]],
    ],
)
def test_invalid_overrides_are_rejected(tmp_path: Path, payload: object) -> None:
    budgets = _load_budgets()
    overrides = tmp_path / "nmg-budgets.json"
    overrides.write_text(json.dumps(payload), encoding="utf-8")
    _expect_override_error(budgets, overrides)


def test_unknown_asset_class_is_rejected() -> None:
    budgets = _load_budgets()
    _expect_override_error(budgets, None, asset_class="tiny_prop")


def test_missing_overrides_file_is_rejected(tmp_path: Path) -> None:
    budgets = _load_budgets()
    error = _expect_override_error(budgets, tmp_path / "absent.json")
    assert "not found" in error.message


def test_budget_module_imports_no_bpy() -> None:
    tree = ast.parse(_BUDGETS_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    assert not {name for name in imported if name.split(".")[0] == "bpy"}


def test_desktop_override_applies_to_desktop_only(tmp_path: Path) -> None:
    """Top-level overrides go to Mobile; the nested desktop object goes to Desktop (#67)."""
    budgets = _load_budgets()
    path = tmp_path / "nmg-budgets.json"
    path.write_text(
        json.dumps({"standard_prop": {"tris": 5000, "desktop": {"max_texture_px": 256}}}),
        encoding="utf-8",
    )

    desktop = budgets.resolve_budget("standard_prop", path, "desktop")
    mobile = budgets.resolve_budget("standard_prop", path)

    assert desktop["max_texture_px"] == 256
    assert desktop["tris"] == 10000
    assert mobile["tris"] == 5000
    assert mobile["max_texture_px"] == 1024


def test_unknown_variant_is_rejected() -> None:
    budgets = _load_budgets()
    with pytest.raises(ValueError):
        budgets.resolve_budget("standard_prop", None, "lod2")


def test_desktop_override_must_be_an_object(tmp_path: Path) -> None:
    budgets = _load_budgets()
    path = tmp_path / "nmg-budgets.json"
    path.write_text(json.dumps({"standard_prop": {"desktop": 256}}), encoding="utf-8")
    with pytest.raises(budgets.BudgetOverrideError):
        budgets.resolve_budget("standard_prop", path, "desktop")


# ---------------------------------------------------------------------------
# Terrain (#154, FR1, FR2): defaults, class registration, and override rules
# ---------------------------------------------------------------------------

_HEIGHTFIELD_PATH = (
    _REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon" / "terrain_core" / "heightfield.py"
)


def _load_heightfield() -> ModuleType:
    spec = importlib.util.spec_from_file_location("nmg_heightfield_budget_test", _HEIGHTFIELD_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_terrain_is_a_registered_asset_class() -> None:
    budgets = _load_budgets()
    assert "terrain" in budgets.ASSET_CLASSES
    assert budgets.ASSET_CLASSES[-1] == "terrain"
    assert "terrain" in budgets.CONTRACT_BUDGETS


def test_terrain_budget_defaults_match_fr2() -> None:
    budgets = _load_budgets()
    assert budgets.CONTRACT_BUDGETS["terrain"] == {
        "desktop": {"heightmap_px": 2017, "layers": 4, "max_texture_px": 2048, "materials": 4},
        "mobile": {"heightmap_px": 1009, "layers": 3, "max_texture_px": 1024, "materials": 3},
    }


def test_terrain_metrics_include_heightmap_and_layers() -> None:
    budgets = _load_budgets()
    assert {"heightmap_px", "layers"} <= set(budgets.METRICS)


def test_resolve_budget_returns_terrain_mobile_defaults() -> None:
    budgets = _load_budgets()
    assert budgets.resolve_budget("terrain") == {
        "heightmap_px": 1009,
        "layers": 3,
        "max_texture_px": 1024,
        "materials": 3,
    }
    assert budgets.resolve_budget("terrain", None, "desktop")["heightmap_px"] == 2017


def test_valid_heightmap_sizes_mirror_the_heightfield_core() -> None:
    """budgets.py cannot import the core under plain CPython, so the tuples are checked here."""
    budgets = _load_budgets()
    assert budgets.VALID_HEIGHTMAP_SIZES == _load_heightfield().VALID_SIZES


def test_terrain_heightmap_and_layers_overrides_apply_to_mobile(tmp_path: Path) -> None:
    budgets = _load_budgets()
    path = tmp_path / "nmg-budgets.json"
    path.write_text(json.dumps({"terrain": {"heightmap_px": 505, "layers": 2}}), encoding="utf-8")
    mobile = budgets.resolve_budget("terrain", path)
    assert mobile["heightmap_px"] == 505
    assert mobile["layers"] == 2
    assert mobile["max_texture_px"] == 1024


def test_terrain_desktop_override_applies_to_desktop_only(tmp_path: Path) -> None:
    budgets = _load_budgets()
    path = tmp_path / "nmg-budgets.json"
    path.write_text(json.dumps({"terrain": {"desktop": {"heightmap_px": 505}}}), encoding="utf-8")
    assert budgets.resolve_budget("terrain", path, "desktop")["heightmap_px"] == 505
    assert budgets.resolve_budget("terrain", path)["heightmap_px"] == 1009


@pytest.mark.parametrize("size", [127, 253, 505, 1009, 2017, 4033])
def test_every_valid_heightmap_size_is_accepted(tmp_path: Path, size: int) -> None:
    budgets = _load_budgets()
    path = tmp_path / "nmg-budgets.json"
    path.write_text(json.dumps({"terrain": {"heightmap_px": size}}), encoding="utf-8")
    assert budgets.resolve_budget("terrain", path)["heightmap_px"] == size


@pytest.mark.parametrize("size", [1000, 2016, 128, 4096, 1])
def test_heightmap_outside_valid_sizes_raises_budget_override_invalid(
    tmp_path: Path, size: int
) -> None:
    budgets = _load_budgets()
    path = tmp_path / "nmg-budgets.json"
    path.write_text(json.dumps({"terrain": {"heightmap_px": size}}), encoding="utf-8")
    with pytest.raises(budgets.BudgetOverrideError) as info:
        budgets.resolve_budget("terrain", path)
    assert info.value.code == "variants.budget_override_invalid"
    assert "heightmap_px" in info.value.message
    assert info.value.remediation


def test_heightmap_desktop_override_outside_valid_sizes_is_rejected(tmp_path: Path) -> None:
    budgets = _load_budgets()
    path = tmp_path / "nmg-budgets.json"
    path.write_text(json.dumps({"terrain": {"desktop": {"heightmap_px": 1000}}}), encoding="utf-8")
    with pytest.raises(budgets.BudgetOverrideError) as info:
        budgets.resolve_budget("terrain", path, "desktop")
    assert info.value.code == "variants.budget_override_invalid"


@pytest.mark.parametrize(
    "payload",
    [
        {"terrain": {"tris": 5000}},
        {"terrain": {"desktop": {"tris": 5000}}},
        {"standard_prop": {"heightmap_px": 1009}},
        {"standard_prop": {"layers": 2}},
        {"environment_piece": {"desktop": {"layers": 2}}},
    ],
)
def test_heightmap_layers_and_tris_follow_their_class(
    tmp_path: Path, payload: dict[str, Any]
) -> None:
    budgets = _load_budgets()
    path = tmp_path / "nmg-budgets.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(budgets.BudgetOverrideError) as info:
        budgets.resolve_budget(next(iter(payload)), path)
    assert info.value.code == "variants.budget_override_invalid"


def test_terrain_materials_and_max_texture_remain_overridable(tmp_path: Path) -> None:
    budgets = _load_budgets()
    path = tmp_path / "nmg-budgets.json"
    path.write_text(
        json.dumps({"terrain": {"materials": 2, "max_texture_px": 512}}), encoding="utf-8"
    )
    mobile = budgets.resolve_budget("terrain", path)
    assert mobile["materials"] == 2
    assert mobile["max_texture_px"] == 512


def test_section_6_documents_the_nested_desktop_override(tmp_path: Path) -> None:
    """FR5 / #134: section 6 names nmg-budgets.json and its nested desktop override, and its
    JSON example is accepted by the real override loader and applies to Desktop."""
    section = _section_6()
    assert "nmg-budgets.json" in section
    assert "keyed by asset class" in section
    example = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)
    assert example is not None
    path = tmp_path / "nmg-budgets.json"
    path.write_text(example.group(1), encoding="utf-8")

    budgets = _load_budgets()

    assert budgets.resolve_budget("hero_prop", path, "desktop")["tris"] == 300000
    assert budgets.resolve_budget("hero_prop", path)["tris"] == 10000
