# Tasks: Contract validation ignores nmg-budgets.json Desktop overrides

**Issue**: #134
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Resolve the Desktop budget through resolve_budget

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/validate.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `_budgets` returns `resolve_budget(asset_class, budgets_path or None, "desktop")` for Desktop and `resolve_budget(asset_class, budgets_path or None, "mobile")` for Mobile (FR1, FR3).
- A `BudgetOverrideError` from either call is re-raised as `ContractError` with the same code, message, and remediation (AC5).
- `validate_asset`'s signature and every caller (`finalize_core/steps.py` `_validate` and `_export`, `operators/validate_contract.py`) stay unchanged and pick up the Desktop override through `validate_asset` (FR2).
- No unused import remains; `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src tests` pass.

### T002: Add Desktop override regression tests

**File(s)**: `tests/blender/test_contract_validate.py`, `tests/blender/contract_fixtures.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- Tests write the overrides file to `tmp_path` and use the compliant Crate fixture validated as `hero_prop` or `standard_prop`, replacing `SM_Crate`'s mesh with a UV-mapped grid of a chosen triangle count through a fixture helper (generalizing the existing dense-grid helper).
- AC1: with `{"hero_prop": {"tris": 40000, "desktop": {"tris": 300000}}}` and a Desktop `SM_Crate` of 50,000 triangles, `validate_asset("Crate", "hero_prop", path, authored=True)` and `validate_asset("Crate", "hero_prop", path)` report no `budget.tris` finding whose target is a Desktop object.
- AC2: with the same file and a Desktop `SM_Crate` of more than 300,000 triangles, a `budget.tris` finding targets `SM_Crate` and its message contains `300000`.
- AC3: with `{"standard_prop": {"desktop": {"max_texture_px": 256}}}`, the full-contract report has a `budget.texture_size` finding targeting `T_Crate_Body_BC` (512 px) whose message cites `256`; with `{"standard_prop": {"desktop": {"materials": 1}}}` and a second material on `SM_Crate`, it has a `budget.materials` finding targeting `SM_Crate` whose message cites limit `1`. Without the override, neither finding appears for Desktop.
- AC4: with no `budgets_path`, a 50,000-triangle Desktop `SM_Crate` as `hero_prop` gets a Desktop `budget.tris` finding citing `40000`; with `{"standard_prop": {"tris": 3000}}` and the `mobile_lod0_4000_tris` defect, the Mobile `budget.tris` finding targets `SM_Crate_Mobile_LOD0` and cites `3000`, and the compliant Desktop has no budget finding.
- AC5: a `desktop` object with an unknown metric (`{"standard_prop": {"desktop": {"polys": 10}}}`) and one with a non-positive value (`{"standard_prop": {"desktop": {"tris": 0}}}`) each make `validate_asset` raise `ContractError` with code `variants.budget_override_invalid` and non-empty message and remediation.
- The AC1, AC2, and AC3 tests fail against the pre-fix `_budgets`; all pass with T001 through `scripts/run-blender-tests.sh` (validation `gate-blender-headless`).

### T003: Document Desktop overrides in contract section 6

**File(s)**: `docs/asset-contract.md`, `tests/unit/test_blender_budgets.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- Section 6 states, in prose outside the budget table, that `nmg-budgets.json` is keyed by asset class, that top-level metrics override the Mobile budget, and that a nested `desktop` object overrides the Desktop budget used by validation, with a short JSON example (FR5).
- The section 6 table rows are unchanged, so the existing table-sync tests in `tests/unit/test_blender_budgets.py` still pass.
- A new unit test in `tests/unit/test_blender_budgets.py` asserts the section 6 text names `nmg-budgets.json` and the nested `desktop` override; `uv run pytest tests/unit tests/bdd -q` (validation `repository.tests`) passes.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #134 | 2026-11-11 | Initial defect tasks |
