# Verification Report: Naming collisions pass validate and fail after the bake

**Date**: 2026-11-11
**Issue**: #142
**Reviewer**: Claude (nmg-sdlc verify worker, architecture-reviewer)
**Scope**: Implementation verification against spec

**Verification head**: ca9b2d69aaa2846d912d1eb3f5806e6bcde2bc1a

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 5 |
| Testability | 3 |
| Error Handling | 4 |
| **Overall** | 4.3 |

### Implementation Status: Fail
**Total Issues**: 4 (1 required gate failure, 1 medium test-harness finding, 2 low findings)

Code review finds every #142 acceptance criterion met, and the add-on code is the same as at `0046d43`, where `gate-blender-headless` passed 184 tests. This head changes only the `plugin.session-smoke` provider and the previous report. At this head the required `gate-blender-headless` gate **failed** (10 failed, 174 passed), so the ceiling is **Fail**. `gate-ue-compile` and `plugin.session-smoke` were deferred as `incomplete`.

Diagnosis: the headless run did not test this checkout's add-on. `tests/blender/_runner.py` links the add-on into Blender's **user** addons directory (`~/Library/Application Support/Blender/5.2/scripts/addons/nmg_game_dev_blender_addon`), and every lane worktree on this host shares that directory. During this run, lane-5's runner re-pointed the link at `lane-5/plugins/nmg-game-dev-blender-addon` (link mtime 17:42). Lane-1 and lane-5 Blender test runs were still active when this was checked. The failures fit foreign code:

- `test_bl_info_version_matches_version_file` failed, so the loaded add-on's version does not match this checkout's `VERSION`.
- All five #142 regression tests failed, along with four `test_finalize_core` tests. For example, `Desktop: SM_Crate_Trim carries SM_Crate_Trim.001` means the export ran without `_name_meshes`.
- Tracebacks show the add-on loaded from the shared user-addons path.

The failed required result stands, and this report cannot override it. A verify worker's publication scope allows only this report, so the harness fix belongs to implementation. Re-running the unchanged gate while other lanes run Blender tests would race again.

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

- Local verification: Not complete (required `gate-blender-headless` failed; `gate-ue-compile` and `plugin.session-smoke` deferred)
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/142.json` (run id `f2045f01-8864-421b-8fe0-b896fbc3a437`, base `main`, head `ca9b2d69aaa2846d912d1eb3f5806e6bcde2bc1a`, tree clean)
- Coverage: declared 11, recorded 11, complete `true`; no missing, duplicate, or unknown ids
- Ceiling: **Fail** (required `gate-blender-headless` failed; the runner's own ceiling field reads `Incomplete` because two later gates were deferred, and the required failure caps the report at Fail)

---

## Acceptance Criteria Verification

Status reflects code review. The headless test evidence for this head is invalid, because the run loaded another lane's add-on (see Remaining Issues).

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Bake outputs take the contract names when source images already hold them | Pass (code) | `bake_core/rewire.py` `_free_contract_name` runs first in `_image_node`, so the loaded image takes the exact name. Test: `tests/blender/test_bake_unique.py::test_issue142_bake_outputs_take_the_contract_names` |
| AC2 | Authored materials keep their source images | Pass (code) | Only the holder's name changes; its pixels, packing, and users stay. `_Src` names do not match `_(BC\|N\|ORM)$`. The same test checks the `_Authoring` images and pixels |
| AC3 | Re-running the bake does not accumulate suffixed images | Pass (code) | Previous outputs move to `_Src2`, … before the new load. Test: `test_issue142_repeated_bake_leaves_no_suffixed_contract_image` |
| AC4 | Export names mesh datablocks after their objects | Pass (code) | `variants_core/export.py`: `_name_meshes(desktop_objects)` runs before the Desktop FBX. Desktop meshes move to temporary names with their objects. `_name_meshes(mobile_objects)` runs after `_unsuffixed`, before the static and rigged Mobile writes. `finally` restores every name in reverse. Tests: `tests/blender/test_variants.py::test_issue142_mesh_datablocks_export_under_their_object_names`; `tests/unit/test_unreal_import.py` (passed in `repository.tests`) |
| AC5 | A mesh datablock shared between parts is a validate finding | Pass (code) | `contract_core/validate.py` `_shared_mesh_findings` runs for each variant and is not export-only, so it survives `authored=True`. The remediation is in `report.py` `RULES["naming.mesh_data"]`. Test: `test_issue142_shared_mesh_data_is_one_naming_finding[True/False]` |
| AC6 | Existing behavior is preserved | Pass (code) | Each new path does nothing when there is no collision: `holder is None`, `obj.data.name == obj.name`, or a group smaller than 2. `repository.tests` passed (970 passed, 9 skipped) |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Free contract image names before the bake | Complete | `bake_core/rewire.py` |
| T002 | Export mesh datablocks under their objects' export names | Complete | `variants_core/export.py` |
| T003 | Report mesh data shared between parts | Complete | `contract_core/validate.py`, `contract_core/report.py` |
| T004 | Document the mesh-data rule | Complete | `docs/asset-contract.md` section 1 |
| T005 | Blender headless regression tests | Complete (written); evidence invalid at this head | Tests exist. The gate run loaded lane-5's add-on, so their results do not reflect this checkout |
| T006 | Unit check that the snapshot part maps to the exported mesh name | Complete | `tests/unit/test_unreal_import.py`; passed in `repository.tests` |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Each fix is a small helper in the module that owns its step |
| Open/Closed | 4 | The new rule plugs into the `finding`/`RULES` catalogue; export reuses the `restores` mechanism |
| Liskov Substitution | 5 | Not applicable |
| Interface Segregation | 4 | Minimal helper signatures |
| Dependency Inversion | 4 | Direct `bpy.data` use, consistent with the headless-core convention |

### Layer Separation

The changes stay in the step-implementation layer (`bake_core`, `variants_core`, `contract_core`). Validate does not mutate the scene. Export changes names only for the FBX write.

### Dependency Flow

There are no new imports. The `plugin.session-smoke` provider change (`steering/extensions/plugin-session-smoke.mjs`) still imports only Node built-ins. It now reads server health from `claude --plugin-dir <checkout> mcp list` in the ephemeral project, which prints one line per server, instead of the folded `/mcp` screen.

---

## Security Assessment

- [x] Authentication: not applicable
- [x] Authorization: not applicable
- [x] Input validation: names come from Blender datablocks; the smoke passes arguments as an argv array (`shell: false`)
- [x] Injection prevention: no shell interpolation added
- [x] Data protection: source pixels are renamed, never overwritten

---

## Performance Assessment

- [x] Async patterns: the smoke adds a per-call timeout (`MCP_LIST_TIMEOUT_MS`) and at most 3 `mcp list` attempts
- [x] Caching: unchanged
- [x] Resource management: linear passes over images and objects; the smoke timer is cleared on close and on error
- [x] Query optimization: lookups by name and by `as_pointer()`

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (headless Blender) | Not proven at this head |
| AC2 | Yes (SCN002) | Yes | Not proven at this head |
| AC3 | Yes (SCN003) | Yes | Not proven at this head |
| AC4 | Yes (SCN004) | Yes (+ unit) | Unit passed; headless not proven |
| AC5 | Yes (SCN005) | Yes | Not proven at this head |
| AC6 | Yes (SCN006) | Yes (existing suites) | Unit/BDD passed; headless not proven |

### Coverage Summary

- Feature files: 6 scenarios in `feature.gherkin`, realized as headless Blender tests
- Step definitions: `tests/blender/` pytest functions
- Unit tests: 1 new
- Integration tests: 5 new headless Blender tests (one parametrized ×2)

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | No nmg-sdlc `workflows/` or `agents/` paths changed; the exercise does not apply |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 970 passed, 9 skipped |
| `repository.lint` | Pass | `uv run ruff check .` exited 0 |
| `repository.format` | Pass | `uv run ruff format --check .` exited 0 |
| `repository.types` | Pass | `uv run mypy src tests`: no issues in 197 source files |
| `gate-blender-headless` | **Fail** | `scripts/run-blender-tests.sh`: 10 failed, 174 passed. Failures include `test_bl_info_version_matches_version_file`, all #142 tests, and 4 `test_finalize_core` tests. The shared user-addons symlink pointed at lane-5's checkout during the run |
| `gate-ue-compile` | Incomplete | Deferred until required local validations pass |
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
| **Location** | `tests/blender/_runner.py` (links the add-on into `bpy.utils.user_resource("SCRIPTS", path="addons")`); `scripts/run-blender-tests.sh` |
| **Issue** | `gate-blender-headless` failed because the run loaded another lane's add-on. Every worktree on the host shares Blender's user addons directory. Each runner re-points `nmg_game_dev_blender_addon` at its own checkout, so concurrent lanes overwrite one another's link during a run. At check time the link pointed at `lane-5/plugins/nmg-game-dev-blender-addon` (mtime 17:42), and lane-1 and lane-5 headless runs were active |
| **Impact** | The required gate caps verification at Fail. Until the harness isolates the add-on per checkout, headless results on this host are not trustworthy |
| **Reason Not Fixed** | The fix is outside the verify publication scope, which allows only this report. Suggested repair: run each headless test run against its own scripts directory. For example, `run-blender-tests.sh` exports `BLENDER_USER_SCRIPTS` set to a per-run temp dir before launching Blender, and `_runner.py` creates its `addons/` link there, linking or skipping the Blender MCP add-on for the `requires_host` tests. Then re-run the full registered gate |

### Medium Priority

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Testing |
| **Location** | `tests/blender/_runner.py` |
| **Issue** | The runner reports pytest results without checking that `nmg_game_dev_blender_addon` resolves to `_ADDON_SRC` for the whole run. A re-pointed link gives misleading failures, or false passes |
| **Impact** | Foreign-code results can be recorded as this checkout's evidence |
| **Reason Not Fixed** | Outside the verify publication scope. Isolating the scripts directory (above) removes the cause. A guard that compares the resolved link to `_ADDON_SRC` would also help |

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
| **Category** | Error Handling |
| **Location** | `plugins/nmg-game-dev-blender-addon/variants_core/export.py` (Desktop `_rename` of `desktop_meshes`) |
| **Issue** | If validate is bypassed and two Desktop parts share a mesh, the datablock gets the temporary prefix twice. The reverse restore still returns its original name |
| **Impact** | No session corruption. Validate's `naming.mesh_data` reports the case first |
| **Reason Not Fixed** | The behavior is safe and is guarded upstream |

---

## Positive Observations

- Both fixes keep the session unchanged: source pixels are preserved, and export restores names in reverse inside `finally`.
- `naming.mesh_data` runs in the `authored=True` pre-bake pass, so it is reported before any long bake.
- The smoke provider change removes the cause of the previous `plugin.session-smoke` failure: plugin servers folded or truncated in a short `/mcp` pane.

---

## Recommendations Summary

### Before PR (Must)
- [ ] Isolate the headless Blender add-on per checkout or run (`BLENDER_USER_SCRIPTS` temp dir, or equivalent), then re-run the full registered gate at the new head.

### Short Term (Should)
- [ ] Add a rigged-asset variant of the AC4 export test.

### Long Term (Could)
- [ ] Skip duplicate datablocks in the Desktop mesh temp-rename.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/bake_core/rewire.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/variants_core/export.py` | 1 (low) | |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | 0 | |
| `docs/asset-contract.md` | 0 | |
| `tests/blender/test_bake_unique.py` | 0 | |
| `tests/blender/test_variants.py` | 1 (low) | |
| `tests/blender/test_contract_validate.py` | 0 | |
| `tests/unit/test_unreal_import.py` | 0 | |
| `steering/extensions/plugin-session-smoke.mjs` | 0 | Reads health from `claude mcp list`; not yet exercised, because the gate was deferred |
| `tests/blender/_runner.py` | 2 (gate, medium) | Not changed by #142; the cause of the invalid headless run |

---

## Recommendation

**Needs fixes**

Code review finds the #142 implementation meets every acceptance criterion. Verification cannot pass while the required `gate-blender-headless` result is failed. That run tested another lane's add-on through the shared Blender user-addons link. Isolate the headless harness per checkout, then re-run the full registered gate before delivery.
