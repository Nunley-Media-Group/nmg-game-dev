"""Desktop and Mobile budgets from contract section 6, with nmg-budgets.json overrides.

Pure Python on purpose: the unit suite loads this file by path under plain CPython,
so it must not import bpy or use relative imports.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

BUDGET_ERROR_CODE: Final = "variants.budget_override_invalid"
ASSET_CLASSES: Final[tuple[str, ...]] = (
    "small_prop",
    "standard_prop",
    "hero_prop",
    "character",
    "environment_piece",
)
METRICS: Final[tuple[str, ...]] = ("tris", "max_texture_px", "materials")

CONTRACT_BUDGETS: Final[dict[str, dict[str, dict[str, int]]]] = {
    "small_prop": {
        "desktop": {"tris": 2000, "max_texture_px": 1024, "materials": 1},
        "mobile": {"tris": 500, "max_texture_px": 512, "materials": 1},
    },
    "standard_prop": {
        "desktop": {"tris": 10000, "max_texture_px": 2048, "materials": 3},
        "mobile": {"tris": 3000, "max_texture_px": 1024, "materials": 1},
    },
    "hero_prop": {
        "desktop": {"tris": 40000, "max_texture_px": 4096, "materials": 4},
        "mobile": {"tris": 10000, "max_texture_px": 2048, "materials": 2},
    },
    "character": {
        "desktop": {"tris": 60000, "max_texture_px": 4096, "materials": 4},
        "mobile": {"tris": 15000, "max_texture_px": 2048, "materials": 2},
    },
    "environment_piece": {
        "desktop": {"tris": 40000, "max_texture_px": 2048, "materials": 6},
        "mobile": {"tris": 10000, "max_texture_px": 1024, "materials": 3},
    },
}


class BudgetOverrideError(ValueError):
    """An nmg-budgets.json file or override that cannot be applied.

    The variants core re-raises this as VariantError so every operator reports the
    same code, message, and remediation shape.
    """

    def __init__(self, message: str, remediation: str) -> None:
        super().__init__(message)
        self.code = BUDGET_ERROR_CODE
        self.message = message
        self.remediation = remediation


def resolve_budget(asset_class: str, budgets_path: str | Path | None = None) -> dict[str, int]:
    """Return the Mobile budget for asset_class with nmg-budgets.json overrides merged in.

    Always returns a fresh dict, so callers can keep or mutate it safely.
    """
    if asset_class not in CONTRACT_BUDGETS:
        raise BudgetOverrideError(
            f"Unknown asset class '{asset_class}'.",
            f"Use one of: {', '.join(ASSET_CLASSES)}.",
        )
    budget = dict(CONTRACT_BUDGETS[asset_class]["mobile"])
    if not budgets_path:
        return budget
    overrides = load_overrides(Path(budgets_path))
    budget.update(overrides.get(asset_class, {}))
    return budget


def load_overrides(path: Path) -> dict[str, dict[str, int]]:
    """Read and validate an nmg-budgets.json file; every class and metric is checked."""
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BudgetOverrideError(
            f"Budget overrides file not found: {path}",
            "Pass the path to an existing nmg-budgets.json, or leave budgets_path empty "
            "to use the contract defaults.",
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise BudgetOverrideError(
            f"Budget overrides file is not readable JSON: {path} ({exc})",
            "Fix the JSON in nmg-budgets.json, or leave budgets_path empty.",
        ) from exc

    if not isinstance(raw, dict):
        raise BudgetOverrideError(
            "nmg-budgets.json must be a JSON object keyed by asset class.",
            'Use the form {"standard_prop": {"tris": 5000}}.',
        )

    overrides: dict[str, dict[str, int]] = {}
    for asset_class, metrics in raw.items():
        if asset_class not in CONTRACT_BUDGETS:
            raise BudgetOverrideError(
                f"Unknown asset class '{asset_class}' in {path.name}.",
                f"Use one of: {', '.join(ASSET_CLASSES)}.",
            )
        if not isinstance(metrics, dict):
            raise BudgetOverrideError(
                f"Overrides for '{asset_class}' must be an object of metric to integer.",
                f'Use the form {{"{asset_class}": {{"tris": 5000}}}}.',
            )
        checked: dict[str, int] = {}
        for metric, value in metrics.items():
            if metric not in METRICS:
                raise BudgetOverrideError(
                    f"Unknown budget metric '{metric}' for '{asset_class}'.",
                    f"Use one of: {', '.join(METRICS)}.",
                )
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise BudgetOverrideError(
                    f"Budget override {asset_class}.{metric} must be a positive integer, "
                    f"got {value!r}.",
                    "Set it to a positive whole number.",
                )
            checked[metric] = value
        overrides[asset_class] = checked
    return overrides
