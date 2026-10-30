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


def _parse_contract_budgets() -> dict[str, dict[str, dict[str, int]]]:
    """Read the section 6 table: Desktop/Mobile tris, max texture px, and D/M materials."""
    text = _CONTRACT_PATH.read_text(encoding="utf-8")
    section = text.split("## 6. Budgets", 1)[1].split("\n## ", 1)[0]
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
