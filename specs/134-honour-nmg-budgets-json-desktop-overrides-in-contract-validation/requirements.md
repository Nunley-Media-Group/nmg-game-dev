# Defect Report: Contract validation ignores nmg-budgets.json Desktop overrides

**Issue**: #134
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Reproduction

1. Write an `nmg-budgets.json` containing `{"hero_prop": {"tris": 40000, "desktop": {"tris": 300000}}}`.
2. Author a `hero_prop` collection whose Desktop variant has more than 40,000 and fewer than 300,000 triangles.
3. Run the finalize `validate` step (or the export step) with `budgets_path` pointing at that file.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | The Desktop variant is checked against the overridden Desktop budget (300,000 tris), so no `budget.tris` finding is raised for it, consistent with `inspect_asset` and the bake step. |
| **Actual** | Validation fails with a `budget.tris` finding stating that the hero_prop desktop budget is 40000. |

## Acceptance Criteria

### AC1: Desktop triangle override is honoured

**Given** an `nmg-budgets.json` with `{"hero_prop": {"tris": 40000, "desktop": {"tris": 300000}}}` and a hero_prop Desktop variant between 40,000 and 300,000 triangles
**When** `validate_asset` runs with that `budgets_path`, both as the finalize validate step calls it (`authored=True`) and as the export pre-check calls it (full contract)
**Then** no `budget.tris` finding is reported for the Desktop variant

### AC2: Desktop override still enforces its own limit

**Given** the same overrides file and a hero_prop Desktop variant above 300,000 triangles
**When** `validate_asset` runs with that `budgets_path`
**Then** a `budget.tris` finding is reported for the Desktop variant and its message cites the 300000 budget

### AC3: Every Desktop budget metric uses the override

**Given** an overrides file whose `desktop` object sets `max_texture_px` or `materials` for a class
**When** the full contract (export pre-check) validates a Desktop variant against it
**Then** the Desktop `budget.texture_size` and `budget.materials` checks use the overridden values

### AC4: Mobile and default behavior is preserved

**Given** an overrides file with only top-level (Mobile) metrics, or no `budgets_path`
**When** `validate_asset` runs
**Then** the Desktop variant is checked against the contract §6 Desktop defaults and the Mobile variant against the top-level overrides, exactly as before

### AC5: Invalid desktop overrides fail with the existing error

**Given** an overrides file whose `desktop` object contains an unknown metric or a non-positive value
**When** `validate_asset` runs with that `budgets_path`
**Then** it raises the existing `variants.budget_override_invalid` contract error with its message and remediation

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `validate_asset` resolves the Desktop budget with `resolve_budget(asset_class, budgets_path, "desktop")` so the nested `desktop` overrides apply to tris, max_texture_px, and materials for the Desktop variant. | Must |
| FR2 | The finalize validate step and the export pre-check honour Desktop overrides through `validate_asset`, matching `inspect_asset` and the bake step. | Must |
| FR3 | Mobile budget resolution and the no-overrides path are unchanged. | Must |
| FR4 | Regression tests cover the Desktop override pass, the Desktop override fail, and the unchanged Mobile/default behavior. | Must |
| FR5 | `docs/asset-contract.md` §6 states that a class's nested `desktop` object in `nmg-budgets.json` overrides the Desktop budget used by validation, and that top-level metrics override Mobile. | Should |

## Out of Scope

- Changing the `nmg-budgets.json` format or the override semantics in `utils/budgets.py`.
- Changing the variants step, which builds Mobile and keeps using the Mobile budget.
- Changing the contract §6 default budget values.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #134 | 2026-11-11 | Initial defect report |
