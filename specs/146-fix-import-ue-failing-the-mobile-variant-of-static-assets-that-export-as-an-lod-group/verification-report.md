# Verification Report: import_ue fails the Mobile variant of static assets that export as an LOD group

**Date**: 2026-11-11
**Issue**: #146
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify worker)
**Scope**: Implementation verification against spec
**Verification head**: 3689c52792e4f98868b7543be80655d6339c1b12

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
**Total Issues**: 1 (Low, informational; no blocking findings)

The fix teaches the host side of `import_ue` that UE 5.8 Interchange imports a static Mobile LOD group as one Static Mesh `SM_<Name>`. A new `_lod_groups` helper finds the group from the snapshot. `_mesh_name_candidates` maps the `_LOD0` key to `SM_<Name>`. A shared `_skipped_lod` rule drops `_LOD1`/`_LOD2` entries for rigged assets and static LOD groups. The UE template now reports `lod_count` for every static mesh, and a new public `check_lod_counts` fails with `import_ue.failed` when the count differs or is missing. The export, the FBX import options, the rigged path and the error codes are unchanged. All 11 registered validations have results, and every applicable one passed at the verification head. This is a re-verification after `3689c52` merged `origin/main` (#184, the `start-unreal-mcp.sh` relaunch fix) into the branch. The merge did not change any #146 source, test or doc file.

---

## Issue Scope

- Active issue: #146
- Spec: `specs/146-fix-import-ue-failing-the-mobile-variant-of-static-assets-that-export-as-an-lod-group`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC9]; FR [FR1–FR11]; tasks [T001–T004]; scenarios [SCN001–SCN009]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":146,"specPath":"specs/146-fix-import-ue-failing-the-mobile-variant-of-static-assets-that-export-as-an-lod-group","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10","FR11"],"tasks":["T001","T002","T003","T004"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/146.json` (from `sdlc-verify-steering.mjs --base main --controller-run-id 00f2f050-3eb8-4315-bfc0-bffe058e627f`, generated 2026-11-11T23:19:45Z)
- Identity: head `3689c52792e4f98868b7543be80655d6339c1b12`, tree clean, spec `sha256:bd4c93cb…`, steering `sha256:119992c8…`
- Coverage: declared 11, recorded 11, complete `true`; missing, duplicate and unknown are empty
- Ceiling: `null`; no cap applies
- The local `main` ref lags `origin/main`, so the runner diffed 151 paths and treated more gates as applicable than the #146 diff against `origin/main` alone would. Every one of those extra gates ran and passed, so the evidence is a superset.
- First run at this head: `repository.tests` failed with 1 failed and 1037 passed. The failure was `tests/bdd/steps/test_scaffold.py::test_unreal_launcher_detaches`, a wall-clock assertion that the launcher returns in under 2.0 s. It measured 2.04 s while the host load average was 120 to 264, with six lanes running builds at once. The test covers main's `start-unreal-mcp.sh` and does not touch #146 code. Run alone, it passed 5 times out of 5, in 0.64 to 1.15 s. The full gate was then run again at the same head and passed everything (see the gates below). The artifact above is from that second run.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | A static Mobile LOD group imports as one Static Mesh with three LODs | Pass | `src/nmg_game_dev/unreal/import_asset.py` `_lod_groups`, `_skipped_lod`, `_mesh_name_candidates`, `_expected_mesh_candidates`. Tests: `test_static_lod_group_expects_one_static_mesh_named_after_its_empty` asserts expected meshes `[["SM_Crate","SM_Crate_LOD0","SM_Crate_Mobile","SM_Crate_Mobile_LOD0"]]`. `test_import_variant_accepts_a_static_lod_group_that_reports_three_lods` and `test_static_lod_group_imports_one_static_mesh_on_the_fake` check that the result holds only `SM_Crate`. |
| AC2 | The LOD count is verified against the snapshot | Pass | `check_lod_counts` raises `import_ue.failed` with the message `"{mesh} has {actual} LODs in Unreal; the snapshot has {n} LOD objects ({first}..{last})"`, where `actual` is `missing` when absent. `import_variant` calls it before `check_pivots`. Tests: `test_static_lod_group_fails_when_the_lod_count_differs_or_is_missing` (parametrized for 1 and missing) and `test_static_lod_group_fails_on_the_fake_when_the_mesh_lost_lods`. |
| AC3 | The LOD0 pivot is verified against the snapshot | Pass | `check_pivots` uses `_skipped_lod` with the groups, and `_matching_mesh` finds `SM_Crate` for `SM_Crate_Mobile_LOD0`. The tolerance stays `PIVOT_TOLERANCE_CM`. Test: `test_static_lod_group_pivot_is_checked_against_lod0_alone` covers the pass, and a mismatch raises `import_ue.pivot_mismatch` naming `SM_Crate_Mobile_LOD0`. |
| AC4 | The result reports the LOD count of a static mesh | Pass | The static branch of `_IMPORT_TEMPLATE` `_bind_materials` adds `"lod_count": mesh.get_num_lods()`. Tests: the generated code contains `get_num_lods()` and `"lod_count"`. On the fake, the LOD group reports 3 and `test_a_single_part_static_mesh_reports_one_lod` reports 1. |
| AC5 | Each LOD carries its own geometry and the asset's materials | Pass | The FBX options are unchanged, and the code has no `FeatureFlags` and no `Interchange` (existing assertion). On the fake, `world.imported_fbx == [SM_Crate.fbx]` (one import), `build_writes == []`, `static_mesh_paths() == [.../SM_Crate]`, and `M_Crate_Body` is bound to `MI_Crate_Body` through `set_material`. The shared template still contains the rigged `import_lod` and the multi-part `StaticMeshEditorSubsystem` code, so T003's "no such text" bullet is shown by behavior on the fake rather than by text absence. |
| AC6 | A reimport gives the same result | Pass | `test_static_lod_group_reimport_passes_the_lod_count_and_pivot_checks_again` asserts `first == second` and `task.replace_existing = True`. `test_a_repeated_static_lod_group_import_gives_the_same_result` covers the same on the fake world. |
| AC7 | Other imports are unchanged | Pass | The existing Desktop, multi-part and rigged tests in `tests/unit/test_unreal_import.py` pass without changes (55 passed). `test_check_lod_counts_passes_for_a_multi_part_mobile_with_no_lod_count` asserts one candidate list per part. `test_check_lod_counts_does_nothing_for_desktop_or_rigged_results` checks those variants. `_lod_groups` returns `{}` when rigged and when there is no `_LOD0` key. |
| AC8 | An end-to-end test covers a static Mobile import | Pass | `tests/e2e/test_finalize_e2e.py::test_finalize_static_mobile_lod_group_imports_as_one_static_mesh` is module-marked `slow`. It builds the Crate headless through `tests/e2e/fixtures/build_crate_fixture.py` (via `resolve_blender()`). It asserts the Mobile `SM_Crate` with 3 LODs, no `SM_Crate_LOD*` assets, `lod_triangles == lod_tris`, the material binding, and a second `import_variant`. `--runslow --collect-only -q` collected 3 tests, and the run without `--runslow` gave 3 skipped. Per the spec, it was not run against live editors. |
| AC9 | Unit tests cover the static Mobile LOD group | Pass | `uv run pytest tests/unit/test_unreal_import.py -q` gave 55 passed. The tests cover success, the count mismatch and missing count, the LOD0 pivot pass and mismatch, and the repeated import. |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Map a static LOD group to one Static Mesh and check its LOD count | Complete | The design named the helper `_mesh_names(key)`, but that name already belonged to the rename map, so it is `_mesh_name_candidates`. The behavior matches the design. `check_lod_counts` is exported in both `__all__` lists. |
| T002 | Document the static Mobile LOD group in Unreal | Complete | `docs/asset-contract.md` §5 has a new bullet. The module docstring and the NMG_RESULT schema were updated (FR11). |
| T003 | Unit regression coverage for the static Mobile LOD group | Complete | 12 new tests. `tests/unit/fake_unreal.py` gained `FbxNode.lods` and `FakeWorld.imported_fbx`. |
| T004 | End-to-end static Mobile import with a generated fixture | Complete | Opt-in only. Collection and skip were verified. |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Each helper does one job: `_snapshot_meshes` (filter), `_lod_groups` (detect), `_skipped_lod` (shared skip rule), `_mesh_name_candidates` (naming). `check_lod_counts` is separate from `check_pivots`. |
| Open/Closed | 5 | The LOD-group behavior is added by the new helpers. The rigged and multi-part branches are not edited, only routed through the shared skip rule. |
| Liskov Substitution | 5 | N/A beyond the `UnrealPythonClient` protocol, which is unchanged |
| Interface Segregation | 5 | `check_lod_counts(report, result)` mirrors `check_pivots`, and the NMG_RESULT change is additive |
| Dependency Inversion | 5 | The check is on the host side and depends on the injected client, which makes it unit-testable with the fake (as the design chose) |

### Layer Separation

The change stays in `src/nmg_game_dev/unreal/` (the UE import step implementation). It does not change the Blender export, the pipeline engine or any skill, which matches the layer responsibilities in structure steering.

### Dependency Flow

`engine.py` → `import_variant` → `check_lod_counts` / `check_pivots`. This adds no new imports and no new coupling.

---

## Security Assessment

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: `lod_count` is type-checked (an int that is not a bool) before comparison. A missing or malformed count fails closed.
- [x] Injection prevention: snapshot data reaches the UE code only through the existing JSON-encoded `PARAMS`, and no new string interpolation goes into code
- [x] Data protection: no secrets or credentials are touched

## Performance Assessment

- [x] Async patterns: N/A (synchronous host checks)
- [x] Caching: N/A
- [x] Resource management: no new I/O. `get_num_lods()` is one cheap UE call per static mesh.
- [x] Query optimization: `_lod_groups` is O(n) over the variant's snapshot entries. It is computed once per check, plus once inside `_variant_meshes` during code build, which is negligible.

## Error Handling Assessment

- The new failure reuses `_fail_import` (`import_ue.failed`, stage `import_ue`, the existing remediation), so the error codes are unchanged (FR6).
- The message names the mesh, the actual count (or `missing`) and the expected count with the key range, as AC2 requires.
- When no UE mesh is found for the group, the message names the export name (`SM_<Name>`) instead of crashing.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (unit tests named in the feature file header) | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes | Yes |
| AC5 | Yes (SCN005) | Yes | Yes |
| AC6 | Yes (SCN006) | Yes | Yes |
| AC7 | Yes (SCN007) | Yes | Yes |
| AC8 | Yes (SCN008) | Yes (e2e, opt-in) | Collected and skipped as specified |
| AC9 | Yes (SCN009) | Yes | Yes |

### Coverage Summary

- Feature files: 9 scenarios in `specs/146-…/feature.gherkin`. Its header maps them to `tests/unit/test_unreal_import.py` and `tests/e2e/test_finalize_e2e.py`.
- Step definitions: implemented as unit tests and the e2e test, per the approved tasks
- Unit tests: 55 in `tests/unit/test_unreal_import.py` (12 new). The full `repository.tests` run gave 1038 passed and 9 skipped.
- Blender headless: 211 passed
- Integration tests: 1 opt-in e2e test (`--runslow`), not run against live editors (by design)

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | `uv run pytest tests/unit tests/bdd -q`: 1038 passed, 9 skipped |
| repository.lint | Pass | `uv run ruff check .`: All checks passed |
| repository.format | Pass | `uv run ruff format --check .`: 316 files already formatted |
| repository.types | Pass | `uv run mypy src tests`: no issues found in 202 source files |
| gate-blender-headless | Pass | `scripts/run-blender-tests.sh`: 211 passed |
| gate-ue-compile | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8` |
| gate-mcp-schema | Pass | MCP tools match tools.json for every server under `mcp-servers/` |
| gate-shellcheck | Pass | `shellcheck -S style` on `scripts/**.sh` exited 0 (applicable through the stale-`main` diff, which includes `scripts/start-unreal-mcp.sh`) |
| gate-ship-smoke | Not applicable | No ship-path change |
| plugin.validate | Pass | `claude plugin validate .`: validation passed with warnings, exit 0 |
| plugin.session-smoke | Pass | Plugin loaded via `--plugin-dir`, and `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable). Coverage is complete (11/11).

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
| **Category** | Testing |
| **Location** | `tests/bdd/features/` |
| **Issue** | No pytest-bdd `.feature` file was added for #146. The tech steering says every AC has a Gherkin test. The approved spec maps its scenarios to the unit and e2e tests instead, as #145's spec did for parts of its coverage. |
| **Impact** | Scenario-to-test mapping is by documentation, not by executable Gherkin. Every AC still has passing automated evidence. |
| **Reason Not Fixed** | The approved tasks do not call for it, and this verify publication scope allows writing only the verification report |

---

## Positive Observations

- The shared `_skipped_lod` rule removes the duplicated rigged-only skip that `check_pivots` and `_variant_meshes` had, so they cannot drift apart again.
- The fake Unreal world models the LOD count on the FBX node, so the tests show the whole host-and-template path (one FBX import, no build-scale writes, the material binding) without a live editor.
- `check_lod_counts` fails closed on a missing or non-int `lod_count`, which also catches an older UE template that does not report it.

---

## Recommendations Summary

### Before PR (Must)
- None

### Short Term (Should)
- None

### Long Term (Could)
- [ ] Loosen the 2.0 s wall-clock bound in `tests/bdd/steps/test_scaffold.py::script_returns_quickly`, or measure detach some other way. It flaked at 2.04 s under heavy parallel load. That test is outside #146's scope.
- [ ] Consider a pytest-bdd feature for the import_ue LOD-group scenarios, next to `tests/bdd/features/import_ue_static_scale.feature`

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `src/nmg_game_dev/unreal/import_asset.py` | 0 | Core fix |
| `src/nmg_game_dev/unreal/__init__.py` | 0 | Export of `check_lod_counts` |
| `docs/asset-contract.md` | 0 | §5 note |
| `tests/unit/test_unreal_import.py` | 0 | 12 new tests |
| `tests/unit/fake_unreal.py` | 0 | `lods`, `imported_fbx` |
| `tests/e2e/test_finalize_e2e.py` | 0 | Opt-in LOD group test |
| `tests/e2e/fixtures/build_crate_fixture.py` | 0 | Headless fixture builder |
| `VERSION`, `CHANGELOG.md`, plugin manifests | 0 | Delivery version prep: patch bump 0.21.2 to 0.21.3, with main's unreleased entries and #146 under `## [0.21.3]` |
| Merge `3689c52` | 0 | Merges `origin/main` (#184). It changes no #146 file, and the branch is level with `origin/main` |

---

## Recommendation

**Ready for PR**

Every acceptance criterion, functional requirement and task has passing evidence. The registered gate coverage is complete with no ceiling, and every applicable required validation passed at `3689c52792e4f98868b7543be80655d6339c1b12`.
