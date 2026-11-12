# Verification Report: Contract validation honours nmg-budgets.json Desktop overrides

**Date**: 2026-11-11
**Issue**: #134
**Reviewer**: Claude (nmg-sdlc architecture-reviewer)
**Scope**: Implementation verification against spec
**Verification head**: 15895db94997afba118bd585d0ab09a9306b5f3e

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 5 |
| Testability | 5 |
| Error Handling | 5 |
| **Overall** | 5.0 |

### Implementation Status: Pass
**Total Issues**: 1 (Low, not blocking)

The fix is the one-function change the design calls for. In `contract_core/validate.py`, `_budgets` now resolves the Desktop budget with `resolve_budget(asset_class, path, "desktop")` instead of copying the section 6 default from `CONTRACT_BUDGETS`. That matches how `bake_core/core.py` `_budgets` and `inspect_core/spatial.py` already resolve it. Every `validate_asset` caller now applies the nested `desktop` overrides with no signature change: the finalize validate step (`finalize_core/steps.py:98`), the export pre-check (`finalize_core/steps.py:178`) and the validate operator. This is a re-verification after `origin/main` (`d66e47e`, #173) was merged into the branch and the CHANGELOG entry was refiled under `## [Unreleased]`. The #134 code, tests and docs are unchanged by the merge. The registered gate was re-run at this head. All 11 registered validations are recorded. The 9 that apply passed and the other 2 do not apply to this change.

---

## Issue Scope

- Active issue: #134
- Spec: `specs/134-honour-nmg-budgets-json-desktop-overrides-in-contract-validation`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5]; FR [FR1, FR2, FR3, FR4, FR5]; tasks [T001, T002, T003]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":134,"specPath":"specs/134-honour-nmg-budgets-json-desktop-overrides-in-contract-validation","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5"],"tasks":["T001","T002","T003"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact

- Artifact: `.nmg-sdlc/verification/134.json`, generated 2026-11-11T22:46:27Z by `sdlc-verify-steering.mjs --issue 134 --base main --controller-run-id b3f40ae9-e8a6-44cb-acca-8329f3b5ebbc` (exit 0).
- Identity: head `15895db94997afba118bd585d0ab09a9306b5f3e`, clean tree.
- Coverage: declared 11, recorded 11, complete; no missing, duplicate or unknown results.
- Ceiling: none.
- Note: the local `main` ref (`41c5b31`) is older than `origin/main` (`d66e47e`), so the runner's changed-path set (139 paths) is wider than this issue's own diff against `origin/main` (7 files). That only makes more gates apply (for example `gate-mcp-schema`). It does not hide any gate.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Desktop triangle override is honoured (finalize validate step and export pre-check) | Pass | `contract_core/validate.py` `_budgets` resolves Desktop through `resolve_budget(..., "desktop")`. `test_scn001_desktop_tris_override_lets_a_larger_desktop_variant_pass` runs with `authored=True` and `authored=False` against a 50,000-triangle Desktop `SM_Crate` and gets no Desktop `budget.tris` finding |
| AC2 | Desktop override still enforces its own limit | Pass | `test_scn002_desktop_override_still_enforces_its_own_limit`: with 320,000 triangles, one Desktop `budget.tris` finding targets `SM_Crate` and its message cites `300000` |
| AC3 | Every Desktop budget metric uses the override | Pass | `test_scn003_desktop_texture_size_override_is_used_by_the_full_contract` (`T_Crate_Body_BC` against 256) and `test_scn003_desktop_materials_override_is_used_by_the_full_contract` (`SM_Crate` against limit 1). Each also checks that the finding is absent without the override |
| AC4 | Mobile and default behavior is preserved | Pass | `test_scn004_without_overrides_the_desktop_budget_is_the_contract_default` (cites `40000`) and `test_scn004_mobile_top_level_override_still_applies_to_mobile_only` (Mobile LOD0 against `3000`, no Desktop finding). Mobile still resolves with `resolve_budget(..., "mobile")`, which is the same result as the old default-variant call |
| AC5 | Invalid desktop overrides fail with the existing error | Pass | `_budgets` re-raises `BudgetOverrideError` from either call as `ContractError` with the same code, message and remediation. `test_scn005_invalid_desktop_override_raises_the_existing_error` covers `unknown_metric` and `non_positive_value` |

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `contract_core/validate.py` `_budgets` |
| FR2 | Pass | The callers at `finalize_core/steps.py:98` (validate) and `:178` (export) and `operators/validate_contract.py:50` are unchanged and get the override through `validate_asset` |
| FR3 | Pass | SCN004 tests; the no-path branch of `resolve_budget` returns the section 6 defaults |
| FR4 | Pass | 9 new Blender test cases in `tests/blender/test_contract_validate.py` |
| FR5 | Pass | `docs/asset-contract.md` section 6 prose and JSON example. `test_section_6_documents_the_nested_desktop_override` parses that example with the real loader |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Resolve the Desktop budget through resolve_budget | Complete | The `CONTRACT_BUDGETS` import was removed and is no longer used. Lint, format and types pass |
| T002 | Add Desktop override regression tests | Complete | `_replace_with_dense_grid` became `replace_mesh_with_grid(name, triangles)`, which gives non-overlapping UVs. `add_trim_material` was added. The `mobile_lod0_4000_tris` defect still produces 4,000 triangles (rows from `_grid_rows(2000)` = 40 x 50) |
| T003 | Document Desktop overrides in contract section 6 | Complete | The prose sits outside the table, so the table-sync tests still pass. A new unit test checks the section 6 text and its JSON example |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | `_budgets` only resolves budgets. Override semantics stay in `utils/budgets.py` |
| Open/Closed | 5 | No change to the override format or to `resolve_budget` |
| Liskov Substitution | 5 | N/A; the return shape `{"desktop", "mobile"}` is unchanged |
| Interface Segregation | 5 | The `validate_asset` signature is unchanged |
| Dependency Inversion | 5 | The core depends on the shared budget resolver, the same as bake and inspect |

### Layer Separation

The change stays in the step-implementation layer (`contract_core/`). The pipeline, MCP server and skill layers are untouched and get the corrected behavior through the existing `validate_asset` entry point.

### Dependency Flow

`contract_core.validate` → `utils.budgets` (pure Python). There is no new coupling.

---

## Security Assessment

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: overrides keep going through `load_overrides`/`_checked_metrics`. Unknown metrics, non-positive values and a non-object `desktop` are rejected
- [x] Injection prevention: N/A (JSON is only parsed, nothing is evaluated)
- [x] Data protection: N/A

---

## Performance Assessment

- [x] Async patterns: N/A
- [x] Caching: N/A
- [x] Resource management: no new handles
- [x] Query optimization: `nmg-budgets.json` is now read and parsed twice per `validate_asset` call (once per variant). Bake core does the same, and the cost is negligible next to scene traversal

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (`test_scn001_*`, 2 params) | Yes |
| AC2 | Yes (SCN002) | Yes (`test_scn002_*`) | Yes |
| AC3 | Yes (SCN003) | Yes (`test_scn003_*` x2) | Yes |
| AC4 | Yes (SCN004) | Yes (`test_scn004_*` x2) | Yes |
| AC5 | Yes (SCN005) | Yes (`test_scn005_*`, 2 params) | Yes |

### Coverage Summary

- Feature files: 5 scenarios in `specs/134-.../feature.gherkin`. Under tech steering, Blender add-on acceptance runs as pytest in headless Blender (`tests/blender/`)
- Step definitions: Implemented as `tests/blender/test_contract_validate.py` scenario tests
- Headless Blender suite: 211 passed, 0 failed (`gate-blender-headless`)
- Unit + BDD suite: 1008 passed, 9 skipped, 0 failed (`repository.tests`), including the new section 6 documentation test

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. The change touches no skill, agent, command or workflow file (`skills/`, `agents/`, `commands/`, `workflows/`), so there is no skill to exercise. `plugin.validate` and `plugin.session-smoke` apply through the changed-path set against local `main`, and both passed |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 1008 passed, 9 skipped |
| `repository.lint` | Pass | `uv run ruff check .` exited 0 |
| `repository.format` | Pass | `uv run ruff format --check .`: 314 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: no issues in 200 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 211 passed in 278.52 s |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8` (applies through the changed-path set against local `main`) |
| `gate-mcp-schema` | Pass | `uv run python scripts/validate-mcp-tools.py`: MCP tools match tools.json for every server (applies through the changed-path set against local `main`) |
| `gate-shellcheck` | N/A | Not applicable: no `scripts/**.sh` change |
| `gate-ship-smoke` | N/A | Not applicable: no ship path change |
| `plugin.validate` | Pass | `claude plugin validate .` exited 0 |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 9/9 applicable gates passed, 0 failed, 0 incomplete; 2 not applicable. Coverage 11/11 recorded.

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | No fixes were needed | — | — |

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Medium Priority
None.

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Architecture |
| **Location** | `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` `_budgets`; `plugins/nmg-game-dev-blender-addon/bake_core/core.py` `_budgets` |
| **Issue** | Two private `_budgets` helpers now resolve both variants and map `BudgetOverrideError` to their own error type in the same way |
| **Impact** | Small duplication; a future override-semantics change touches both cores |
| **Reason Not Fixed** | Out of scope for this defect. Each core maps the error to a different exception type, and the shared resolution already lives in `utils/budgets.py` |

---

## Positive Observations

- The regression tests check the variant of each finding's target through `report["snapshot"]`, so a Mobile finding cannot hide a Desktop regression and the reverse.
- The tests that need the fix (AC1–AC3) also assert the default behavior, which shows they test the override path and not the fixture.
- The generalized grid helper keeps the existing 4,000-triangle Mobile defect exact and adds a guard against odd triangle counts.
- The documentation test feeds the section 6 JSON example through the real loader, so the docs cannot drift from the format.

---

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- None.

### Long Term (Could)
- [ ] Consider a shared `resolve_variant_budgets(asset_class, path)` helper in `utils/budgets.py` for contract and bake cores.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 0 | Core fix |
| `plugins/nmg-game-dev-blender-addon/utils/budgets.py` | 0 | Unchanged; override semantics confirmed |
| `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py` | 0 | Callers unchanged |
| `plugins/nmg-game-dev-blender-addon/bake_core/core.py` | 1 (Low) | Reference behavior; duplication note |
| `tests/blender/contract_fixtures.py` | 0 | Grid helper generalized; trim material helper |
| `tests/blender/test_contract_validate.py` | 0 | SCN001–SCN005 |
| `tests/unit/test_blender_budgets.py` | 0 | Section 6 doc test |
| `docs/asset-contract.md` | 0 | FR5 prose and example |
| `CHANGELOG.md` | 0 | #134 entry under `## [Unreleased]` after the `origin/main` merge |

---

## Recommendation

**Ready for PR**

All five acceptance criteria, five functional requirements and three tasks are implemented and covered by passing tests. The registered gate is full green at `15895db94997afba118bd585d0ab09a9306b5f3e` with complete coverage. The only finding is a Low-priority duplication note that is outside this defect's scope.
