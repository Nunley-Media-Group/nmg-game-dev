# Verification Report: import_ue fails multi-part static imports because UE 5.8 reports only the first mesh on the import task

**Date**: 2026-11-11
**Issue**: #141
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Implementation verification against spec
**Verification head**: 771d1c9235cca37d716a9454da8d88bf1e0223fc

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
**Total Issues**: 3 (all low severity, none blocking)

The fix replaces the generated UE-side code's reliance on `AssetImportTask.imported_object_paths` with name-based resolution in the destination folder (`_resolve_expected`). It also adds a Desktop rig guarantee (`_ensure_rig_assets`) that requires the skeleton and creates, moves, assigns, and saves a missing physics asset. #145's multi-part scale and rename steps now run on parts found by datablock name before resolution, and #146's candidate lists are used unchanged. Every acceptance criterion has executed-code coverage against the in-memory fake `unreal` module, and all 10 applicable registered gates passed at the verification head.

---

## Issue Scope

- Active issue: #141
- Spec: `specs/141-fix-import-ue-failing-multi-part-static-imports-because-ue-5-8-reports-only-the-first-mesh-on-the-import-task`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC9]; FR [FR1–FR8]; tasks [T001, T002, T003]; scenarios [SCN001–SCN009]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":141,"specPath":"specs/141-fix-import-ue-failing-multi-part-static-imports-because-ue-5-8-reports-only-the-first-mesh-on-the-import-task","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8"],"tasks":["T001","T002","T003"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 141 --base main --controller-run-id 632f44e9-26c8-4deb-bf1a-f85b81cbeb13`
- Artifact: `.nmg-sdlc/verification/141.json`
- Identity: head `771d1c9235cca37d716a9454da8d88bf1e0223fc`, tree clean, steering `sha256:119992c8…96a9`, spec `sha256:8549d50b…97c5`
- Coverage: declared 11, recorded 11, complete `true`; missing/duplicate/unknown none
- Ceiling: none

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Multi-part static import returns every part | Pass | `_import_meshes` → `_resolve_expected(unreal.StaticMesh)` in `src/nmg_game_dev/unreal/import_asset.py`; `test_a_multi_part_static_import_returns_every_part` |
| AC2 | Expected meshes resolved from the destination folder by candidate name and class; others ignored | Pass | `_resolve_expected` uses `does_asset_exist` + `load_asset` + `isinstance` and never reads `imported_object_paths`; `test_expected_meshes_are_resolved_by_name_and_an_unrelated_mesh_is_ignored` |
| AC3 | Rigged Desktop import guarantees skeleton and physics asset | Pass | `_ensure_rig_assets`; `test_a_rigged_desktop_import_creates_the_missing_physics_asset`, `test_a_created_physics_asset_is_moved_into_the_destination_folder`, `test_a_rigged_desktop_import_without_a_skeleton_fails_naming_it` |
| AC4 | Rigged Mobile import reuses Desktop skeleton and physics asset, imports LOD1/LOD2 | Pass | `_skeletal_options(desktop=False)` loads the Desktop rig; `test_a_rigged_mobile_import_reuses_the_desktop_skeleton_and_physics_asset` asserts options and `import_lod` levels 1 and 2 |
| AC5 | Re-import reports the new geometry | Pass | Resolution after `import_asset_tasks` with `replace_existing`; `test_a_reimport_reports_the_new_bounds_and_passes_the_pivot_check` |
| AC6 | Every missing part is named in `import_ue.failed` | Pass | `missing` list joined into one `RuntimeError`; `test_two_missing_parts_fail_the_import_and_name_both` |
| AC7 | Two-part regression with an under-reporting task | Pass | `test_a_two_part_static_import_returns_both_parts_when_the_task_lists_only_the_first` (`reported_paths = _only_first_mesh`) |
| AC8 | Single-part behaviour preserved | Pass | Existing `test_texture_settings_material_binding_and_result_keys_are_unchanged` and the pivot-check tests still pass (65/65 in the file) |
| AC9 | Interchange cvar is not offered | Pass | `test_no_shipped_file_offers_the_interchange_cvar_as_a_workaround`; independent `grep -rl` over `src skills docs scripts templates` found no match |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `_imported_assets` removed; `_import_fbx` no longer returns the task |
| FR2 | Pass | Only `PARAMS["expected_meshes"]` names are resolved, bound, and reported |
| FR3 | Pass | `_ensure_rig_assets` (create, rename into `dest`, assign, save both, re-check) |
| FR4 | Pass | Re-import test |
| FR5 | Pass | Missing-parts test |
| FR6 | Pass | Cvar scan test and grep |
| FR7 | Pass | `NMG_RESULT` keys, error codes, texture import, material binding, Mobile LOD import, and `check_pivots` unchanged; #145/#146 tests pass |
| FR8 | Pass | `tests/unit/fake_unreal.py` extended (`reported_paths`, `skeleton_on_import`, `physics_folder`, `create_physics_asset`, `import_lod`, `run_import_code`) |

### BDD Scenario Mapping

| Scenario | Test |
|----------|------|
| SCN001 | `test_a_multi_part_static_import_returns_every_part` |
| SCN002 | `test_expected_meshes_are_resolved_by_name_and_an_unrelated_mesh_is_ignored` |
| SCN003 | `test_a_rigged_desktop_import_creates_the_missing_physics_asset` |
| SCN004 | `test_a_rigged_mobile_import_reuses_the_desktop_skeleton_and_physics_asset` |
| SCN005 | `test_a_reimport_reports_the_new_bounds_and_passes_the_pivot_check` |
| SCN006 | `test_two_missing_parts_fail_the_import_and_name_both` |
| SCN007 | `test_a_two_part_static_import_returns_both_parts_when_the_task_lists_only_the_first` |
| SCN008 | `test_texture_settings_material_binding_and_result_keys_are_unchanged` (existing baseline) |
| SCN009 | `test_no_shipped_file_offers_the_interchange_cvar_as_a_workaround` |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Resolve expected meshes from the folder and guarantee rig assets | Complete | `_resolve_expected`, `_part_meshes`, `_ensure_rig_assets`; module docstring updated; `_check_expected` removed |
| T002 | Extend the shared fake `unreal` module | Complete | Extends #145's fake, keeping its existing helpers; no real `unreal`, socket, or process |
| T003 | Executed-code regression tests | Complete | 11 new tests plus one updated rigged-import assertion |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | `_resolve_expected`, `_part_meshes`, and `_ensure_rig_assets` each do one job; `_import_skeletal` now also triggers the rig guarantee, which is acceptable |
| Open/Closed | 4 | Candidate names still come only from `_expected_mesh_candidates` (#146) |
| Liskov Substitution | 5 | Fake satisfies `UnrealPythonClient` unchanged |
| Interface Segregation | 5 | Host API (`build_import_code`, `parse_nmg_result`, `check_pivots`, `import_variant`) unchanged |
| Dependency Inversion | 4 | Generated code depends on `PARAMS` and the `unreal` module only |

### Layer Separation

The change stays inside `_IMPORT_TEMPLATE` in `src/nmg_game_dev/unreal/`, the step-implementation layer. The pipeline (`src/nmg_game_dev/pipeline/engine.py`) is untouched. No editor-only logic leaks into the host side.

### Dependency Flow

Unchanged: pipeline → `unreal.import_variant` → Unreal MCP client → generated code.

---

## Security Assessment

- [x] Authentication: N/A (no external services)
- [x] Authorization: N/A
- [x] Input validation: asset paths are built from `PARAMS` produced host-side from the snapshot; no new inputs
- [x] Injection prevention: no new string-to-code paths; `PARAMS` serialisation is unchanged
- [x] Data protection: no credentials or secrets touched

## Performance Assessment

- [x] Async patterns: synchronous after `import_asset_tasks`, per spec (no polling)
- [x] Caching: N/A
- [x] Resource management: at most one `does_asset_exist` and `load_asset` per candidate; negligible next to the FBX import
- [x] Query optimisation: N/A

## Testability Assessment

The fake now models the UE 5.8 under-reporting directly (`reported_paths`), along with skeleton and physics-asset creation. Tests run the real generated code without a live editor, as `feedback_no_live_editors_in_sdlc` requires.

## Error Handling Assessment

- Missing parts produce one aggregated error naming every part (AC6).
- Missing skeleton, `create_physics_asset` returning `None`, and a physics asset still missing after the move each raise a specific `RuntimeError` that names the path. `import_variant` maps each one to `import_ue.failed`.
- The return value of `rename_asset` is not checked directly, but the existence re-check right after it catches a failed move.

---

## Test Results

| Command | Result |
|---------|--------|
| `uv run pytest tests/unit/test_unreal_import.py -q` | 65 passed |
| `repository.tests` (`uv run pytest tests/unit tests/bdd -q`) | 1048 passed, 9 skipped |

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | 1048 passed, 9 skipped in 100.41s |
| `repository.lint` | Pass | `ruff check .`: All checks passed |
| `repository.format` | Pass | 316 files already formatted |
| `repository.types` | Pass | mypy: no issues in 202 source files |
| `gate-blender-headless` | Pass | 211 passed |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against UE 5.8 |
| `gate-mcp-schema` | Pass | MCP tools match tools.json |
| `gate-shellcheck` | Pass | exit 0 |
| `gate-ship-smoke` | Not applicable | no matching paths changed |
| `plugin.validate` | Pass | Validation passed (with warnings) |
| `plugin.session-smoke` | Pass | plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable passed, 0 failed, 0 incomplete (1 not applicable)

Note: `--base main` uses the local `main` ref (41c5b31), which is behind `origin/main`. More paths therefore counted as changed, and more gates applied than the #141 diff alone needs. Every one of them passed.

---

## Fixes Applied

| Severity | Category | Location | Issue | Fix | Routing |
|----------|----------|----------|-------|-----|---------|
| — | — | — | No fixes were needed | — | — |

## Remaining Issues

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Low | Correctness (design trade-off) | `import_asset.py` `_resolve_expected` | A stale asset left in `dest` by an earlier import can satisfy a part that this import did not create. | This is inherent to the folder-resolution approach the spec selected. Expected names come from the same export, and `check_pivots` compares bounds against the snapshot, so a stale part would only slip through if its bounds still matched. |
| Low | Live-editor evidence | `_ensure_rig_assets` | `SkeletalMeshEditorSubsystem.create_physics_asset` and its return path are proven only against the fake. | Project policy forbids using the live editor during SDLC work. The design cites ghost1's use of the same call. Run the E2E pipeline by hand before release. |
| Info | Error handling | `_ensure_rig_assets` | The return value of `rename_asset` is ignored. | The existence re-check right after it already fails with a clear message. |

## Recommendation

Ready for PR.
