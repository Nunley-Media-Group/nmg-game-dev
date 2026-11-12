# Verification Report: import_ue fails multi-part static imports because UE 5.8 reports only the first mesh on the import task

**Date**: 2026-11-11
**Issue**: #141
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Implementation verification against spec, after `4ff3217` removed the duplicate released CHANGELOG heading that the merge left behind

**Verification head**: 4ff3217fb005f7e0b544c062df416bd223c99d88

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 5 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.7 |

### Implementation Status: Pass
**Total Issues**: 3 (all low, none blocking)

All nine acceptance criteria (AC1 to AC9) are tested by running the generated code against the in-memory fake `unreal` module. All 10 applicable registered gates passed at the verification head, and `gate-ship-smoke` did not apply. Coverage is complete: 11 declared, 11 recorded, no ceiling.

The previous verification's only blocker is fixed. That was the merge residue in `CHANGELOG.md`: a duplicate `## [0.21.4] - 2026-11-11` heading inside a released section. `git diff origin/main...HEAD` now touches 5 files. In `CHANGELOG.md` the only change is the #141 entry under `## [Unreleased]`. `VERSION`, `.claude-plugin/plugin.json` and the plugin manifests match `origin/main` (0.21.4).

---

## Issue Scope

- Active issue: #141
- Spec: `specs/141-fix-import-ue-failing-multi-part-static-imports-because-ue-5-8-reports-only-the-first-mesh-on-the-import-task`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9]; FR [FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8]; tasks [T001, T002, T003]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005, SCN006, SCN007, SCN008, SCN009]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":141,"specPath":"specs/141-fix-import-ue-failing-multi-part-static-imports-because-ue-5-8-reports-only-the-first-mesh-on-the-import-task","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8"],"tasks":["T001","T002","T003"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 141 --spec specs/141-… --base main --controller-run-id 6a7e9943-20d2-4752-90aa-3efd088d9ec4` exited 0. Generated 2026-11-12T02:42:38Z.
- Artifact: `.nmg-sdlc/verification/141.json`. Head `4ff3217fb005f7e0b544c062df416bd223c99d88`, tree clean. Steering `sha256:795f9897…c0e4`, spec `sha256:8549d50b…97c5`.
- Coverage: declared 11, recorded 11, `complete: true`. Nothing missing, duplicated or unknown.
- Ceiling: `null`. No required validation failed or was incomplete.
- Base ref: the local `main` is behind `origin/main`, so the runner treated more paths as changed than the 5-file diff against `origin/main` does. It ran every path-scoped gate except `gate-ship-smoke`. That is stricter than this change needs.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Multi-part static import returns every part | Pass | `_import_meshes` → `_resolve_expected(unreal.StaticMesh)` (`src/nmg_game_dev/unreal/import_asset.py:323`, `:255`); `test_a_multi_part_static_import_returns_every_part` (`tests/unit/test_unreal_import.py:1016`) |
| AC2 | Expected meshes resolved by name from dest, by class; unrelated assets ignored | Pass | `_resolve_expected` tries each `PARAMS["expected_meshes"]` candidate as `dest/<name>` with `does_asset_exist`, `load_asset` and `isinstance` (`import_asset.py:255-281`); `test_expected_meshes_are_resolved_by_name_and_an_unrelated_mesh_is_ignored` (`:1057`) |
| AC3 | Rigged Desktop import guarantees skeleton and physics asset | Pass | `_ensure_rig_assets` (`import_asset.py:299`): fails on a missing skeleton, calls `create_physics_asset`, uses `rename_asset` to move it into place, sets `physics_asset`, and saves both; tests at `:1080`, `:1099`, `:1114` |
| AC4 | Rigged Mobile import reuses the Desktop skeleton and physics asset | Pass | `_skeletal_options(desktop=False)` loads the `skeleton_dest` assets (`import_asset.py:228`); `import_lod` for LOD 1 and 2 (`:338`); `test_a_rigged_mobile_import_reuses_the_desktop_skeleton_and_physics_asset` (`:1131`) |
| AC5 | A re-import reports the new geometry | Pass | Meshes are loaded from the folder after `import_asset_tasks` with `replace_existing`; `test_a_reimport_reports_the_new_bounds_and_passes_the_pivot_check` (`:1168`) |
| AC6 | A missing part fails with every missing asset named | Pass | `missing` is collected across all candidate lists and raised once (`import_asset.py:274-280`); `test_two_missing_parts_fail_the_import_and_name_both` (`:1185`) checks for `import_ue.failed` naming both parts |
| AC7 | Regression test with a two-part fixture and an under-reporting task | Pass | `FakeWorld.reported_paths` setting (`tests/unit/fake_unreal.py`); `test_a_two_part_static_import_returns_both_parts_when_the_task_lists_only_the_first` (`:1037`) |
| AC8 | Existing import behavior preserved | Pass | `test_texture_settings_material_binding_and_result_keys_are_unchanged` (`:690`), the single-part, #145 and #146 tests (`:561`, `:617`, `:642`, `:994`); 65/65 pass in the file |
| AC9 | The Interchange cvar is not offered as a workaround | Pass | `grep -rn "Interchange.FeatureFlags" src skills docs scripts templates` finds nothing; `test_no_shipped_file_offers_the_interchange_cvar_as_a_workaround` (`:1201`) |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | The template never reads `imported_object_paths` and never calls `get_objects()`; the name appears only in the module docstring |
| FR2 | Pass | Only `expected_meshes` names are resolved and passed to `_bind_materials` |
| FR3 | Pass | `_ensure_rig_assets` runs only on the Desktop path |
| FR4 | Pass | Re-import test |
| FR5 | Pass | One combined `RuntimeError`, reported as `import_ue.failed` |
| FR6 | Pass | Repository scan test and grep |
| FR7 | Pass | `NMG_RESULT` keys, error codes, texture import, LOD import and the pivot check are unchanged. #145's scale and rename steps run on `_part_meshes()` before resolution, and #146's candidate lists are used as given |
| FR8 | Pass | `fake_unreal.py` extends #145's shared fake with `reported_paths`, `skeleton_on_import`, `physics_folder`, `create_physics_asset`, `import_lod`, and `run_import_code` |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Resolve meshes from dest; guarantee rig assets | Complete | `_resolve_expected`, `_part_meshes`, `_ensure_rig_assets`; docstring updated |
| T002 | Extend the shared fake `unreal` module | Complete | Reuses #145's fake; its existing behavior is kept |
| T003 | Executed-code regression tests | Complete | 10 new tests |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Each new template helper has one job: resolve, find parts, or ensure rig assets. `_ensure_rig_assets` validates, creates, moves and saves, which is acceptable at this size |
| Open/Closed | 4 | The asset class is a parameter of `_resolve_expected`, so static and skeletal imports share one path |
| Liskov Substitution | 5 | The fake satisfies the `UnrealPythonClient` protocol |
| Interface Segregation | 5 | The host-side API (`build_import_code`, `import_variant`, `check_pivots`) is unchanged |
| Dependency Inversion | 4 | The generated code depends on the `unreal` module by name; tests swap it through `sys.modules` |

### Layer Separation

All behavior stays inside the UE-side `_IMPORT_TEMPLATE` in `src/nmg_game_dev/unreal/`, the step-implementation layer. Pipeline orchestration is untouched.

### Dependency Flow

Shipped code gains no imports. The test fake imports `parse_nmg_result` from the public package.

---

## Security Assessment

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: asset paths come from the snapshot report through `PARAMS`, which the host serializes as JSON
- [x] Injection prevention: no new string-built code; `PARAMS` is embedded as JSON by `build_import_code`
- [x] Data protection: N/A

## Performance Assessment

- [x] Async patterns: N/A. The import is synchronous by design; polling is out of scope
- [x] Caching: N/A
- [x] Resource management: at most one `does_asset_exist` and one `load_asset` per candidate name
- [x] Query optimization: the candidate search stops at the first match

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Test | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | SCN001 | Yes | Yes |
| AC2 | SCN002 | Yes | Yes |
| AC3 | SCN003 | Yes (3 tests) | Yes |
| AC4 | SCN004 | Yes | Yes |
| AC5 | SCN005 | Yes | Yes |
| AC6 | SCN006 | Yes | Yes |
| AC7 | SCN007 | Yes | Yes |
| AC8 | SCN008 | Yes | Yes |
| AC9 | SCN009 | Yes | Yes |

### Coverage Summary

- Feature file: `specs/141-.../feature.gherkin`, 9 scenarios. Each maps to an executed unit test in `tests/unit/test_unreal_import.py`, as the gherkin header declares.
- Unit tests: 10 new #141 tests. `repository.tests` exited 0, and a separate run of `uv run pytest tests/unit/test_unreal_import.py -q` passed 65 tests.
- No live editor was used. Every import test runs against `tests/unit/fake_unreal.py`.

---

## Exercise Test Results

Not applicable. No nmg-sdlc plugin workflow or agent files changed, and the change touches no consumer skill.

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q` exited 0 |
| `repository.lint` | Pass | `uv run ruff check .` exited 0 |
| `repository.format` | Pass | `uv run ruff format --check .` exited 0 |
| `repository.types` | Pass | `uv run mypy src tests` exited 0 |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh` exited 0 |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8` |
| `gate-mcp-schema` | Pass | `uv run python scripts/validate-mcp-tools.py` exited 0 |
| `gate-shellcheck` | Pass | `find scripts -name *.sh -exec shellcheck -S style {} +` exited 0 |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .` exited 0 |
| `plugin.session-smoke` | Pass | Loaded the plugin via `--plugin-dir` in an ephemeral project; `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None needed in this verify pass. The earlier CHANGELOG blocker was fixed in implementation (`4ff3217`) | — | — |

## Remaining Issues

### Low Priority

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Low | Error Handling | `src/nmg_game_dev/unreal/import_asset.py:255` | Resolution reads the destination folder. If a re-import silently fails to recreate a part, a stale asset with the expected name from an earlier import satisfies the lookup, and the part is not reported missing. The pivot check against the new snapshot still catches changed geometry | Inherent to the approved design, which chose folder resolution over the under-reporting task list |
| Low | Error Handling | `src/nmg_game_dev/unreal/import_asset.py:299` | When the import already made `SM_<Name>_PhysicsAsset`, `_ensure_rig_assets` returns without checking that it is assigned to the mesh. UE assigns the physics asset it creates during import | Matches the spec, which requires assignment only for a created asset |
| Low | Testability | `src/nmg_game_dev/unreal/import_asset.py:284` | `_part_meshes` silently skips a datablock whose asset is not a Static Mesh | `_resolve_expected` then reports that part as missing, so the failure still names it |

---

## Positive Observations

- One combined error names every missing part, so one run shows everything to fix.
- The fake models UE 5.8's under-reporting with a setting (`reported_paths`), so the regression reproduces without an editor.
- The fix composes with #145 (scale and rename before resolution) and #146 (candidate lists used as given) exactly as the design says, and their tests still pass.

---

## Recommendations Summary

### Before PR (Must)
- [x] None

### Short Term (Should)
- [ ] None

### Long Term (Could)
- [ ] Check the physics-asset assignment even when the import made the asset.
- [ ] Consider checking that a resolved mesh was written by this import, for example by its package save time, to catch stale assets.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `src/nmg_game_dev/unreal/import_asset.py` | 3 (low) | Folder resolution and the rig-asset guarantee |
| `tests/unit/fake_unreal.py` | 0 | Scenario settings and `run_import_code` |
| `tests/unit/test_unreal_import.py` | 0 | 10 #141 tests |
| `CHANGELOG.md` | 0 | Only the #141 entry under `## [Unreleased]`; released sections match `origin/main` |

---

## Recommendation

**Ready for PR**

The #141 implementation meets every acceptance criterion. All applicable registered gates pass at `4ff3217fb005f7e0b544c062df416bd223c99d88`, coverage is complete, and the release files match `origin/main`.
