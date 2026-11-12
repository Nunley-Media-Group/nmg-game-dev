# Verification Report: Naming collisions pass validate and fail after the bake

**Date**: 2026-11-11
**Issue**: #142
**Reviewer**: Claude (nmg-sdlc verify worker, architecture-reviewer)
**Scope**: Implementation verification against spec

**Verification head**: 5448dc900dee6531a4fbf11e416f7d1dd8364e50

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 5 |
| Testability | 4 |
| Error Handling | 4 |
| **Overall** | 4.5 |

### Implementation Status: Fail
**Total Issues**: 3 (1 required gate failure, 2 low findings)

The headless-runner fix in `5448dc9` works. `gate-blender-headless` now loads this checkout's add-on and passed 184 tests, including all five #142 regression tests. Code review finds every #142 acceptance criterion met.

The required `repository.tests` gate **failed** in both full-gate runs at this head, so the ceiling is **Fail**. The only failure in each run was `tests/bdd/steps/test_scaffold.py::test_unreal_launcher_detaches`: run 1 took 2.04 s and run 2 took 2.36 s, against a 2.0 s limit. #142 changes neither that test nor `scripts/start-unreal-mcp.sh`. Run alone, the test passes in about 1 s (3/3 runs). During verification the host load average was 143 to 182, with six lanes running Blender, UE, and pytest at once. With `repository.tests` failed, the runner deferred `gate-ue-compile` and `plugin.session-smoke` as `incomplete`.

A verify worker may publish only this report, so the repair belongs to the controller or implementation.

---

## Issue Scope

- Active issue: #142
- Spec: `specs/142-fix-naming-collisions-that-pass-validate-and-fail-after-the-bake`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5, AC6]; FR [FR1, FR2, FR3, FR4, FR5, FR6, FR7]; tasks [T001, T002, T003, T004, T005, T006]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005, SCN006]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":142,"specPath":"specs/142-fix-naming-collisions-that-pass-validate-and-fail-after-the-bake","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7"],"tasks":["T001","T002","T003","T004","T005","T006"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Not complete. Required `repository.tests` failed; `gate-ue-compile` and `plugin.session-smoke` were deferred.
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/142.json`, generated `2026-11-12T00:01:13Z` (run id `fad8febb-8ced-49c0-adb9-232ee2552a39`, base `main`, head `5448dc900dee6531a4fbf11e416f7d1dd8364e50`, tree clean)
- Coverage: 11 declared, 11 recorded, complete `true`; no missing, duplicate, or unknown ids
- Ceiling: **Fail**. Required `repository.tests` failed. The runner's ceiling field reads `Incomplete` because two later gates were deferred, but a required failure caps the report at Fail.
- Run 1 (`2026-11-11T23:55:43Z`) recorded the same results. Its only failure was the same test, at 2.04 s.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Bake outputs take the contract names when source images already hold them | Pass | `bake_core/rewire.py` `_free_contract_name` runs first in `_image_node`, so the loaded image takes the exact name. `tests/blender/test_bake_unique.py::test_issue142_bake_outputs_take_the_contract_names` passed in `gate-blender-headless` |
| AC2 | Authored materials keep their source images | Pass | The bake renames only the holder image, so its pixels, packing, and users stay. `_Src` names do not match `_(BC\|N\|ORM)$`. The same test checks the `_Authoring` images and their pixels |
| AC3 | Re-running the bake does not accumulate suffixed images | Pass | Previous outputs move to `_Src2` before the new load. `test_issue142_repeated_bake_leaves_no_suffixed_contract_image` passed |
| AC4 | Export names mesh datablocks after their objects | Pass | `variants_core/export.py` calls `_name_meshes(desktop_objects)` before the Desktop FBX write. Desktop meshes then move to temporary names with their objects, and `_name_meshes(mobile_objects)` runs after `_unsuffixed`, before the static and rigged Mobile writes. `finally` restores every name in reverse order. `tests/blender/test_variants.py::test_issue142_mesh_datablocks_export_under_their_object_names` passed. `tests/unit/test_unreal_import.py::test_build_import_code_expects_each_desktop_part_under_its_object_name` passed |
| AC5 | A mesh datablock shared between parts is a validate finding | Pass | `contract_core/validate.py` `_shared_mesh_findings` runs for each variant and is not export-only, so the `authored=True` run reports it. The remediation is in `report.py` `RULES["naming.mesh_data"]`. `test_issue142_shared_mesh_data_is_one_naming_finding[True/False]` passed |
| AC6 | Existing behavior is preserved | Pass | Each new path does nothing when there is no collision (`holder is None`, `obj.data.name == obj.name`, or a group smaller than 2). All 184 headless Blender tests passed, including the existing bake, variants, and validate suites |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Free contract image names before the bake | Complete | `bake_core/rewire.py` |
| T002 | Export mesh datablocks under their objects' export names | Complete | `variants_core/export.py` |
| T003 | Report mesh data shared between parts | Complete | `contract_core/validate.py`, `contract_core/report.py` |
| T004 | Document the mesh-data rule | Complete | `docs/asset-contract.md` section 1 |
| T005 | Blender headless regression tests | Complete | Passed in `gate-blender-headless` (184 passed) |
| T006 | Unit check that the snapshot part maps to the exported mesh name | Complete | `tests/unit/test_unreal_import.py`; the test passed in `repository.tests`, which failed only on the unrelated launcher timing test |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Each fix is a small helper in the module that owns its step |
| Open/Closed | 4 | The new rule plugs into the `finding`/`RULES` catalogue, and export reuses the `restores` mechanism |
| Liskov Substitution | 5 | Not applicable |
| Interface Segregation | 4 | Minimal helper signatures |
| Dependency Inversion | 4 | Direct `bpy.data` use, consistent with the headless-core convention |

### Layer Separation

The changes stay in the step-implementation layer (`bake_core`, `variants_core`, `contract_core`). Validate does not mutate the scene, and export renames only for the FBX write.

### Dependency Flow

#142 adds no new imports to the add-on. `tests/blender/_runner.py` now links the add-on in a private `mkdtemp` directory placed first on `sys.path`, instead of Blender's shared user add-ons directory. It removes any preloaded copy and fails when the import resolves outside this checkout. That is the right isolation for concurrent lanes.

---

## Security Assessment

- [x] Authentication: not applicable
- [x] Authorization: not applicable
- [x] Input validation: names come from Blender datablocks
- [x] Injection prevention: no shell interpolation added
- [x] Data protection: source pixels are renamed, never overwritten

---

## Performance Assessment

- [x] Async patterns: not applicable
- [x] Caching: unchanged
- [x] Resource management: linear passes over images and objects. The test runner leaves one small temp directory holding a symlink per run (see Low findings)
- [x] Query optimization: lookups by name and by `as_pointer()`

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (headless Blender) | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes (+ unit) | Yes |
| AC5 | Yes (SCN005) | Yes | Yes |
| AC6 | Yes (SCN006) | Yes (existing suites) | Yes |

### Coverage Summary

- Feature files: 6 scenarios in `feature.gherkin`, implemented as headless Blender tests
- Step definitions: `tests/blender/` pytest functions
- Unit tests: 1 new (passed)
- Integration tests: 5 new headless Blender tests (one parametrized ×2), all passed

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | No nmg-sdlc `workflows/` or `agents/` paths changed, so the exercise does not apply |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | **Fail** | `uv run pytest tests/unit tests/bdd -q`: 1 failed, 969 passed, 9 skipped (both runs). `test_unreal_launcher_detaches`: "Script took 2.36s (> 2s)" (run 1: 2.04 s) |
| `repository.lint` | Pass | `uv run ruff check .`: All checks passed |
| `repository.format` | Pass | `uv run ruff format --check .`: 309 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: no issues in 197 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 184 passed (both runs) |
| `gate-ue-compile` | Incomplete | Deferred until required local validations pass. It applies because `nmg-game-dev.uplugin` changed (version bump) |
| `gate-mcp-schema` | Not applicable | No `mcp-servers/**` changes |
| `gate-shellcheck` | Not applicable | No `scripts/**.sh` changes |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .`: Validation passed with warnings |
| `plugin.session-smoke` | Incomplete | Deferred until required local validations pass |

**Gate Summary**: 5/8 applicable gates passed, 1 failed, 2 incomplete (3 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None. The verify publication scope allows only this report | — | — |

## Remaining Issues

### Critical Issues

| Field | Value |
|-------|-------|
| **Severity** | Critical (required gate) |
| **Category** | Testing / verification environment |
| **Location** | `tests/bdd/steps/test_scaffold.py:271` (`script_returns_quickly`, 2.0 s wall-clock limit); `scripts/start-unreal-mcp.sh` |
| **Issue** | `repository.tests` failed on `test_unreal_launcher_detaches`, the AC3 test that the launcher detaches. The launcher returned in 2.04 s and 2.36 s, against a strict 2.0 s limit. In the test environment it starts the project plugin freshness check and build ("Building project plugins (VibeUE, nmg-game-dev)"), which walks this lane's local `fixtures/Plugins` copy. Run alone, the test passes in 0.97 to 1.14 s. During the gate the host load average was 143 to 182 |
| **Impact** | The required gate caps verification at Fail and defers `gate-ue-compile` and `plugin.session-smoke`. The #142 change does not cause this: the branch touches neither the launcher nor the test |
| **Reason Not Fixed** | Outside the verify publication scope, which allows only this report. Suggested repairs: (a) merge `origin/main` into the branch. It carries `02597c5` (#184), which stops `start-unreal-mcp.sh` rebuilding plugins on every launch and checks each module against its own source. That may bring the launcher well under the limit, but this is not verified. Or (b) re-run the full gate when lane contention is lower. Or (c) make the AC3 timing check robust to host load in a separate issue. Then re-run the full registered gate at the new head |

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `tests/blender/test_variants.py` |
| **Issue** | The AC4 test covers the static Mobile LOD group, but not a rigged asset's per-LOD FBX files with a mismatched datablock |
| **Impact** | The rigged path uses the same `_name_meshes(mobile_objects)` call, but no test covers it on its own |
| **Reason Not Fixed** | Outside the verify publication scope; a candidate follow-up test |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Resource management |
| **Location** | `tests/blender/_runner.py` `_install_addon_link` |
| **Issue** | Each run creates a `nmg-blender-tests-*` temp directory holding one symlink and never removes it; `os._exit` skips cleanup |
| **Impact** | A few bytes per run in the system temp directory; the OS reclaims them |
| **Reason Not Fixed** | Harmless; outside the verify publication scope |

---

## Positive Observations

- Both fixes leave the session unchanged: source pixels are preserved, and export restores names in reverse order inside `finally`.
- `naming.mesh_data` runs in the `authored=True` pre-bake pass, so the finding appears before any long bake.
- The runner isolation removes the cross-lane race that invalidated the previous headless run, and it guards the resolved module origin.

---

## Recommendations Summary

### Before PR (Must)
- [ ] Get `repository.tests` green at the branch head: merge `origin/main` (#184 launcher fix), or re-run when lane contention drops. Then re-run the full registered gate, including `gate-ue-compile` and `plugin.session-smoke`.

### Short Term (Should)
- [ ] Add a rigged-asset variant of the AC4 export test.

### Long Term (Could)
- [ ] Make the launcher-detach timing assertion robust to host load.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/bake_core/rewire.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/variants_core/export.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | 0 | |
| `docs/asset-contract.md` | 0 | |
| `tests/blender/_runner.py` | 1 (low) | Add-on isolation per run is correct |
| `tests/blender/test_bake_unique.py` | 0 | |
| `tests/blender/test_variants.py` | 1 (low) | |
| `tests/blender/test_contract_validate.py` | 0 | |
| `tests/unit/test_unreal_import.py` | 0 | |
| `steering/extensions/plugin-session-smoke.mjs` | 0 | Not exercised; the gate was deferred |
| `tests/bdd/steps/test_scaffold.py` | 1 (gate) | Not changed by #142; its wall-clock limit failed under host load |

---

## Recommendation

**Needs fixes**

Code review and the headless Blender gate show that the #142 implementation meets every acceptance criterion. Verification cannot pass while the required `repository.tests` result is failed. The only failure is the unrelated launcher timing test, which exceeds 2.0 s under heavy host load. Get it green, preferably by merging `origin/main` with the #184 launcher fix, then re-run the full registered gate before delivery.
