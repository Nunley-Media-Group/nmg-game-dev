# Verification Report: Blender cleanup, decimate, LOD, and variant operators

**Date**: 2026-10-30
**Issue**: #33
**Reviewer**: Claude (nmg-sdlc verify worker)
**Scope**: Implementation verification against spec

**Verification head**: 98779e5107a2a9a74e9d8da7d9d3b9acd812735b

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.5 |

### Implementation Status: Pass

**Total Issues**: 4 (0 critical, 0 high, 1 medium, 3 low). None block delivery.

The three add-on operator stubs are now real operators backed by one `variants_core` package. Each acceptance criterion has a headless Blender 5.2 test, and all of them pass. All 5 registered validations passed at the verification head, with complete coverage and no ceiling.

---

## Issue Scope

- Active issue: #33
- Spec: `specs/33-build-blender-cleanup-remesh-lod-and-variant-operators`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC8]; FR [FR1–FR9]; tasks [T001–T007]; scenarios [SCN001–SCN008]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":33,"specPath":"specs/33-build-blender-cleanup-remesh-lod-and-variant-operators","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9"],"tasks":["T001","T002","T003","T004","T005","T006","T007"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact

- Runner: `sdlc-verify-steering.mjs --base main --controller-run-id 85837256-3edd-4589-a50c-08ad4d01aafd`
- Artifact: `.nmg-sdlc/verification/33.json`, head `98779e5107a2a9a74e9d8da7d9d3b9acd812735b`
- Coverage: declared 5, recorded 5, complete `true`; missing, duplicate, and unknown are all empty
- Ceiling: none

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Desktop and Mobile FBX exported with identical names | Pass | `variants_core/export.py` (temp-renames Desktop, strips `_Mobile` for the Mobile export, then restores the names); `tests/blender/test_variants.py:67` re-imports both FBX files |
| AC2 | Desktop cleanup preserves quality | Pass | `variants_core/cleanup.py` (applies modifiers, removes doubles, zero-area faces and loose geometry, dissolves degenerate geometry, recalculates normals, never decimates); `test_variants.py:94` |
| AC3 | Mobile decimated to budget with two LODs | Pass | `variants_core/mobile.py` `_build_lod_group` (Empty `fbx_type=LodGroup`, LOD0 at budget, LOD1 at 50%, LOD2 at 25%); `textures.py` `mobile_image_copy` scales to 1,024 px; `test_variants.py:123` |
| AC4 | Sidecars record metrics and budget settings | Pass | `variants_core/sidecars.py`, `variants_core/__init__.py` (result keys), `operators/_common.py` `store_last_result`; `test_variants.py:147` |
| AC5 | Results are deterministic | Pass | `meshes.py` `fit_meshes` uses a fixed ratio schedule; sidecar keys are sorted; `test_variants.py:189` |
| AC6 | Budget overrides apply | Pass | `utils/budgets.py` `resolve_budget`; `test_variants.py:208`, `tests/unit/test_blender_budgets.py` |
| AC7 | Unsupported inputs fail with a remediation and no writes | Pass | `assets.py` `validate_inputs` runs before any mutation or write; operators return `CANCELLED` with code, message and remediation; `test_variants.py:229,246,254` |
| AC8 | Processing is local | Pass | No network imports in `variants_core`; `test_variants.py:267` patches `socket.socket` to raise |

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Contract budget table and override resolution | Complete | `utils/budgets.py`; imports no `bpy` |
| T002 | Core cleanup and Mobile build | Complete | `variants_core/{__init__,errors,cleanup,mobile,textures}.py`; the code is also split into `assets.py` and `meshes.py` |
| T003 | Export and sidecars | Complete | `variants_core/export.py`, `sidecars.py` |
| T004 | Real operators | Complete | Operators, `last_result` property, panel, `bl_info` text, `log_operator_result` |
| T005 | Contract update and changelog | Complete | Contract §5 LOD-group text added; CHANGELOG bullet ending `(#33)` (now under `[0.8.0]` after the version bump) |
| T006 | Budget table unit test | Complete | `tests/unit/test_blender_budgets.py` parses contract §6 |
| T007 | Blender headless variant tests | Complete | `conftest.py` fixtures, `test_variants.py` (11 tests); stub-behaviour tests in `test_operator_stubs.py` deleted |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Each module does one job: assets/validation, meshes, textures, cleanup, mobile, export, sidecars |
| Open/Closed | 4 | The budget table and overrides are data-driven; the allowed upstream node set is one frozenset |
| Liskov Substitution | 5 | N/A — no inheritance beyond Blender operator base classes |
| Interface Segregation | 4 | The core exposes three entry points; the operators are thin wrappers |
| Dependency Inversion | 4 | The operators depend on `variants_core`; the core depends on `bpy` directly, which is unavoidable in the add-on |

### Layer Separation

The operators parse properties, call `variants_core`, store `last_result`, and report errors. The core holds all the logic and can be called from `execute_blender_code` and from the future background-job pipeline (#69), as FR1 requires.

### Dependency Flow

The dependency chain is `operators → variants_core → utils.budgets`. `utils/budgets.py` imports no `bpy`, so it can be unit-tested from the host Python.

## Security Assessment

- [x] Authentication: N/A (local only)
- [x] Authorization: N/A
- [x] Input validation: collection, root mesh, materials, export root and budget overrides are validated before any write
- [x] Injection prevention: no shell or eval; JSON is parsed only through `json`
- [x] Data protection: no network I/O (AC8 is tested)

## Performance Assessment

- [x] Decimation is bounded: at most 20 passes per fit, and each pass works on a scratch copy that is then freed
- [x] Resource management: scratch objects, meshes and earlier Mobile datablocks are removed
- [ ] Texture copies use a full float pixel buffer per image. A 2048² RGBA image takes about 64 MB transiently, which is acceptable at current sizes

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1–AC8 | Yes (`feature.gherkin` SCN001–SCN008) | Yes (headless Blender tests in `tests/blender/test_variants.py`) | Yes |

### Coverage Summary

- Headless Blender suite (`scripts/run-blender-tests.sh` with Blender 5.2): 20 passed, 2 failed. Both failures are in `test_coexistence.py` and also fail identically on `main` (see Remaining Issues)
- All 11 `test_variants.py` tests pass, plus the registration tests
- Unit and BDD tests (`repository.tests`): passed, including `test_blender_budgets.py`

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | No nmg-sdlc plugin `workflows/` or `agents/` changes; this repo's Claude Code plugin surface was not modified. `plugin.validate` and `plugin.session-smoke` ran as registered validations and passed |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q` exited 0 |
| `repository.lint` | Pass | `uv run ruff check .` exited 0 |
| `repository.types` | Pass | `uv run mypy src tests` exited 0 |
| `plugin.validate` | Pass | `claude plugin validate .` exited 0 |
| `plugin.session-smoke` | Pass | Session smoke connected `blender` |

**Gate Summary**: 5/5 passed, 0 failed, 0 incomplete

Additional check (`gate-blender-headless` from tech steering; not a manifest-registered validation): 20/22 passed. The 2 coexistence failures already exist on `main` and are not caused by this change.

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | No code fixes were needed | — | — |

## Remaining Issues

### Medium Priority

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Supply chain |
| **Location** | `uv.lock` (package `nmg-game-dev`) |
| **Issue** | Version-bump commit `98779e5` raised `pyproject.toml` to 0.8.0 but left `uv.lock` at 0.7.0. Every `uv run` rewrites the lock and dirties the tree. Earlier bumps (#86, #87) updated `uv.lock` |
| **Impact** | The working tree goes dirty after any `uv run` |
| **Reason Not Fixed** | `uv.lock` is outside this verification's publication scope (only this report is writable). Fix by running `uv lock` and committing the result in delivery or a follow-up |

### Low Priority

- **`variants_core/export.py` `_unsuffixed`**: replaces the first `_Mobile` in a name, so an asset or material whose own name contains `_Mobile` (for example `M_Mobile_Body`) would be renamed wrongly. This is not reachable with contract-conforming names in practice. Not fixed because it is outside publication scope.
- **`variants_core/__init__.py` `generate_variants`**: does not validate `category`, so an empty category exports to `<root>/<Name>/`. The panel and pipeline always pass a category. Not fixed for the same scope reason.
- **`tests/blender/test_coexistence.py`**: `test_both_addons_load` and `test_disabling_nmg_leaves_host_functional` fail on this machine and also on `main`. The installed Blender MCP host add-on is a single file (`blender-mcp-addon.py`) and does not load under the probed id `blender_mcp`. This is environmental and comes from before #33.

---

## Positive Observations

- Validation finishes before any mutation or write, so failure runs leave no FBX or sidecar files.
- Decimation is deterministic: it uses a fixed ratio schedule and a sorted iteration order, and the sidecars use sorted keys.
- Desktop names are restored in a `finally` block after the Mobile export renames.
- The budget table is checked against the contract §6 markdown table, which prevents drift.

## Recommendations Summary

### Before PR (Must)

- [ ] None

### Short Term (Should)

- [ ] Run `uv lock` so `uv.lock` matches version 0.8.0

### Long Term (Could)

- [ ] Strip the `_Mobile` suffix only at the end of names; validate `category`
- [ ] Make the coexistence test probe the single-file host add-on id

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/variants_core/*.py` | 2 (low) | |
| `plugins/nmg-game-dev-blender-addon/operators/*.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/utils/budgets.py` | 0 | |
| `tests/blender/*.py`, `tests/unit/test_blender_budgets.py` | 0 | |
| `docs/asset-contract.md`, `CHANGELOG.md` | 0 | |
| `uv.lock` | 1 (medium) | Stale version |

## Recommendation

**Ready for PR**

All 8 acceptance criteria and 7 tasks are met, each with passing headless Blender evidence, and all 5 registered validations pass with complete coverage. The remaining items are low-risk follow-ups, and the stale `uv.lock` version is best fixed during delivery.
