# Verification Report: Naming collisions pass validate and fail after the bake

**Date**: 2026-11-11
**Issue**: #142
**Reviewer**: Claude (nmg-sdlc verify worker, architecture-reviewer)
**Scope**: Implementation verification against spec

**Verification head**: 1419615b9a7f0cfa5236f71c74f34949021b30f7

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

### Implementation Status: Pass
**Total Issues**: 3 (all low; none block delivery)

Every #142 acceptance criterion is met, and the full registered gate passed at this head. Coverage is complete: 11 declared, 11 recorded, 8 applicable and passed, 3 not applicable.

The previous verification (head `5448dc9`) failed only on `tests/bdd/steps/test_scaffold.py::test_unreal_launcher_detaches`. Under host load, its 2.0 s limit was also timing the plugin build check over `fixtures/Plugins`. Commit `1419615` now runs the launcher against a copy of `dogfood.uproject` with no plugin directories beside it, so the limit times only the detach. The test asserts the same thing: the launcher exits 0, returns in under 2 s, and passes the MCP arguments to the editor. In this run `repository.tests` passed with 970 passed and 9 skipped. The gates the previous run deferred, `gate-ue-compile` and `plugin.session-smoke`, ran and passed.

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

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/142.json`, generated `2026-11-12T00:15:06Z` (run id `fad8febb-8ced-49c0-adb9-232ee2552a39`, base `main`, head `1419615b9a7f0cfa5236f71c74f34949021b30f7`, tree clean)
- Coverage: 11 declared, 11 recorded, complete `true`; no missing, duplicate, or unknown ids
- Ceiling: none (`ceiling: null`). Every applicable required validation recorded `passed`.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Bake outputs take the contract names when source images already hold them | Pass | `bake_core/rewire.py` calls `_free_contract_name` first in `_image_node`, so the loaded image takes the exact name. `tests/blender/test_bake_unique.py::test_issue142_bake_outputs_take_the_contract_names` passes, including `validate_asset(..., authored=False)` with no `naming.texture` after variants |
| AC2 | Authored materials keep their source images | Pass | Only the image holding the name is renamed (`<name>_Src`, `_Src2`, …), so its pixels, packing, and users stay. The same test checks the `_Authoring` images by name and compares their pixels |
| AC3 | Re-running the bake does not accumulate suffixed images | Pass | Previous outputs move to `_Src2` before the new load. `test_issue142_repeated_bake_leaves_no_suffixed_contract_image` passes |
| AC4 | Export names mesh datablocks after their objects | Pass | `variants_core/export.py` `_name_meshes(desktop_objects)` runs before the Desktop FBX write. Desktop meshes then move to temporary names with their objects. `_name_meshes(mobile_objects)` runs after `_unsuffixed` and before the static and rigged Mobile writes. `finally` restores every name in reverse order. `tests/blender/test_variants.py::test_issue142_mesh_datablocks_export_under_their_object_names` and `tests/unit/test_unreal_import.py::test_build_import_code_expects_each_desktop_part_under_its_object_name` pass |
| AC5 | A mesh datablock shared between parts is a validate finding | Pass | `contract_core/validate.py` runs `_shared_mesh_findings` for each variant, outside the export-only checks, so the `authored=True` run reports it. The remediation is in `report.py` `RULES["naming.mesh_data"]`. `test_issue142_shared_mesh_data_is_one_naming_finding[True/False]` pass |
| AC6 | Existing behavior is preserved | Pass | Each new path does nothing when there is no collision (`holder is None`, `obj.data.name == obj.name`, or a group smaller than 2). All 184 headless Blender tests and 970 unit/BDD tests pass |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Free contract image names before the bake | Complete | `bake_core/rewire.py` |
| T002 | Export mesh datablocks under their objects' export names | Complete | `variants_core/export.py` |
| T003 | Report mesh data shared between parts | Complete | `contract_core/validate.py`, `contract_core/report.py` |
| T004 | Document the mesh-data rule | Complete | `docs/asset-contract.md` section 1 |
| T005 | Blender headless regression tests | Complete | Passed in `gate-blender-headless` (184 passed) |
| T006 | Unit check that the snapshot part maps to the exported mesh name | Complete | `tests/unit/test_unreal_import.py`; passed in `repository.tests` |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Each fix is a small helper in the module that owns its step |
| Open/Closed | 4 | The new rule plugs into the `finding`/`RULES` catalogue, and export reuses the `restores` mechanism |
| Liskov Substitution | 5 | Not applicable |
| Interface Segregation | 4 | Minimal helper signatures |
| Dependency Inversion | 4 | Uses `bpy.data` directly, as the other headless cores do |

### Layer Separation

The changes stay in the step-implementation layer (`bake_core`, `variants_core`, `contract_core`). Validate does not change the scene, and export renames only for the FBX write, then restores.

### Dependency Flow

#142 adds no new imports to the add-on. `tests/blender/_runner.py` now links the add-on in a private `mkdtemp` directory placed first on `sys.path`, not in Blender's shared user add-ons directory. It removes any preloaded copy and fails when the import resolves outside this checkout. That is the right isolation for concurrent lanes. `steering/extensions/plugin-session-smoke.mjs` now reads server health from `claude --plugin-dir … mcp list` instead of scraping the `/mcp` pane. Each attempt is bounded by a timeout, and the result no longer depends on the pane's size.

---

## Security Assessment

- [x] Authentication: not applicable
- [x] Authorization: not applicable
- [x] Input validation: names come from Blender datablocks
- [x] Injection prevention: no shell interpolation added; the smoke uses `spawn` with `shell: false`
- [x] Data protection: source pixels are renamed, never overwritten

---

## Performance Assessment

- [x] Async patterns: not applicable
- [x] Caching: unchanged
- [x] Resource management: linear passes over images and objects
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
- Integration tests: 5 new headless Blender test cases (one test parametrized ×2), all passed

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
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 970 passed, 9 skipped in 74.91 s |
| `repository.lint` | Pass | `uv run ruff check .`: All checks passed! |
| `repository.format` | Pass | `uv run ruff format --check .`: 309 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: Success: no issues found in 197 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 184 passed in 170.00 s |
| `gate-ue-compile` | Pass | `Build.sh DogfoodEditor Mac Development -Project=fixtures/dogfood.uproject`: Result: Succeeded (UE 5.8) |
| `gate-mcp-schema` | Not applicable | No `mcp-servers/**` changes |
| `gate-shellcheck` | Not applicable | No `scripts/**.sh` changes |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .`: Validation passed with warnings |
| `plugin.session-smoke` | Pass | Real lifecycle: ephemeral git project → Herdr tab → `herdr agent start … --plugin-dir <checkout>` (trust accepted, idle) → `claude --plugin-dir <checkout> mcp list` (attempt 1): `nmg-game-dev:blender connected` → tab closed and project removed |

**Gate Summary**: 8/8 applicable gates passed, 0 failed, 0 incomplete (3 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None. The verify publication scope allows only this report | — | — |

## Remaining Issues

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
| **Category** | Edge case |
| **Location** | `plugins/nmg-game-dev-blender-addon/bake_core/rewire.py` `_free_contract_name` |
| **Issue** | For a contract name of 60 or more characters, Blender's 63-character name limit truncates `<name>_Src`. The free-name check compares against the untruncated string, so Blender may add a `.001` suffix to the moved image |
| **Impact** | Only the moved source image gets an odd name. The truncated name cannot end in `_BC`, `_N`, or `_ORM`, so the output still takes the exact contract name and `naming.texture` is unaffected |
| **Reason Not Fixed** | Cosmetic and does not affect the contract |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Resource management |
| **Location** | `tests/blender/_runner.py` `_install_addon_link` |
| **Issue** | Each run creates a `nmg-blender-tests-*` temp directory holding one symlink and never removes it |
| **Impact** | A few bytes per run in the system temp directory; the OS reclaims them |
| **Reason Not Fixed** | Harmless; outside the verify publication scope |

---

## Positive Observations

- Both fixes leave the session unchanged: source pixels are kept, and export restores names in reverse order inside `finally`.
- `naming.mesh_data` runs in the `authored=True` pre-bake pass, so the finding appears before any long bake.
- The launcher-detach test now times only the detach, not the unrelated plugin scan, so heavy load from concurrent lanes no longer fails it.
- The session smoke reads `mcp list`, so its result no longer depends on the pane's size.

---

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- [ ] Add a rigged-asset variant of the AC4 export test.

### Long Term (Could)
- [ ] Clean up the per-run temp directory in the headless Blender runner.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/bake_core/rewire.py` | 1 (low) | Long-name truncation edge case |
| `plugins/nmg-game-dev-blender-addon/variants_core/export.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | 0 | |
| `docs/asset-contract.md` | 0 | |
| `tests/blender/_runner.py` | 1 (low) | Per-run add-on isolation is correct |
| `tests/blender/test_bake_unique.py` | 0 | |
| `tests/blender/test_variants.py` | 1 (low) | |
| `tests/blender/test_contract_validate.py` | 0 | |
| `tests/unit/test_unreal_import.py` | 0 | |
| `tests/bdd/steps/test_scaffold.py` | 0 | The detach test copies the `.uproject` into a plugin-free directory |
| `steering/extensions/plugin-session-smoke.mjs` | 0 | Passed with the real lifecycle |

---

## Recommendation

**Ready for PR**

The #142 implementation meets every acceptance criterion. The full registered gate passed at `1419615b9a7f0cfa5236f71c74f34949021b30f7` with complete coverage, including `gate-ue-compile` and the real `plugin.session-smoke`. The remaining findings are low and can wait for follow-up.
