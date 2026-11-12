# Verification Report: Fix finalize export failing the contract on Mobile LODs the variants step decimated

**Date**: 2026-11-11
**Issue**: #140
**Reviewer**: Claude (nmg-sdlc architecture-reviewer)
**Scope**: Implementation verification against spec
**Verification head**: b0846686c9b507de63182d5a7b430761ea48329b

---

## Executive Summary

The fix moves Desktop cleanup into one shared `clean_mesh` routine in `variants_core/meshes.py`. The routine merges doubles, dissolves degenerate geometry, and deletes zero-area faces at the contract's `1e-8` limit. It also removes faces past the two largest on any non-manifold edge, removes repeated faces and loose geometry, and recalculates normals. `fit_meshes` runs it on every candidate before comparing against the target, and `build_mobile` re-seats the Mobile variant on the world origin with `_reseat`. Every applicable registered gate passed at the verification head, including headless Blender (189 passed, with the 10 new `test_variants_clean.py` tests) and the UE compile.

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 4 |
| Testability | 4 |
| Error Handling | 4 |
| **Overall** | 4.5 |

### Implementation Status: Pass
**Total Issues**: 0 blocking (3 low-severity observations)

---

## Issue Scope

- Active issue: #140
- Spec: `specs/140-fix-finalize-export-failing-the-contract-on-mobile-lods-the-variants-step-decimated`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5, AC6, AC7]; FR [FR1, FR2, FR3, FR4, FR5, FR6, FR7]; tasks [T001, T002, T003, T004, T005]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005, SCN006, SCN007]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":140,"specPath":"specs/140-fix-finalize-export-failing-the-contract-on-mobile-lods-the-variants-step-decimated","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7"],"tasks":["T001","T002","T003","T004","T005"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/140.json` (runner `sdlc-verify-steering.mjs`, controller run `979946ff-b251-4bad-aa36-864693c81b63`, base `main`)
- Identity: head `b0846686c9b507de63182d5a7b430761ea48329b`, clean tree
- Coverage: declared 11, recorded 11, complete `true`; no missing, duplicate or unknown results
- Ceiling: none

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Decimated LODs have no zero-area or loose geometry | Pass | `variants_core/meshes.py` `fit_meshes` wraps every `decimated_copy` in `_cleaned`, and `clean_mesh` deletes faces `< ZERO_AREA_LIMIT` (1e-8) and loose geometry; `test_scn001_decimated_lods_have_no_zero_area_or_loose_geometry` (rigged Hero, defect injected into every decimated candidate) passes |
| AC2 | Stable normals on Desktop and every Mobile LOD | Pass | `meshes.py` `_drop_non_manifold_faces` keeps the two largest faces per >2-face edge, then `recalc_face_normals`; `test_scn002_normals_are_stable_on_desktop_and_every_mobile_lod` asserts no `geometry.normals` and identical repeated validation |
| AC3 | Mobile root re-seated after decimation | Pass | `variants_core/mobile.py` `_reseat` measures world bounds of non-`_LOD[1-9]` meshes (same set and `bound_box` basis as `contract_core/validate.py` `_pivot_findings`) and translates mesh data in each object's local frame; `test_scn003_mobile_root_is_reseated_after_decimation` (UV sphere, 200-tri budget) asserts origin and bottom centre within 1e-3 and no `pivot.bottom_center` |
| AC4 | Desktop cleanup removes non-manifold-edge and duplicate faces | Pass | `cleanup.py` `cleanup_desktop` calls `clean_mesh`; `_delete_repeated_faces` keeps the first face per vertex set; `test_scn004_cleanup_removes_non_manifold_and_duplicate_faces` asserts 15 -> 13 tris, one face for the pair, sliver tip gone |
| AC5 | Re-import triangle counts match | Pass | `test_scn005_reimport_triangle_counts_match` runs cleanup, optimize, `export_variants`, and `run_isolated` per variant; no `reimport.tris` for Desktop or Mobile |
| AC6 | Budgets, skinning, layout preserved | Pass | `_reseat` only calls `obj.data.transform`, so objects, parents, the LodGroup Empty, modifiers and vertex groups are untouched. Three `test_scn006_*` tests cover the rigged chain (Armature modifier, vertex groups, parent `SK_Hero`), the unrigged LodGroup, and the multi-part LOD0-only layout. Each also checks that `lod_tris` equals the mesh counts |
| AC7 | Clean meshes unchanged | Pass | `_reseat` returns early when the offset is exactly zero; `test_scn007_clean_asset_keeps_triangles_and_is_deterministic` (two identical runs) and `test_scn007_mobile_already_on_origin_is_not_translated` pass |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Share one clean routine | Complete | `meshes.clean_mesh` with the specified step order; `cleanup.py` no longer defines `_clean_mesh` or the 1e-10 constant; `_drop_duplicate_faces` removed |
| T002 | Clean every fit_meshes result | Complete | Under-budget copies and every decimated candidate are cleaned before the target comparison; rejected copies are freed |
| T003 | Re-seat the Mobile variant | Complete | `_reseat` called at the end of `build_mobile`, covering all three layouts |
| T004 | Document the clean and re-seat | Complete | `docs/asset-contract.md` §5 Variants bullet; CHANGELOG entry ending `(#140)`. Delivery has already moved it from `[Unreleased]` into `[0.21.2]` |
| T005 | Blender regression coverage | Complete | `tests/blender/test_variants_clean.py`: 10 tests mapped to SCN001-SCN007 |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | `clean_mesh` composes small private steps (`_drop_non_manifold_faces`, `_delete_repeated_faces`, `_delete_loose`); `_reseat` and `_world_bounds_corners` are separate |
| Open/Closed | 5 | The layout builders are unchanged; the re-seat is one post-step |
| Liskov Substitution | 5 | N/A beyond the consistent `fit_meshes` contract (fresh meshes, total <= target) |
| Interface Segregation | 5 | `cleanup.py` imports only the helpers it uses |
| Dependency Inversion | 5 | `variants_core` keeps its own copy of the contract constants rather than importing `contract_core` (per the design's Alternatives) |

### Layer Separation

The change stays inside the step-implementation layer (`plugins/nmg-game-dev-blender-addon/variants_core/`). `contract_core/` is unchanged, as the spec requires.

### Dependency Flow

`cleanup.py` and `mobile.py` depend on `meshes.py`. No new cross-package imports.

---

## Security Assessment

No input from outside the scene, no subprocesses, no file or network I/O added. Score 5.

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: mesh data only
- [x] Injection prevention: N/A
- [x] Data protection: N/A

## Performance Assessment

- [x] Async patterns: N/A (runs in background Blender per the long-running-work rule)
- [x] Caching: unchanged
- [x] Resource management: bmesh freed in `finally`; rejected `fit_meshes` copies are removed from `bpy.data`
- [x] Complexity: `clean_mesh` is linear in faces and edges per pass, except `_drop_non_manifold_faces`, which repeats only while non-manifold edges remain. Each candidate of each decimation pass now gets one extra bmesh round trip, a small cost next to the decimate modifier evaluation. Score 4.

## Error Handling

No new failure modes. The `fit_meshes` unreachable-target error is unchanged. `_reseat` returns early on empty geometry, and `_world_bounds_corners` handles meshes with no vertices. Score 4.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (`test_scn001_*`) | Yes |
| AC2 | Yes (SCN002) | Yes (`test_scn002_*`) | Yes |
| AC3 | Yes (SCN003) | Yes (`test_scn003_*`) | Yes |
| AC4 | Yes (SCN004) | Yes (`test_scn004_*`) | Yes |
| AC5 | Yes (SCN005) | Yes (`test_scn005_*`) | Yes |
| AC6 | Yes (SCN006) | Yes (3 `test_scn006_*`) | Yes |
| AC7 | Yes (SCN007) | Yes (2 `test_scn007_*`) | Yes |

### Coverage Summary

- Feature file: `specs/140-.../feature.gherkin`, 7 scenarios (manual QA scripts)
- Headless Blender tests: 10 new in `tests/blender/test_variants_clean.py`; 189 passed in `gate-blender-headless`
- Python unit + BDD: 969 passed, 9 skipped (`repository.tests`)

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. No nmg-sdlc `workflows/` or `agents/` paths changed, and no skill changed. `plugin.validate` and `plugin.session-smoke` cover the plugin manifest version bump |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 969 passed, 9 skipped |
| `repository.lint` | Pass | `ruff check .`: All checks passed |
| `repository.format` | Pass | `ruff format --check .`: 310 files already formatted |
| `repository.types` | Pass | `mypy src tests`: no issues in 197 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 189 passed in 262.59 s |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against UE 5.8, Result: Succeeded (applies because the `.uplugin` `VersionName` changed) |
| `gate-mcp-schema` | Not applicable | No `mcp-servers/**` change |
| `gate-shellcheck` | Not applicable | No `scripts/**.sh` change |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .`: Validation passed with warnings |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 8/8 applicable gates passed, 0 failed, 0 incomplete (3 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| - | - | - | None required | - | - |

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
| **Category** | Architecture |
| **Location** | `plugins/nmg-game-dev-blender-addon/variants_core/mobile.py` `_reseat` |
| **Issue** | The design says to measure world vertex positions, but the code measures the world-transformed corners of each object's local bounding box. That is the basis `_pivot_findings` uses (`obj.bound_box`), so it matches the contract more closely. The two agree for unrotated objects |
| **Impact** | None on the tests; it improves agreement with the contract for rotated parts |
| **Reason Not Fixed** | Not a defect. Recorded as a spec drift note |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Architecture |
| **Location** | `plugins/nmg-game-dev-blender-addon/variants_core/mobile.py` `_reseat` |
| **Issue** | On rigged assets the Mobile meshes shift by the pivot drift (at most millimetres) while the bones stay put |
| **Impact** | Sub-millimetre to millimetre skin offset against bones; the design accepts this |
| **Reason Not Fixed** | Within the approved design's blast radius |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `tests/blender/test_variants_clean.py` `decimation_leaks_zero_area` |
| **Issue** | SCN001 injects the zero-area face into `decimated_copy` output with monkeypatch, because collapse decimation does not reliably produce one on the fixtures |
| **Impact** | The test proves `fit_meshes` cleans each candidate, but not that a natural decimation repro is covered |
| **Reason Not Fixed** | A deterministic natural repro is not available. The injection exercises the exact code path the fix changes |

---

## Positive Observations

- One clean routine, with one zero-area threshold equal to the contract's, removes the Desktop/Mobile mismatch at its source.
- Under-budget copies are cleaned before the budget comparison, so `lod_tris` and `tris_after` report what the FBX keeps.
- `_reseat` leaves objects, parents, and the rig binding alone, which keeps `transform.root_applied` and skinning intact.
- The guard tests (AC6, AC7) pin the existing layouts and determinism.

## Recommendations Summary

### Before PR (Must)
- [x] None

### Short Term (Should)
- [ ] Update the design note to say the re-seat measures bounding-box corners, matching `_pivot_findings`.

### Long Term (Could)
- [ ] Add a natural decimation fixture that produces a zero-area face, if one can be made deterministic.

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/variants_core/meshes.py` | 0 | Shared `clean_mesh`, cleaned `fit_meshes` |
| `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py` | 0 | Uses `clean_mesh` |
| `plugins/nmg-game-dev-blender-addon/variants_core/mobile.py` | 2 (low) | `_reseat`, `_world_bounds_corners` |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 0 | Read-only reference for the pivot rule |
| `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` | 0 | Read-only reference for zero-area and normals rules |
| `tests/blender/test_variants_clean.py` | 1 (low) | 10 tests, SCN001-SCN007 |
| `docs/asset-contract.md` | 0 | FR7 bullet |
| `CHANGELOG.md`, `VERSION`, manifests | 0 | 0.21.2 patch bump (bug label) |

---

## Recommendation

**Ready for PR**

Every AC, FR, and task is implemented with passing headless Blender evidence, and every applicable registered gate passed at the verification head, so the verdict is Pass.
