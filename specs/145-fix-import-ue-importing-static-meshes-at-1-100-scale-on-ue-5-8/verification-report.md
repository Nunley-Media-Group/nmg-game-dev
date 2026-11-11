# Verification Report: import_ue imports static meshes at 1/100 scale on UE 5.8

**Date**: 2026-11-11
**Issue**: #145
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Implementation verification against spec (defect fix), re-run after merging `origin/main` into the issue branch
**Verification head**: 7cfe44978acad4b62cd4018a18c2990901967750

---

## Executive Summary

This is a fresh verification at the merge commit `7cfe449` ("chore: merge origin/main into #145 branch"). The merge brought in main's #140 variants changes (`variants_core/cleanup.py`, `meshes.py`, `mobile.py`) and approved specs for other issues. It did not change any file in this fix's scope. Against `origin/main`, the branch diff is still the #145 change only: `import_asset.py`, the snapshot key in `contract_core/validate.py`, a mypy override, the CHANGELOG entry under `[Unreleased]`, and tests.

The fix follows the approved design:

- A single-part static asset bakes the node transform (`transform_vertex_to_absolute = not PARAMS["multi_part"]`).
- A multi-part asset keeps its part pivots. `build_scale3d` 100 is written on every LOD on every run, and each mesh is renamed from its datablock name to its part's export name. An existing asset at that name is consolidated into the new mesh first.
- The skeletal path is untouched.

All eight acceptance criteria map to code and to passing tests. Every applicable registered gate passed at this head with the merged main code, including `gate-blender-headless` (195 passed), `gate-ue-compile` and `plugin.session-smoke`.

I reproduced the defect again by running the new tests against the pre-fix `import_asset.py` from `origin/main`: 19 tests fail (13 unit and 6 BDD, AC1 and AC4 among them). All of them pass with the fix.

One Medium error-handling finding carries over from the earlier verification: the generated UE Python ignores the boolean results of `EditorAssetLibrary.rename_asset` and `consolidate_assets`. It does not fail an acceptance criterion and is recorded as a follow-up.

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 3 |
| **Overall** | 4.3 |

### Implementation Status: Pass
**Verification type**: defect fix
**Total Issues**: 3 (0 Critical, 0 High, 1 Medium, 2 Low)

---

## Issue Scope

- Active issue: #145
- Spec: `specs/145-fix-import-ue-importing-static-meshes-at-1-100-scale-on-ue-5-8`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8]; FR [FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9]; tasks [T001, T002, T003, T004, T005]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005, SCN006, SCN007, SCN008]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":145,"specPath":"specs/145-fix-import-ue-importing-static-meshes-at-1-100-scale-on-ue-5-8","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9"],"tasks":["T001","T002","T003","T004","T005"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/145.json` (from `sdlc-verify-steering.mjs --base main --controller-run-id 95c2a036-76e0-43ac-aa78-0569ebc60388`)
- Identity: head `7cfe44978acad4b62cd4018a18c2990901967750`, tree clean, spec `sha256:d440451d…`, steering `sha256:119992c8…`
- Coverage: declared 11, recorded 11, complete `true`; no missing, duplicate or unknown ids
- Ceiling: none
- Note: the local `main` ref (`41c5b31`) is behind `origin/main`, so the runner diffed 107 changed paths. Applicability is therefore a superset of the issue's own change. Every gate it made applicable passed.

---

## Acceptance Criteria Verification

### Reproduction check (defect path)

| Check | Pre-fix (`origin/main:src/nmg_game_dev/unreal/import_asset.py`) | With fix (`7cfe449`) |
|-------|-------------------------------------------------------------------|----------------------|
| `tests/unit/test_unreal_import.py` + `tests/bdd/steps/test_import_ue_static_scale.py` | 19 failed, 32 passed. Multi-part bounds at 1/100, `no static mesh for snapshot part: SM_Crate_Lid`, and a stale reimport | 51 passed (inside `repository.tests`: 991 passed, 9 skipped) |

Every `@regression` scenario (SCN001–SCN005) fails before the fix and passes after it. SCN006 (rigged path unchanged) and SCN007 (e2e collection) pass in both runs, as expected for "unchanged" and "collected and skipped" contracts.

### Acceptance criteria

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Static meshes import at the authored size | Pass | `src/nmg_game_dev/unreal/import_asset.py`: `_static_options` (`transform_vertex_to_absolute = not PARAMS["multi_part"]`) and `_set_build_scale` (per-LOD `build_scale3d` 100, then save). Tests: `test_single_part_static_mesh_imports_at_the_authored_size[desktop,mobile]`, `test_multi_part_static_meshes_import_at_the_authored_size[desktop,mobile]`, SCN001 |
| AC2 | Part pivots preserved on a multi-part asset | Pass | A multi-part asset keeps `transform_vertex_to_absolute` and `bake_pivot_in_vertex` off, and build scale scales about the mesh origin. Tests: `test_each_part_keeps_its_own_pivot_on_a_multi_part_asset`, SCN002 |
| AC3 | Static meshes named after part objects | Pass | `contract_core/validate.py` `object_snapshot` adds `"mesh"`. `_mesh_names` builds the datablock-to-export map and leaves out shared datablocks. `_rename_to_parts` matches on the UE-sanitized name. Tests: `test_a_static_mesh_is_named_after_its_part_object_not_its_datablock[desktop,mobile]`, the snapshot test in `tests/blender/test_finalize_core.py` (in `gate-blender-headless`), SCN003 |
| AC4 | A reimport reports the new geometry | Pass | The build scale is written on every run and always rebuilds. An existing asset at the export name is consolidated into the new mesh before the rename. Tests: `test_a_reimport_reports_the_new_bounds_over_a_mesh_at_one_hundredth_scale`, SCN004. Live-UE failure reporting is subject to the Medium finding below |
| AC5 | Desktop and Mobile both import correctly | Pass | The AC1 and AC3 tests run for both variants, and `_export_name` strips `_Mobile`. SCN005 drives both variants |
| AC6 | Rigged imports unchanged | Pass | `_run` runs both new steps only when `PARAMS["multi_part"] and not PARAMS["rigged"]`. The diff does not change `_import_skeletal` or `_skeletal_options`. Tests: `test_a_rigged_import_keeps_its_size_and_sets_no_build_scale_or_name`, SCN006 |
| AC7 | An e2e test covers a multi-part static asset | Pass | `tests/e2e/fixtures/build_multipart_fixture.py` (`build_gantry()`). `tests/blender/test_e2e_fixture_builder.py` passes in `gate-blender-headless`. `test_finalize_multi_part_static_asset_keeps_size_pivots_and_names` is in `tests/e2e/test_finalize_e2e.py`. Without `--runslow`: `2 skipped` ("Pass --runslow to run end-to-end tests"). The `--runslow` run is opt-in and was not run, as T005 requires |
| AC8 | Other import behavior preserved | Pass | The diff does not change texture settings, `_instance`, `_bind_materials`, the `RESULT` keys, `check_pivots`, or `PIVOT_TOLERANCE_CM = 0.01`. Tests: `test_texture_settings_material_binding_and_result_keys_are_unchanged`, `test_a_missing_master_material_fails_with_the_import_ue_failed_code`, the existing pivot and parse tests, SCN008 |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | The node transform is baked for a single-part asset, and build scale 100 is applied to a multi-part asset |
| FR2 | Pass | A multi-part asset keeps the vertex transform and the pivot bake off |
| FR3 | Pass | `_mesh_names` + `_rename_to_parts` |
| FR4 | Pass | The build-scale write is absolute and runs every time; the existing asset is consolidated before the rename |
| FR5 | Pass | The module never mentions `Interchange.FeatureFlags`; `test_build_import_code_scales_and_renames_static_parts_and_never_sets_feature_flags` asserts this |
| FR6 | Pass | The exporter is not changed, and the skeletal path is unchanged |
| FR7 | Pass | The tolerance, the `NMG_RESULT` keys and the error codes are unchanged |
| FR8 | Pass | An opt-in Gantry e2e test runs on a generated fixture |
| FR9 | Pass | Unit tests run the generated code against `tests/unit/fake_unreal.py` |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Record the mesh datablock name in the snapshot | Complete | One line added to `validate.py`; the headless test passes |
| T002 | Correct static import size, bounds and naming | Complete | `import_asset.py`. The docstring describes the single-part/multi-part split and cites the ghost1 `sitecustomize.py` workaround |
| T003 | Run the generated code against an in-memory `unreal` fake | Complete | `fake_unreal.py`, `test_unreal_import.py`. 13 unit tests fail against the pre-fix source (AC1 and AC4 among them) |
| T004 | BDD scenarios for the corrected static import | Complete | `import_ue_static_scale.feature` (8 scenarios) and step definitions; they pass under `repository.tests` |
| T005 | Opt-in multi-part e2e test with a generated fixture | Complete | Builder, headless builder test and slow e2e test; the crate test is unchanged |

---

## Architecture Assessment

### Blast radius (defect path)

- **Shared callers**: `import_variant` is called by the finalize pipeline's `import_ue` step only. The new steps run only for non-rigged multi-part imports.
- **Public contract**: no signature, return-type or error-code change. `build_import_code` adds two `PARAMS` keys that only the generated template reads. The contract snapshot gains the additive `mesh` key. `reimport.py` reads snapshot fields by name, and the `import_ue` cache key does not include the snapshot.
- **Silent data changes**: an existing asset at a part's export name is consolidated into the new import, so references now point to the new mesh. This is the intended AC4 behavior.
- **Interaction with the merged #140 changes**: #140 changes Mobile mesh cleanup and re-seats the Mobile root. The pivot check uses each part's local bounds, so the re-seat does not affect it. With both changes merged, `gate-blender-headless` and `repository.tests` pass.
- **Minimal change**: outside the fix there is only the `pyproject.toml` mypy override for `bpy`/`bmesh`/`mathutils`, which the new Blender-run fixture builder needs. It is in scope.

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | `_set_build_scale` and `_rename_to_parts` are separate steps. `_variant_meshes` holds the snapshot filtering that `_expected_mesh_candidates`, `_multi_part` and `_mesh_names` share |
| Open/Closed | 4 | `PARAMS` drives the new behavior; the skeletal path is not touched |
| Liskov Substitution | 5 | The fake implements the subset of the `unreal` API that the template uses |
| Interface Segregation | 4 | `PARAMS` gains two keys, and only the static path reads them |
| Dependency Inversion | 4 | The host-side code makes the decisions, and the UE-side template only applies them |

### Layer Separation

The change stays inside the step implementation (`src/nmg_game_dev/unreal/`) and the Blender contract core, as the structure steering layer table requires. No skill, MCP server or pipeline composition changed.

---

## Security Assessment

- [x] Authentication / authorization: N/A
- [x] Input validation: snapshot names reach the UE code only through the double-`json.dumps` `PARAMS` literal
- [x] Injection prevention: no names are interpolated into Python source
- [x] Data protection: no credentials or external services are involved

---

## Performance Assessment

- [x] Caching: unchanged
- [x] Resource management: one extra rebuild per LOD per static mesh for multi-part assets, bounded by the part count
- [ ] Redundant work: each multi-part mesh is saved in `_set_build_scale` and again in `_bind_materials` (Low)

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001, @regression) | Yes | Yes |
| AC2 | Yes (SCN002, @regression) | Yes | Yes |
| AC3 | Yes (SCN003, @regression) | Yes | Yes |
| AC4 | Yes (SCN004, @regression) | Yes | Yes |
| AC5 | Yes (SCN005, @regression) | Yes | Yes |
| AC6 | Yes (SCN006) | Yes | Yes |
| AC7 | Yes (SCN007) | Yes | Yes (collected and skipped; the live run is opt-in) |
| AC8 | Yes (SCN008) | Yes | Yes |

### Coverage Summary

- Full `repository.tests`: 991 passed, 9 skipped
- Headless Blender (`gate-blender-headless`): 195 passed, including the snapshot, fixture-builder and merged #140 variant tests
- E2E: `uv run pytest tests/e2e/test_finalize_e2e.py -q`: 2 skipped (needs `--runslow`)

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable: the change touches no nmg-sdlc `workflows/` or `agents/`. `plugin.session-smoke` checked the plugin load and the MCP connection |
| **Recommendation** | Run `pytest tests/e2e --runslow` against live Blender and UE 5.8 before a release, as tech steering directs |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 991 passed, 9 skipped |
| `repository.lint` | Pass | `ruff check .`: All checks passed |
| `repository.format` | Pass | `ruff format --check .`: 314 files already formatted |
| `repository.types` | Pass | `mypy src tests`: no issues found in 200 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 195 passed |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8` (Result: Succeeded) |
| `gate-mcp-schema` | Not applicable | No change under `mcp-servers/**` |
| `gate-shellcheck` | Not applicable | No change under `scripts/**.sh` |
| `gate-ship-smoke` | Not applicable | No ship path changed |
| `plugin.validate` | Pass | `claude plugin validate .`: passed (ICON_MISSING warning only) |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 8/8 applicable gates passed, 0 failed, 0 incomplete (3 not applicable)

---

## Fixes Applied

None. The verify publication scope allows writing only this report, so findings are recorded as remaining issues.

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Medium Priority

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Error Handling |
| **Location** | `src/nmg_game_dev/unreal/import_asset.py` (`_IMPORT_TEMPLATE` `_rename_to_parts`) |
| **Issue** | The template ignores the boolean results of `EditorAssetLibrary.consolidate_assets` and `rename_asset`. In UE these calls return `False` and log an error instead of raising. If a rename fails in a live editor (for example, because a redirector was left at the export name after a consolidate), the result records `dest/<export>` as the mesh path while the mesh stays at its datablock-named path. `tests/unit/fake_unreal.py` raises on these failures, so the unit tests cannot see the difference. |
| **Impact** | A failed rename during a live reimport (AC4) could report success with a wrong asset path. This can only be observed in a live UE 5.8 reimport. |
| **Reason Not Fixed** | Verify may write only the report. Suggested follow-up: raise `RuntimeError` when either call returns `False` (so the failure maps to `import_ue.failed`), make the fake return `False` instead of raising, and exercise a reimport in the `--runslow` e2e run. |

### Low Priority

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Low | Performance | `src/nmg_game_dev/unreal/import_asset.py` (`_set_build_scale`, `_bind_materials`) | Each multi-part static mesh is saved twice per import | Outside verify scope; harmless |
| Low | Testing | `tests/e2e/test_finalize_e2e.py` | The opt-in e2e test covers one finalize run, not a reimport, so AC4 is shown only against the fake | The spec scopes AC7 to a single run; verify must not drive the live editors |

---

## Recommendations Summary

### Before PR (Must)
- [ ] None

### Short Term (Should)
- [ ] Check the `rename_asset` / `consolidate_assets` return values and make the fake return `False` on failure (Medium)

### Long Term (Could)
- [ ] Add a reimport pass to the `--runslow` Gantry e2e test
- [ ] Drop the redundant save in `_set_build_scale` or `_bind_materials`

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `src/nmg_game_dev/unreal/import_asset.py` | 2 | Medium: unchecked return values; Low: double save |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 0 | Additive snapshot key |
| `pyproject.toml` | 0 | mypy override for Blender modules |
| `tests/unit/fake_unreal.py` | 0 | Raises where UE returns `False` (see the Medium finding) |
| `tests/unit/test_unreal_import.py` | 0 | |
| `tests/bdd/features/import_ue_static_scale.feature`, `tests/bdd/steps/test_import_ue_static_scale.py` | 0 | |
| `tests/blender/test_finalize_core.py`, `tests/blender/test_e2e_fixture_builder.py` | 0 | |
| `tests/e2e/fixtures/build_multipart_fixture.py`, `tests/e2e/test_finalize_e2e.py` | 1 | Low: no reimport pass |

---

## Recommendation

**Ready for PR**

Every acceptance criterion, functional requirement and task is met at `7cfe44978acad4b62cd4018a18c2990901967750`. All applicable registered gates pass with main's changes merged, and the regression tests fail without the fix. The Medium error-handling finding is a hardening follow-up, not a spec gap.
