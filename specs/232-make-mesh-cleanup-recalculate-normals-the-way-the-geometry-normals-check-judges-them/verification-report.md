# Verification Report: Make mesh cleanup recalculate normals the way the geometry.normals check judges them

**Date**: 2026-11-18
**Issue**: #232
**Reviewer**: Claude (nmg-sdlc verify worker, gate phase)
**Scope**: Implementation verification against spec

**Verification head**: 5911683850349b440f8aadbfa644c61d93f2aa8a

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.7 |

### Implementation Status: Pass
**Total Issues**: 3 (all `info`; none blocking, major or minor)

The review passed at `6d38bffa34422071cfac6be60a8f4b6c39b11fed` (scoped, after a repair of the first review's findings). The verification head adds only the release-preparation commit (VERSION 0.25.4, CHANGELOG, and the three version manifests) on top of the reviewed source, with `main` integrated. All 11 registered validations are recorded at the verification head: 8 applicable and passed, 3 not applicable to the changed paths.

---

## Issue Scope

- Active issue: #232
- Spec: `specs/232-make-mesh-cleanup-recalculate-normals-the-way-the-geometry-normals-check-judges-them`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5]; FR [FR1, FR2, FR3, FR4]; tasks [T001, T002, T003]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":232,"specPath":"specs/232-make-mesh-cleanup-recalculate-normals-the-way-the-geometry-normals-check-judges-them","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5"],"functionalRequirements":["FR1","FR2","FR3","FR4"],"tasks":["T001","T002","T003"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact

- Artifact: `.nmg-sdlc/verification/232.json`
- Identity: head `5911683850349b440f8aadbfa644c61d93f2aa8a`, tree clean, steering `sha256:7db2c1fd212d4f84230398c629c1291687ccdac34fa35a2bc469460279b5bc93`, spec `sha256:2dcf365ffd8c25586a8b92fd6bb35fa1564aa5dc771a21c3f5368b89bf58c060`
- Ceiling: none
- Coverage: declared 11, recorded 11, complete `true`; no missing, duplicate or unknown results
- Tier: the project declares no tiers, so every applicable required validation ran (`tier: null`, `selection: null` on every result)

---

## Acceptance Criteria Verification

Evidence is from the review record `.nmg-sdlc/verification/232-review.json`. Every criterion is exercised through the real entry point (`clean_mesh`, `cleanup_desktop`, `optimize_mobile`, `contract.validate_asset`) in headless Blender. No criterion's tests mock the path under test.

| AC | Description | Status | Exercised | Evidence |
|----|-------------|--------|-----------|----------|
| AC1 | Cleanup output never fails geometry.normals | Pass | real entry point | `variants_core/meshes.py` `clean_mesh` ends in `_settle_normals`, which returns only when `normal_violations` on a from_mesh probe flags nothing; `tests/blender/test_clean_normals.py` SCN001 reproduces the failure with the pre-fix steps and shows none after `clean_mesh`. Pre-fix probe: SCN001-SCN004 fail on main's `meshes.py`. |
| AC2 | A mesh that passes validate still passes after Desktop cleanup | Pass | real entry point | SCN002: collection Klein/SM_Klein has no `geometry.*` findings before and after `variants_core.cleanup_desktop`. |
| AC3 | Mobile LODs never introduce geometry.normals failures | Pass | real entry point | SCN003: `cleanup_desktop` then `optimize_mobile('Klein','standard_prop')`; no `geometry.normals` on SM_Klein_Mobile LOD0-LOD2. `fit_meshes` cleans every candidate through `clean_mesh`. |
| AC4 | Faces with no consistent orientation are removed deterministically | Pass | real entry point | SCN004 compares two identical runs (positions, face vertex lists, normals); `test_scn004_each_pass_deletes_only_the_faces_it_flagged` asserts each settle pass deletes exactly the flagged faces. Mutation probes (over-deletion, off-by-one index) are caught. |
| AC5 | Normals rule and existing clean behavior are preserved | Pass | real entry point | SCN005 x3: open quad passes; inside-out cube repaired to 6 outward faces; `build_crate` keeps its triangle count with no `geometry.*` finding. Neighbour suites pass (test_geometry_normals, test_variants_clean, test_contract_validate). |

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `contract_core/geometry.py` `recalc_island_normals` (per island, in `_islands` order) and public `normal_violations`, used by both `geometry_findings` and `clean_mesh`. |
| FR2 | Pass | `variants_core/meshes.py` `_settle_normals` loop: recalc, write, probe, delete flagged faces, delete loose, repeat until none flagged. |
| FR3 | Pass | Desktop cleanup and Mobile fitting both route through `clean_mesh`; SCN002 and SCN003. |
| FR4 | Pass | Klein bottle fixtures and SCN001-SCN005 in `tests/blender/test_clean_normals.py`, tags 1:1 with `feature.gherkin`. |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Share the per-island normal recalculation | Complete | `recalc_island_normals`, `normal_violations` in `contract_core/geometry.py` |
| T002 | Settle normals in clean_mesh | Complete | `_settle_normals` in `variants_core/meshes.py`; `docs/asset-contract.md` documents the deletion |
| T003 | Add regression coverage | Complete | `tests/blender/test_clean_normals.py` (8 tests) |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Normal recalculation and the normals rule live in `contract_core`; `variants_core` only composes them |
| Open/Closed | 5 | `geometry_findings` keeps its output; the shared routine is additive |
| Liskov Substitution | 5 | Not applicable beyond unchanged call signatures |
| Interface Segregation | 5 | Two small public functions |
| Dependency Inversion | 5 | `variants_core` depends on the contract core, matching the layer direction in structure steering |

### Layer Separation

Both cores stay headless-safe step implementations; no pipeline, MCP or skill layer changed.

### Dependency Flow

`variants_core/meshes.py` imports from `contract_core/geometry.py`, so cleanup and the check cannot drift apart again. Consumers (CONS1-CONS7 in the review record) are unchanged callers or historical reports.

---

## Security Assessment

- [x] Authentication: not applicable (local geometry code)
- [x] Authorization: not applicable
- [x] Input validation: face indices resolved after `ensure_lookup_table`
- [x] Injection prevention: not applicable
- [x] Data protection: not applicable

---

## Performance Assessment

- [x] Async patterns: not applicable; runs in background Blender steps
- [x] Caching: unchanged
- [x] Resource management: probe and bmesh freed in `finally`
- [x] Query optimization: each settle pass adds one to_mesh/from_mesh round trip and island walks (info F3)

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

### Coverage Summary

- Feature file: `feature.gherkin`, 5 scenarios, implemented as headless Blender tests per tech steering
- Blender headless suite at the verification head: 390 passed, 4 skipped
- Python unit + BDD suite at the verification head: 1722 passed, 14 skipped

---

## Exercise Test Results

Not applicable: the change touches no `workflows/` or `agents/` plugin skills. The plugin manifest change (version only) is covered by `plugin.validate` and `plugin.session-smoke` below.

---

## Steering Doc Verification Gates

Each result is from `.nmg-sdlc/verification/232.json` at head `5911683850349b440f8aadbfa644c61d93f2aa8a`. Tier `null` and selection `null` for every result (no tiers declared).

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | `uv run pytest tests/unit tests/bdd -q`: 1722 passed, 14 skipped |
| repository.lint | Pass | `uv run ruff check .`: All checks passed |
| repository.format | Pass | `uv run ruff format --check .`: 418 files already formatted |
| repository.types | Pass | `uv run mypy src tests`: no issues in 265 source files |
| gate-blender-headless | Pass | `scripts/run-blender-tests.sh`: 390 passed, 4 skipped |
| gate-ue-compile | Pass | `project.ue-compile`: DogfoodEditor compiled against UE 5.8 (applies via the `.uplugin` version change) |
| gate-mcp-schema | Not applicable | No `mcp-servers/**` or `scripts/validate-mcp-tools.py` change |
| gate-shellcheck | Not applicable | No `scripts/**.sh` change |
| gate-ship-smoke | Not applicable | No ship path change |
| plugin.validate | Pass | `claude plugin validate .`: validation passed (with pre-existing warnings) |
| plugin.session-smoke | Pass | `project.plugin-session-smoke`: plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 8/8 applicable gates passed, 0 failed, 0 incomplete; 3 not applicable

---

## Fixes Applied

None in the gate phase. Review findings F1 (asset contract did not document face deletion) and F4 (no test that each pass deletes only flagged faces) were repaired by implement in `6d38bff` and confirmed by the scoped review.

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
| **Severity** | Low (info F2) |
| **Category** | Error Handling |
| **Location** | `plugins/nmg-game-dev-blender-addon/variants_core/meshes.py` |
| **Issue** | Deletion can be broad on non-orientable islands (klein(32,16) lost 373 of 512 faces over 3 passes) |
| **Impact** | Such meshes lose much of a twisted island, as the approved design accepts |
| **Reason Not Fixed** | Within the approved design; targeted twist-seam repair is follow-up #243 |

| Field | Value |
|-------|-------|
| **Severity** | Low (info F3) |
| **Category** | Performance |
| **Location** | `plugins/nmg-game-dev-blender-addon/variants_core/meshes.py`, `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` |
| **Issue** | Each settle pass adds a to_mesh/from_mesh round trip and two island walks (131072-face sphere 0.94 s to 3.94 s) |
| **Impact** | Within authoring budgets for standard props; watch hero assets |
| **Reason Not Fixed** | Info only |

| Field | Value |
|-------|-------|
| **Severity** | Low (info F5) |
| **Category** | Documentation |
| **Location** | `docs/asset-contract.md:169` |
| **Issue** | Line wraps at 114 chars, and "It then re-seats the Mobile variant" can read as referring to the deletion |
| **Impact** | Readability only; content is accurate |
| **Reason Not Fixed** | Info only |

---

## Positive Observations

- Cleanup and the contract check now share one recalculation routine, removing the drift that caused the bug.
- The regression fixture reproduces the original failure (4 tests fail on the pre-fix code) and mutation probes confirm the pass-alignment test catches over-deletion.

---

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- Follow-up #243: targeted twist-seam repair to reduce deletion on non-orientable islands.

### Long Term (Could)
- Measure settle cost on hero assets against the 5-minute finalize budget.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` | 1 (info F3) | Shared recalc and rule |
| `plugins/nmg-game-dev-blender-addon/variants_core/meshes.py` | 2 (info F2, F3) | Settle loop |
| `tests/blender/test_clean_normals.py` | 0 | Regression coverage |
| `docs/asset-contract.md` | 1 (info F5) | Consumer-facing doc |
| `VERSION`, `CHANGELOG.md`, `.claude-plugin/plugin.json`, `blender_manifest.toml`, `nmg-game-dev.uplugin` | 0 | Release preparation 0.25.4 |

---

## Recommendation

**Ready for PR**

Every acceptance criterion and functional requirement passes through the real entry point. The review found nothing above `info`, and all applicable registered validations passed at the verification head with coverage complete.
