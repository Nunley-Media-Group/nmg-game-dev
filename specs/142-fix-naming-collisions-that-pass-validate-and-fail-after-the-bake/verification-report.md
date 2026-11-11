# Verification Report: Naming collisions pass validate and fail after the bake

**Date**: 2026-11-11
**Issue**: #142
**Reviewer**: Claude (nmg-sdlc verify worker, architecture-reviewer)
**Scope**: Implementation verification against spec

**Verification head**: 0046d43f96b7726c83ced4e99a0d172d7ad0deef

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
**Total Issues**: 3 (1 gate failure, 2 low findings)

The code change satisfies every acceptance criterion, and 8 of the 9 applicable required gates passed at the verification head, including `gate-blender-headless` (184 passed). The required `plugin.session-smoke` gate failed with `plugin MCP servers not all connected: nmg-game-dev:blender missing`, so the deterministic ceiling is **Fail**. The captured `/mcp` screen shows a 16-row pane: the user and claude.ai servers are visible, and the plugin servers sit under the `↓ 10 more` fold. The provider only reads the visible screen, so it found no `nmg-game-dev` `blender` line. This looks like a limit of how the smoke reads the screen in a short Herdr pane, not a defect from #142, which does not touch `.mcp.json` or any MCP server. The required failed result still stands, and this report cannot override it.

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

- Local verification: Not complete (required `plugin.session-smoke` failed)
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/142.json` (run id `8cba658c-4aca-4f97-aa3f-0977565400ee`, base `main`, head `0046d43f96b7726c83ced4e99a0d172d7ad0deef`, tree clean)
- Coverage: declared 11, recorded 11, complete `true`; no missing, duplicate, or unknown ids
- Ceiling: **Fail**

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Bake outputs take the contract names when source images already hold them | Pass | `bake_core/rewire.py` `_free_contract_name` called first in `_image_node`; `tests/blender/test_bake_unique.py::test_issue142_bake_outputs_take_the_contract_names` checks the exact names and that the full contract reports no `naming.texture` after variants |
| AC2 | Authored materials keep their source images | Pass | The renamed holder keeps its datablock and users; the same test checks that `M_Crate_Body_Authoring` samples `T_Crate_Body_{BC,N,ORM}_Src` with unchanged pixels. `_Src` names do not match the `_(BC\|N\|ORM)$` contract pattern |
| AC3 | Re-running the bake does not accumulate suffixed images | Pass | `test_issue142_repeated_bake_leaves_no_suffixed_contract_image`: exactly one image per contract name, none matching `\.\d+$`, and the previous output moved to `_Src2` |
| AC4 | Export names mesh datablocks after their objects | Pass | `variants_core/export.py` `_name_meshes` runs on the Desktop objects before the Desktop FBX, and on the Mobile objects after `_unsuffixed` (covering the static LOD group and the rigged per-LOD jobs). Desktop meshes move to temporary names with their objects, and `finally` restores every name in reverse. `tests/blender/test_variants.py::test_issue142_mesh_datablocks_export_under_their_object_names` re-imports both FBX files and checks the session names. `tests/unit/test_unreal_import.py` checks the expected mesh names |
| AC5 | A mesh datablock shared between parts is a validate finding | Pass | `contract_core/validate.py` `_shared_mesh_findings` runs for each variant. `naming.mesh_data` is not in `_EXPORT_ONLY_RULES`, so it survives `authored=True`. `report.py` `RULES["naming.mesh_data"]` holds the Make Single User remediation. `test_issue142_shared_mesh_data_is_one_naming_finding[True/False]` |
| AC6 | Existing behavior is preserved | Pass | Both new paths are no-ops when nothing collides (`holder is None`; `obj.data.name == obj.name`; groups smaller than 2). The existing bake, variants, and validate suites pass unchanged (`gate-blender-headless` 184 passed; `repository.tests` 970 passed) |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Free contract image names before the bake | Complete | `bake_core/rewire.py` |
| T002 | Export mesh datablocks under their objects' export names | Complete | `variants_core/export.py` |
| T003 | Report mesh data shared between parts | Complete | `contract_core/validate.py`, `contract_core/report.py` |
| T004 | Document the mesh-data rule | Complete | `docs/asset-contract.md` section 1 |
| T005 | Blender headless regression tests | Complete | `tests/blender/test_bake_unique.py`, `test_variants.py`, `test_contract_validate.py`. `bake_fixtures.py` did not need changes because the existing `image_material` and `checker_image` helpers were reused |
| T006 | Unit check that the snapshot part maps to the exported mesh name | Complete | `tests/unit/test_unreal_import.py` |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Each fix is a small helper in the module that owns that step (bake rewire, export, validate) |
| Open/Closed | 4 | The new rule plugs into the existing `finding`/`RULES` catalogue; export reuses the `restores` mechanism |
| Liskov Substitution | 5 | Not applicable; no type hierarchies changed |
| Interface Segregation | 4 | Helper signatures are minimal (`objects` in, restore pairs out) |
| Dependency Inversion | 4 | Uses `bpy.data` directly, which matches the existing headless-core convention |

### Layer Separation

The changes stay inside the step-implementation layer (`bake_core`, `variants_core`, `contract_core`), as steering's layer table requires. Validate stays read-only: it reports shared data and does not mutate the scene. Export changes names only for the duration of the FBX write and restores them.

### Dependency Flow

No new imports or cross-core dependencies. `validate.export_name` and `export._unsuffixed` still agree on the Mobile-suffix removal that the mesh names now follow.

---

## Security Assessment

- [x] Authentication: not applicable
- [x] Authorization: not applicable
- [x] Input validation: names come from Blender datablocks; no paths or shell built from them beyond the existing PNG writer
- [x] Injection prevention: not applicable
- [x] Data protection: source pixels are preserved (renamed, never overwritten)

---

## Performance Assessment

- [x] Async patterns: not applicable (runs in background Blender)
- [x] Caching: unchanged
- [x] Resource management: O(n) passes over images and objects; `_free_contract_name` probes `_SrcN` names linearly, bounded by how many re-bakes have run
- [x] Query optimization: dictionary lookups by name and `as_pointer()` grouping

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (headless Blender test) | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes (+ unit) | Yes |
| AC5 | Yes (SCN005) | Yes (parametrized authored True/False) | Yes |
| AC6 | Yes (SCN006) | Yes (existing suites unchanged) | Yes |

### Coverage Summary

- Feature files: 6 scenarios in `feature.gherkin`, realized as headless Blender tests, which is the steering-designated layer for add-on code
- Step definitions: implemented as `tests/blender/` pytest functions
- Unit tests: 1 new (`test_build_import_code_expects_each_desktop_part_under_its_object_name`)
- Integration tests: 5 new headless Blender tests (one parametrized ×2)

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | No nmg-sdlc plugin workflow or agent files changed (no `workflows/` or `agents/` paths in the diff); the exercise is not applicable |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 970 passed, 9 skipped |
| `repository.lint` | Pass | `uv run ruff check .` exited 0 |
| `repository.format` | Pass | `uv run ruff format --check .` exited 0 |
| `repository.types` | Pass | `uv run mypy src tests`: no issues in 197 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 184 passed in 143 s |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against UE 5.8: `Result: Succeeded` (applies because the version bump touched `nmg-game-dev.uplugin`) |
| `gate-mcp-schema` | Not applicable | No `mcp-servers/**` changes |
| `gate-shellcheck` | Not applicable | No `scripts/**.sh` changes |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .`: `Validation passed with warnings` |
| `plugin.session-smoke` | **Fail** | `plugin MCP servers not all connected: nmg-game-dev:blender missing`. The captured `/mcp` screen lists only the user and claude.ai servers, with `↓ 10 more` below the visible area of a 16-row pane |

**Gate Summary**: 8/9 applicable gates passed, 1 failed, 0 incomplete (3 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None; no code findings needed a fix | — | — |

## Remaining Issues

### Critical Issues

| Field | Value |
|-------|-------|
| **Severity** | Critical (required gate) |
| **Category** | Verification gate |
| **Location** | `steering/extensions/plugin-session-smoke.mjs` (`serverStatus`, reads the `--source visible` screen only) |
| **Issue** | `plugin.session-smoke` failed: `nmg-game-dev:blender missing`. The Herdr smoke tab opened with a 16-row viewport, so `/mcp` folded the plugin servers under `↓ 10 more`, and the visible-screen parse found no `nmg-game-dev … blender` line |
| **Impact** | The required gate caps verification at Fail, so delivery is blocked |
| **Reason Not Fixed** | This is an environment and provider problem, not one caused by #142, which changes no MCP config. The fix is a taller Herdr client for the smoke tab, or a steering-extension change that reads scrollback or scrolls the `/mcp` list. Both are outside the verify publication scope, which allows only this report. Re-running the unchanged smoke is not allowed |

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `tests/blender/test_variants.py` |
| **Issue** | The AC4 regression test covers the static Mobile LOD group, but not a rigged asset's per-LOD FBX files with a mismatched datablock |
| **Impact** | The rigged path runs through the same `_name_meshes(mobile_objects)` call, but no test covers it on its own |
| **Reason Not Fixed** | Outside the verify publication scope; a candidate follow-up test |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `plugins/nmg-game-dev-blender-addon/variants_core/export.py` (Desktop `_rename` of `desktop_meshes`) |
| **Issue** | If validate is bypassed and two Desktop parts share a mesh, the shared datablock is renamed to a temporary name twice (double prefix). The reverse restore still returns the original name |
| **Impact** | No session corruption; the FBX would still carry one name for two objects, and validate's `naming.mesh_data` reports that case first |
| **Reason Not Fixed** | Behaviour is safe, and validate guards against it upstream |

---

## Positive Observations

- Both fixes adapt ghost1's tested approach and keep the session unchanged: source pixels are preserved, and export names are restored in reverse order inside `finally`.
- The new validate rule runs in the `authored=True` pre-bake pass, so shared datablocks are reported before any long bake.
- The tests assert the observable outcomes: exact names, unchanged pixels, re-imported FBX mesh names, and the full contract after variants.

---

## Recommendations Summary

### Before PR (Must)
- [ ] Get a real passing `plugin.session-smoke` result: run it in a Herdr client tall enough for `/mcp` to show the plugin servers, or make the extension read scrollback or scroll the list (a steering change), then re-run the full gate.

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
| `steering/extensions/plugin-session-smoke.mjs` | 1 (gate) | Provider for the failed gate; not changed by #142 |

---

## Recommendation

**Needs fixes**

The implementation meets every #142 acceptance criterion, and the code-level gates are green. Verification still cannot pass while the required `plugin.session-smoke` result is failed. Diagnose the smoke environment, change it, and re-run the full registered gate before delivery.
