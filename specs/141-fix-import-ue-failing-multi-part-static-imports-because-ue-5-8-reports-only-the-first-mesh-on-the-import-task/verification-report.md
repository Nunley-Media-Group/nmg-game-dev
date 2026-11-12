# Verification Report: import_ue fails multi-part static imports because UE 5.8 reports only the first mesh on the import task

**Date**: 2026-11-11
**Issue**: #141
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Implementation verification against spec, after the `chore: merge origin/main into #141 branch` merge

**Verification head**: 06f385a81650717abfc3163a358d6a866efb3cfe

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

### Implementation Status: Partial
**Total Issues**: 3 (1 high, 2 low)

The fix itself is complete. Every acceptance criterion (AC1 to AC9) has executed-code coverage against the in-memory fake `unreal` module, and all 10 applicable registered gates passed at the verification head. Coverage is complete: 11 declared, 11 recorded.

Status is **Partial** because the merge commit `06f385a` damaged a released section of `CHANGELOG.md`. It left a duplicate, empty `## [0.21.4] - 2026-11-11` / `### Fixed` heading under main's released `## [0.21.4] - 2026-11-12` section. That section is identical to `origin/main` everywhere else. Delivering as-is would publish a duplicate released-version heading on `main`. The file is outside this verify stage's writable scope, which is only the report, so the fix goes back to implementation. It is a single four-line deletion (see Remaining Issues).

---

## Issue Scope

- Active issue: #141
- Spec: `specs/141-fix-import-ue-failing-multi-part-static-imports-because-ue-5-8-reports-only-the-first-mesh-on-the-import-task`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9]; FR [FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8]; tasks [T001, T002, T003]; scenarios [SCN001 to SCN009]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":141,"specPath":"specs/141-fix-import-ue-failing-multi-part-static-imports-because-ue-5-8-reports-only-the-first-mesh-on-the-import-task","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8"],"tasks":["T001","T002","T003"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Not complete. Spec ACs and every applicable gate passed, but the CHANGELOG merge defect blocks delivery.
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 141 --spec specs/141-… --base main --controller-run-id 6a7e9943-20d2-4752-90aa-3efd088d9ec4` (exit 0, `ok: true`), generated 2026-11-12T02:35:49Z
- Artifact: `.nmg-sdlc/verification/141.json`, head `06f385a81650717abfc3163a358d6a866efb3cfe`, steering `sha256:795f9897…c0e4`, spec `sha256:8549d50b…97c5`
- Coverage: declared 11, recorded 11, complete `true`; missing, duplicate and unknown are all empty
- Ceiling: `null`. No required validation failed or was incomplete.
- Base ref `main`: the local `main` is behind `origin/main`, so the runner treated 200 paths as changed and ran every path-scoped gate except `gate-ship-smoke`. That is stricter than the 5-file diff against `origin/main` requires.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Multi-part static import returns every part | Pass | `_import_meshes` → `_resolve_expected(unreal.StaticMesh)` (`src/nmg_game_dev/unreal/import_asset.py:255`, `:323`); `test_a_multi_part_static_import_returns_every_part` (`tests/unit/test_unreal_import.py:1016`) |
| AC2 | Expected meshes resolved by name from dest, by class; unrelated assets ignored | Pass | `_resolve_expected` tries each `PARAMS["expected_meshes"]` candidate as `dest/<name>` with `does_asset_exist` + `load_asset` + `isinstance` (`import_asset.py:255-281`); `test_expected_meshes_are_resolved_by_name_and_an_unrelated_mesh_is_ignored` (`:1057`) |
| AC3 | Rigged Desktop import guarantees skeleton and physics asset | Pass | `_ensure_rig_assets` (`import_asset.py:299`): fails on a missing skeleton, then `create_physics_asset`, `rename_asset` into place, `set_editor_property("physics_asset")`, and saves both; tests at `:1080`, `:1099`, `:1114` |
| AC4 | Rigged Mobile import reuses the Desktop skeleton and physics asset | Pass | `_skeletal_options(desktop=False)` loads `skeleton_dest` assets (`import_asset.py:228-240`); `import_lod` for LOD 1/2 (`:356`); `test_a_rigged_mobile_import_reuses_the_desktop_skeleton_and_physics_asset` (`:1131`) |
| AC5 | A re-import reports the new geometry | Pass | Meshes are loaded from the folder after `import_asset_tasks` with `replace_existing`; `test_a_reimport_reports_the_new_bounds_and_passes_the_pivot_check` (`:1168`) |
| AC6 | A missing part fails with every missing asset named | Pass | `missing` is collected across all candidate lists and raised once (`import_asset.py:274-280`); `test_two_missing_parts_fail_the_import_and_name_both` (`:1185`) asserts `import_ue.failed` naming both |
| AC7 | Regression test with a two-part fixture and an under-reporting task | Pass | `FakeWorld.reported_paths` knob (`tests/unit/fake_unreal.py`); `test_a_two_part_static_import_returns_both_parts_when_the_task_lists_only_the_first` (`:1037`) |
| AC8 | Existing import behavior preserved | Pass | `test_texture_settings_material_binding_and_result_keys_are_unchanged` (`:690`) and all earlier #145/#146 tests pass (65/65 in the file; `repository.tests` exited 0) |
| AC9 | The Interchange cvar is not offered as a workaround | Pass | `grep -r "Interchange.FeatureFlags.Import.FBX" src skills docs scripts templates` finds nothing; `test_no_shipped_file_offers_the_interchange_cvar_as_a_workaround` (`:1201`) |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `imported_object_paths` and `get_objects()` are not read anywhere in the template (only a docstring mention at `import_asset.py:34`) |
| FR2 | Pass | Only `expected_meshes` names are resolved and returned to `_bind_materials` |
| FR3 | Pass | `_ensure_rig_assets` (Desktop only) |
| FR4 | Pass | Re-import test |
| FR5 | Pass | Single aggregated `RuntimeError` → `import_ue.failed` |
| FR6 | Pass | Repo scan test plus grep |
| FR7 | Pass | `NMG_RESULT` keys, error codes, textures, LOD import and pivot check unchanged; #145 scale/rename now runs on `_part_meshes()` before resolution, and #146 candidates are used as given |
| FR8 | Pass | `fake_unreal.py` extends #145's shared fake with `reported_paths`, `skeleton_on_import`, `physics_folder`, `create_physics_asset`, `import_lod`, and `run_import_code` |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Resolve meshes from dest; guarantee rig assets | Complete | `_resolve_expected`, `_part_meshes`, `_ensure_rig_assets`; docstring updated |
| T002 | Extend the shared fake `unreal` module | Complete | Reuses #145's fake and keeps its existing behavior |
| T003 | Executed-code regression tests | Complete | 10 new tests; the existing rigged test was updated for the new rig assets |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Each new template helper has one job (resolve, find parts, ensure rig). `_ensure_rig_assets` combines validation, creation, relocation and save; acceptable at this size |
| Open/Closed | 4 | The asset class is a parameter of `_resolve_expected`, so static and skeletal share one path |
| Liskov Substitution | 5 | N/A beyond the fake honoring the `UnrealPythonClient` protocol |
| Interface Segregation | 5 | Host-side API (`build_import_code`, `import_variant`, `check_pivots`) unchanged |
| Dependency Inversion | 4 | Generated code depends on the `unreal` module by name; tests substitute it through `sys.modules` |

### Layer Separation

All behavior stays inside the UE-side `_IMPORT_TEMPLATE` in `src/nmg_game_dev/unreal/`, the step-implementation layer. Pipeline orchestration (`pipeline/engine.py`) is untouched.

### Dependency Flow

No new imports in shipped code. The test fake imports `parse_nmg_result` from the public package.

---

## Security Assessment

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: asset paths come from the snapshot report and `PARAMS`, which the host serializes; nothing is evaluated
- [x] Injection prevention: no new string-built code; `PARAMS` is already JSON-embedded by `build_import_code`
- [x] Data protection: N/A

## Performance Assessment

- [x] Async patterns: N/A. The import is synchronous by design (out of scope: polling)
- [x] Caching: N/A
- [x] Resource management: at most one `does_asset_exist` + `load_asset` per candidate name; trivial
- [x] Query optimization: candidate search stops at the first match

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

- Feature file: `specs/141-.../feature.gherkin`, 9 scenarios, all mapped to executed unit tests in `tests/unit/test_unreal_import.py` (as the gherkin header declares)
- Unit tests: 10 new or updated #141 tests; `repository.tests` exited 0; `test_unreal_import.py` 65 passed
- No live editor was used: every import test runs against `tests/unit/fake_unreal.py`

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: exited 0 (independent rerun of `tests/unit/test_unreal_import.py`: 65 passed) |
| `repository.lint` | Pass | `uv run ruff check .`: exited 0 |
| `repository.format` | Pass | `uv run ruff format --check .`: exited 0 |
| `repository.types` | Pass | `uv run mypy src tests`: exited 0 |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: exited 0 |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8` |
| `gate-mcp-schema` | Pass | `scripts/validate-mcp-tools.py`: exited 0 |
| `gate-shellcheck` | Pass | shellcheck exited 0 |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .`: exited 0 |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None. The only blocking finding is outside verify's writable scope | — | — |

## Remaining Issues

### High Priority

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | Release artifacts |
| **Location** | `CHANGELOG.md:23-26` |
| **Issue** | Merge commit `06f385a` left a stray, empty `## [0.21.4] - 2026-11-11` heading followed by `### Fixed` inside main's released `## [0.21.4] - 2026-11-12` section. These are leftovers of this branch's earlier version preparation (`771d1c9`). `git diff origin/main...HEAD -- CHANGELOG.md` shows them as additions to a released section |
| **Impact** | Delivery would publish a duplicate released-version heading on `main`, and the released 0.21.4 history would no longer match what was shipped |
| **Fix** | Delete those four lines (`## [0.21.4] - 2026-11-11`, blank, `### Fixed`, blank) so everything below `## [Unreleased]`'s #141 entry matches `origin/main` byte for byte. Keep the #141 entry under `## [Unreleased]` |
| **Reason Not Fixed** | The verify stage may only write `verification-report.md`, and the finalizer rejects any other change |

### Low Priority

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Low | Error Handling | `src/nmg_game_dev/unreal/import_asset.py:299` | When the import already made `SM_<Name>_PhysicsAsset`, `_ensure_rig_assets` returns without checking that it is assigned to the mesh. UE assigns the physics asset it creates during import, so this is safe today | Matches the spec (assignment is required only for a created asset) |
| Low | Testability | `src/nmg_game_dev/unreal/import_asset.py:284` | `_part_meshes` silently skips a datablock whose asset is not a Static Mesh. `_resolve_expected` then reports the part as missing, so the failure is still named | By design (documented in the helper comment) |

---

## Positive Observations

- One aggregated error names every missing part, which makes failure triage one step.
- The fake models UE 5.8's under-reporting as a knob (`reported_paths`), so the regression is reproducible without an editor.
- The composition with #145 (scale and rename before resolution) and #146 (candidate lists used as given) follows the design exactly, and their tests keep passing.

---

## Recommendations Summary

### Before PR (Must)
- [ ] Remove the stray `## [0.21.4] - 2026-11-11` / `### Fixed` lines from `CHANGELOG.md` (lines 23 to 26) and re-run the full gate.

### Short Term (Should)
- [ ] None

### Long Term (Could)
- [ ] Consider asserting the physics-asset assignment even when the import created it.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `src/nmg_game_dev/unreal/import_asset.py` | 2 (low) | Folder resolution and rig guarantee |
| `tests/unit/fake_unreal.py` | 0 | Scenario knobs and `run_import_code` |
| `tests/unit/test_unreal_import.py` | 0 | 10 #141 tests |
| `CHANGELOG.md` | 1 (high) | Merge residue in released 0.21.4 section |

---

## Recommendation

**Needs fixes**

The #141 implementation meets every acceptance criterion, and all applicable gates pass at `06f385a`. Fix the one-hunk `CHANGELOG.md` merge residue, then re-verify, before delivery.
