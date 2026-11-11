# Root Cause Analysis: Contract validation ignores nmg-budgets.json Desktop overrides

**Issue**: #134
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Root Cause

`validate_asset` builds its per-variant budgets with `_budgets(asset_class, budgets_path)` in `plugins/nmg-game-dev-blender-addon/contract_core/validate.py`. `_budgets` calls `resolve_budget(asset_class, budgets_path or None)`, whose default variant is Mobile, and returns `dict(CONTRACT_BUDGETS[asset_class]["desktop"])` for Desktop. The Desktop entry never passes through `resolve_budget(..., "desktop")`, so the nested `desktop` object in `nmg-budgets.json` is never merged. `_budget_findings` then compares the Desktop variant's triangle total, material count, and largest texture against the §6 defaults.

The overrides file is still fully validated, because the Mobile call loads it through `load_overrides`, which checks every class including the `desktop` object. Invalid Desktop overrides therefore already raise `variants.budget_override_invalid`; only valid ones are ignored.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | `_budgets` | Builds the Desktop budget from defaults instead of `resolve_budget(..., "desktop")` |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | `validate_asset`, `_budget_findings` | Consume `budgets["desktop"]` for `budget.tris`, `budget.materials`, `budget.texture_size` |
| `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py` | `_validate`, `_export` | Call `validate_asset` with the request's `budgets_path` (unchanged) |
| `plugins/nmg-game-dev-blender-addon/operators/validate_contract.py` | `execute` | Calls `validate_asset` with the operator's `budgets_path` (unchanged) |
| `plugins/nmg-game-dev-blender-addon/utils/budgets.py` | `resolve_budget`, `load_overrides` | Already merge and validate Desktop overrides (unchanged) |

## Fix Strategy

In `_budgets`, resolve both variants through `resolve_budget` inside the existing `try`:

    path = budgets_path or None
    desktop = resolve_budget(asset_class, path, "desktop")
    mobile = resolve_budget(asset_class, path, "mobile")
    return {"desktop": desktop, "mobile": mobile}

`BudgetOverrideError` is still re-raised as `ContractError(error.code, error.message, error.remediation)`. Drop the `CONTRACT_BUDGETS` import if it becomes unused. This mirrors `bake_core/core.py` `_budgets`.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | `_budgets` resolves Desktop with `resolve_budget(asset_class, path, "desktop")` | AC1, AC2, AC3, FR1, FR2 |
| `tests/blender/test_contract_validate.py` | Regression tests for Desktop override pass/fail, texture and material overrides, preserved Mobile/default behavior, invalid Desktop overrides | AC1–AC5, FR3, FR4 |
| `docs/asset-contract.md` | §6 prose (outside the table) describing `nmg-budgets.json` top-level (Mobile) and nested `desktop` overrides | FR5 |
| `tests/unit/test_blender_budgets.py` | Assert the §6 text documents the nested `desktop` override | FR5 |

## Blast Radius

Every `validate_asset` caller: the finalize `validate` step (`authored=True`), the export pre-check (full contract, whose report also feeds `reimport_check`), and the `nmggamedev.validate_contract` operator. With no `budgets_path`, or with a file that has no `desktop` object for the class, `resolve_budget(..., "desktop")` returns the §6 defaults, so results are identical. Only Desktop budgets with an explicit nested override change. The Mobile path is untouched. The §6 table rows that `tests/unit/test_blender_budgets.py` parses are not edited.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Resolve Desktop with `resolve_budget(..., "desktop")` in `_budgets` | Selected | One-line fix, reuses the tested resolver, matches the bake step and `inspect_asset` |
| Merge `class_overrides["desktop"]` inline in `validate.py` | Rejected | Duplicates `resolve_budget` logic that is out of scope to change |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #134 | 2026-11-11 | Initial defect design |
