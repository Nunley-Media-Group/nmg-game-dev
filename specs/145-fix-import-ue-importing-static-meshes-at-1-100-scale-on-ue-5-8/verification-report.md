# Verification Report: import_ue imports static meshes at 1/100 scale on UE 5.8

**Date**: 2026-11-11
**Issue**: #145
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Implementation verification against spec
**Verification head**: aaa04835f07754558695a98038f81d76e6da3750

---

## Executive Summary

The fix follows the approved design. A single-part static asset bakes the node transform (`transform_vertex_to_absolute = not PARAMS["multi_part"]`). A multi-part asset keeps its pivots, gets `build_scale3d` 100 written on every LOD on every run, and is renamed from datablock names to part export names, with any existing asset at that name consolidated into the new one first. The skeletal path is untouched. All eight acceptance criteria are mapped to code and to passing tests. Every applicable registered gate passed at the verification head, including `gate-blender-headless`, `gate-ue-compile` and `plugin.session-smoke`. The new unit tests fail against the pre-fix source (13 failures, AC1 and AC4 among them) and pass against the fix.

One Medium error-handling finding remains: the generated UE Python ignores the boolean results of `EditorAssetLibrary.rename_asset` and `consolidate_assets`. The fake raises where real UE returns `False`, so a failed rename in a live editor would report the target path without an error. This does not fail an acceptance criterion, which the spec verifies against the in-memory fake. It is recorded below as a follow-up because verify may only write this report.

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

- Artifact: `.nmg-sdlc/verification/145.json` (from `sdlc-verify-steering.mjs --base main --controller-run-id 882f4c08-f2e2-45e1-a5c1-ca4e9cb7493e`)
- Identity: head `aaa04835f07754558695a98038f81d76e6da3750`, tree clean, spec `sha256:d440451d…`, steering `sha256:119992c8…`
- Coverage: declared 11, recorded 11, complete `true`; no missing, duplicate or unknown ids
- Ceiling: none

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Static meshes import at the authored size | Pass | `src/nmg_game_dev/unreal/import_asset.py` `_static_options` (`transform_vertex_to_absolute = not PARAMS["multi_part"]`) and `_set_build_scale` (per-LOD `build_scale3d` 100, then save). Tests: `test_single_part_static_mesh_imports_at_the_authored_size[desktop,mobile]`, `test_multi_part_static_meshes_import_at_the_authored_size[desktop,mobile]`, SCN001 |
| AC2 | Part pivots preserved on a multi-part asset | Pass | Multi-part keeps `transform_vertex_to_absolute` and `bake_pivot_in_vertex` off; build scale scales about the mesh origin. Test: `test_each_part_keeps_its_own_pivot_on_a_multi_part_asset`, SCN002 |
| AC3 | Static meshes named after part objects | Pass | `contract_core/validate.py` `object_snapshot` adds `"mesh"`; `_mesh_names` builds the datablock-to-export map (shared datablocks excluded); `_rename_to_parts` renames using the UE-sanitized name. Tests: `test_a_static_mesh_is_named_after_its_part_object_not_its_datablock[desktop,mobile]`, `test_object_snapshot_records_the_mesh_datablock_name` (headless Blender), SCN003 |
| AC4 | A reimport reports the new geometry | Pass | The build scale is written on every run and always rebuilds; an existing asset at the export name is consolidated into the new mesh before the rename. Test: `test_a_reimport_reports_the_new_bounds_over_a_mesh_at_one_hundredth_scale` (pre-seeded 1/100-scale `SM_Crate_Lid` plus a datablock-named duplicate), SCN004. Live-UE behavior is subject to the Medium finding below |
| AC5 | Desktop and Mobile both import correctly | Pass | AC1 and AC3 tests are parametrized over both variants; `_export_name` strips `_Mobile`. SCN005 drives both variants |
| AC6 | Rigged imports unchanged | Pass | `_run` gates both new steps on `PARAMS["multi_part"] and not PARAMS["rigged"]`; `_import_skeletal` and `_skeletal_options` are unchanged in the diff. Test: `test_a_rigged_import_keeps_its_size_and_sets_no_build_scale_or_name` (no build writes, no redirects), SCN006 |
| AC7 | An e2e test covers a multi-part static asset | Pass | `tests/e2e/fixtures/build_multipart_fixture.py` (`build_gantry()`: 2 m root, two off-origin children, `SM_Gantry_Trim.001` datablock); `tests/blender/test_e2e_fixture_builder.py` (5 tests, passed in `gate-blender-headless`); `test_finalize_multi_part_static_asset_keeps_size_pivots_and_names` in `tests/e2e/test_finalize_e2e.py`. Without `--runslow`: `2 skipped` ("Pass --runslow to run end-to-end tests"). The `--runslow` run is opt-in and was not run, as T005 requires |
| AC8 | Other import behavior preserved | Pass | Texture settings, `_instance`, `_bind_materials`, `RESULT` keys, `check_pivots` and `PIVOT_TOLERANCE_CM = 0.01` are unchanged in the diff. Tests: `test_texture_settings_material_binding_and_result_keys_are_unchanged`, `test_a_missing_master_material_fails_with_the_import_ue_failed_code`, the existing pivot and parse tests, SCN008 |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | Single-part node-transform bake; multi-part build scale 100 |
| FR2 | Pass | Multi-part keeps vertex transform and pivot bake off |
| FR3 | Pass | `_mesh_names` + `_rename_to_parts` |
| FR4 | Pass | Absolute build-scale write on every run; consolidate before rename |
| FR5 | Pass | No `Interchange.FeatureFlags` in the module; asserted by `test_build_import_code_scales_and_renames_static_parts_and_never_sets_feature_flags` |
| FR6 | Pass | Exporter not changed; skeletal path unchanged |
| FR7 | Pass | Tolerance, `NMG_RESULT` keys and error codes unchanged |
| FR8 | Pass | Opt-in Gantry e2e test with a generated fixture |
| FR9 | Pass | Unit tests run the generated code against `tests/unit/fake_unreal.py` |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Record the mesh datablock name in the snapshot | Complete | `validate.py` +1 line; headless test passes |
| T002 | Correct static import size, bounds and naming | Complete | `import_asset.py`; docstring describes the split and cites the ghost1 `sitecustomize.py` workaround |
| T003 | Run the generated code against an in-memory `unreal` fake | Complete | `fake_unreal.py` (598 lines), `test_unreal_import.py`. Against the pre-fix source, 13 tests fail, AC1 and AC4 among them; all pass with the fix |
| T004 | BDD scenarios for the corrected static import | Complete | `import_ue_static_scale.feature` (8 scenarios) and step definitions; pass under `repository.tests` |
| T005 | Opt-in multi-part e2e test with a generated fixture | Complete | Builder, headless builder test, slow e2e test; crate test unchanged |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | `_set_build_scale` and `_rename_to_parts` are separate steps. `_variant_meshes` factors out the snapshot filtering that `_expected_mesh_candidates`, `_multi_part` and `_mesh_names` share |
| Open/Closed | 4 | The new behavior is driven by `PARAMS`; the skeletal path is not touched |
| Liskov Substitution | 5 | N/A beyond the fake honoring the subset of the `unreal` API used |
| Interface Segregation | 4 | `PARAMS` gains two keys, both read only by the static path |
| Dependency Inversion | 4 | Host-side code computes the decisions; the UE-side template only applies them |

### Layer Separation

The change stays inside the step implementation (`src/nmg_game_dev/unreal/`) and the Blender contract core. No skill, MCP server or pipeline composition changed, which matches the layer table in structure steering.

### Dependency Flow

Snapshot (Blender) to `build_import_code` (host) to generated UE Python. The added snapshot key is additive. `reimport.py` reads snapshot fields by name, and the `import_ue` cache key does not include the snapshot.

---

## Security Assessment

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: snapshot names reach the UE code only through the double-`json.dumps` `PARAMS` literal, so no code injection is possible
- [x] Injection prevention: no string interpolation of names into Python source
- [x] Data protection: no credentials or external services involved

---

## Performance Assessment

- [x] Async patterns: N/A (runs inside one editor Python call)
- [x] Caching: unchanged
- [x] Resource management: one extra rebuild per LOD per static mesh for multi-part assets; bounded by part count
- [ ] Redundant work: each multi-part mesh is saved in `_set_build_scale` and again in `_bind_materials` (Low)

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes | Yes |
| AC5 | Yes (SCN005) | Yes | Yes |
| AC6 | Yes (SCN006) | Yes | Yes |
| AC7 | Yes (SCN007) | Yes | Yes (collection and skip; live run opt-in) |
| AC8 | Yes (SCN008) | Yes | Yes |

### Coverage Summary

- Feature files: 8 scenarios in `tests/bdd/features/import_ue_static_scale.feature`
- Step definitions: implemented in `tests/bdd/steps/test_import_ue_static_scale.py`
- Unit + BDD for this change: 51 passed (`tests/unit/test_unreal_import.py` and the new BDD steps)
- Full `repository.tests`: 991 passed, 9 skipped
- Headless Blender (`gate-blender-headless`): 185 passed, including the new snapshot and fixture-builder tests
- E2E: the new slow test is collected and skipped without `--runslow`

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable: the change touches no nmg-sdlc `workflows/` or `agents/`. Plugin load and MCP connection were checked by `plugin.session-smoke` |
| **Recommendation** | Run `pytest tests/e2e --runslow` against live Blender and UE 5.8 before a release, as tech steering directs |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 991 passed, 9 skipped |
| `repository.lint` | Pass | `ruff check .`: All checks passed |
| `repository.format` | Pass | `ruff format --check .`: 313 files already formatted |
| `repository.types` | Pass | `mypy src tests`: no issues in 200 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 185 passed |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8` |
| `gate-mcp-schema` | Not applicable | No change under `mcp-servers/**` |
| `gate-shellcheck` | Not applicable | No change under `scripts/**.sh` |
| `gate-ship-smoke` | Not applicable | No ship path changed |
| `plugin.validate` | Pass | `claude plugin validate .`: validation passed (with warnings) |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 8/8 applicable gates passed, 0 failed, 0 incomplete (3 not applicable)

---

## Fixes Applied

None. The verify publication scope allows only this report, so findings are recorded as remaining issues.

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
| **Issue** | The template ignores the boolean results of `EditorAssetLibrary.consolidate_assets` and `rename_asset`. In UE these return `False` and log an error instead of raising. If a rename fails in a live editor (for example, a redirector left at the export name after a consolidate), the result records `dest/<export>` as the mesh path while the mesh stays at its datablock-named path. `_check_expected` and `_bind_materials` then key on the target name, so the run reports success. `tests/unit/fake_unreal.py` raises on these failures, so the unit tests cannot observe the difference. |
| **Impact** | A failed rename during a live reimport (AC4) could report success with a wrong asset path. It cannot be observed without a live UE 5.8 reimport. |
| **Reason Not Fixed** | Verify may write only the report. Suggested follow-up: raise `RuntimeError` when either call returns `False`, so the failure maps to `import_ue.failed`, and make the fake return `False` instead of raising. Exercise a reimport in the `--runslow` e2e run. |

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Performance |
| **Location** | `src/nmg_game_dev/unreal/import_asset.py` (`_set_build_scale`, `_bind_materials`) |
| **Issue** | Each multi-part static mesh is saved after the build-scale write and again after material binding. |
| **Impact** | One extra package write per part per import. |
| **Reason Not Fixed** | Out of verify scope; harmless. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `tests/e2e/test_finalize_e2e.py` |
| **Issue** | The opt-in e2e test covers one finalize run, not a reimport over existing assets, so AC4 is shown only against the fake. |
| **Impact** | Reimport behavior in a live editor is not covered by the e2e test. |
| **Reason Not Fixed** | The spec scopes AC7 to a single finalize run; verify must not drive the live editors. |

---

## Positive Observations

- The fake models the UE 5.8 Interchange behavior that caused the defect: metre values read as centimetres, bounds that stay stale until a rebuild, and datablock-named meshes. Running the generated code against it closes the gap where the old tests asserted only option strings.
- The tests were confirmed against the pre-fix source: 13 of them fail there.
- `_variant_meshes` removes duplicated snapshot filtering. `_mesh_names` handles shared datablocks and pre-#145 snapshots by leaving them out.
- The module docstring records why the ghost1 workaround's "only while 1.0" condition was dropped.

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
| `src/nmg_game_dev/unreal/import_asset.py` | 2 | Medium unchecked return values; Low double save |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 0 | Additive snapshot key |
| `tests/unit/fake_unreal.py` | 0 | Raises where UE returns `False` (see Medium) |
| `tests/unit/test_unreal_import.py` | 0 | |
| `tests/bdd/features/import_ue_static_scale.feature`, `tests/bdd/steps/test_import_ue_static_scale.py` | 0 | |
| `tests/blender/test_finalize_core.py`, `tests/blender/test_e2e_fixture_builder.py` | 0 | |
| `tests/e2e/fixtures/build_multipart_fixture.py`, `tests/e2e/test_finalize_e2e.py` | 1 | Low: no reimport pass |

---

## Recommendation

**Ready for PR**

Every acceptance criterion, functional requirement and task is met. All applicable registered gates pass at `aaa04835f07754558695a98038f81d76e6da3750`, and the regression tests are proven to fail without the fix. The Medium error-handling finding is a hardening follow-up, not a spec gap.
