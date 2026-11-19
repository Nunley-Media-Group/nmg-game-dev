# Verification Report: Let finalize fix or tolerate a millimetre-scale pivot bottom-center offset on rigged meshes

**Date**: 2026-11-19
**Issue**: #244
**Reviewer**: Claude (nmg-sdlc verify worker, gate phase)
**Scope**: Implementation verification against spec

**Verification head**: f39a344bf4e03ffc9feb1666ac692f85623c844c

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 5 |
| Testability | 4 |
| Error Handling | 5 |
| **Overall** | 4.7 |

### Implementation Status: Pass
**Total Issues**: 3 (all `info`, none blocking)

The review (`.nmg-sdlc/verification/244-review.md`, full mode, reviewed head `e542ccc`) passed with no finding above `info`. Since that review the branch only gained the merge of `main` and the version-preparation commit. The gate phase ran the pre-merge steering validations once at the verification head. Every applicable required validation passed, and coverage is complete (11 declared, 11 recorded).

### Deterministic steering artifact and ceiling

- Artifact: `.nmg-sdlc/verification/244.json` (run `17415cf7-bdfe-4cc6-a6a8-6636ae6e7f02`, tree clean, head `f39a344bf4e03ffc9feb1666ac692f85623c844c`)
- Ceiling: none
- Coverage: declared 11, recorded 11, complete `true`; missing, duplicate and unknown are all empty

---

## Issue Scope

- Active issue: #244
- Spec: `specs/244-let-finalize-fix-or-tolerate-a-millimetre-scale-pivot-bottom-center-offset-on-rigged-meshes`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5, AC6]; FR [FR1, FR2, FR3, FR4, FR5]; tasks [T001, T002, T003, T004]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005, SCN006]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":244,"specPath":"specs/244-let-finalize-fix-or-tolerate-a-millimetre-scale-pivot-bottom-center-offset-on-rigged-meshes","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5"],"tasks":["T001","T002","T003","T004"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Acceptance Criteria Verification

The evidence comes from the review record. Every criterion was exercised through the real entry point under headless Blender (`tests/blender/test_pivot_reseat.py`). No criterion's tests mock the path under test.

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Rigged Desktop mesh with a millimetre-scale bottom-center offset passes and is re-seated | Pass | `contract_core/validate.py` (rigged authored allowance `RIGGED_PIVOT_TOLERANCE` 5 mm), `variants_core/cleanup.py` `reseat_desktop`; `test_scn001` |
| AC2 | Re-seat moves mesh data only, without changing transforms, modifiers, weights or bones | Pass | `variants_core/cleanup.py` translates only `obj.data`; `test_scn002` |
| AC3 | An on-origin rig is left untouched | Pass | `reseat_desktop` returns `{reseated: False, offset: [0,0,0]}`; `test_scn003` |
| AC4 | An offset over 5 mm fails with an actionable message | Pass | `_pivot_findings` adds the 5 mm remedy; `test_scn004` |
| AC5 | Static assets keep the 1 mm tolerance and are never re-seated | Pass | `_has_rig` false keeps `PIVOT_TOLERANCE`; `test_scn005` |
| AC6 | Exported Desktop/Mobile pass export-time and re-import pivot checks | Pass | `test_scn006` (cleanup, mobile, export, `run_isolated`) |

FR1 to FR5, the design paths (DP1 to DP5) and the consumers (CN1 to CN5) all passed. See `.nmg-sdlc/verification/244-review.md`.

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Rigged authored pivot allowance in contract validation | Complete | `contract_core/validate.py`, `contract_core/report.py` |
| T002 | Desktop re-seat in the variants step | Complete | `variants_core/cleanup.py`, `finalize_core/steps.py` (`pivot` output) |
| T003 | Asset contract documentation | Complete | `docs/asset-contract.md` section 2 |
| T004 | Headless Blender tests SCN001 to SCN006 | Complete | `tests/blender/test_pivot_reseat.py` |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Validation decides tolerance, and cleanup does the re-seat |
| Open/Closed | 4 | Rigged allowance added beside the existing tolerance, not in place of it |
| Liskov Substitution | 5 | n/a; no substitutable hierarchy changed |
| Interface Segregation | 5 | `cleanup_desktop` gains one additive `pivot` output key |
| Dependency Inversion | 4 | `_has_rig` duplicates `asset_armature` to avoid a contract_core to variants_core import cycle (documented) |

### Layer Separation

The changes stay inside the Blender add-on step cores (`contract_core`, `variants_core`, `finalize_core`). The pipeline reads only its existing output keys, so the added `pivot` key breaks no reader.

### Dependency Flow

`variants_core/cleanup.py` imports the shared `bottom_center` and `pivot_meshes` helpers. `contract_core` does not import `variants_core`, so there is no cycle.

---

## Security Assessment

- [x] Authentication: n/a (no external services)
- [x] Authorization: n/a
- [x] Input validation: offsets are bounded by the 5 mm allowance before any data moves
- [x] Injection prevention: n/a
- [x] Data protection: mesh data only, in the background-Blender checkpoint

## Performance Assessment

- [x] Async patterns: n/a (runs inside the background Blender variants step)
- [x] Caching: unchanged
- [x] Resource management: one matrix transform per asset mesh
- [x] Query optimization: n/a

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (`test_scn001`) | Yes |
| AC2 | Yes (SCN002) | Yes (`test_scn002`) | Yes |
| AC3 | Yes (SCN003) | Yes (`test_scn003`) | Yes |
| AC4 | Yes (SCN004) | Yes (`test_scn004`) | Yes |
| AC5 | Yes (SCN005) | Yes (`test_scn005`) | Yes |
| AC6 | Yes (SCN006) | Yes (`test_scn006`) | Yes |

### Coverage Summary

- Feature file: 6 scenarios (`specs/.../feature.gherkin`)
- Step definitions: implemented as headless Blender tests (`tests/blender/test_pivot_reseat.py`)
- Executed by `gate-blender-headless` (passed)

---

## Steering Doc Verification Gates

None of these validations declares a tier, so every one records `tier: null` and `selection: null`.

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | `uv run pytest tests/unit tests/bdd -q`, which exited 0 |
| repository.lint | Pass | `uv run ruff check .`, which exited 0 |
| repository.format | Pass | `uv run ruff format --check .`, which exited 0 |
| repository.types | Pass | `uv run mypy src tests`, which exited 0 |
| gate-blender-headless | Pass | `scripts/run-blender-tests.sh`, which exited 0 |
| gate-godot-headless | Pass | `scripts/run-godot-tests.sh`, which exited 0 (it applies because `main` was integrated, including the plugin.cfg version) |
| gate-mcp-schema | Not applicable | No `mcp-servers/**` change |
| gate-shellcheck | Not applicable | No `scripts/**.sh` change |
| gate-ship-smoke | Not applicable | No ship-path change |
| plugin.validate | Pass | `claude plugin validate .`, which exited 0 |
| plugin.session-smoke | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 8/8 applicable gates passed, 0 failed, 0 incomplete (3 not applicable)

No `nmg-sdlc-smoke` validation is registered for this repository. The `plugin.session-smoke` extension passed.

---

## Fixes Applied

None. The review ran under `/sdlc-execute`, so the verify stage made no source edits.

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Medium Priority
None.

### Low Priority (info notes from the review)

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Info | Spec Compliance | `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py` | F1: an offset that rounds to zero at 1 micrometre counts as zero, where FR3 says "exactly zero" | Deliberate. The docstring explains the float32-noise rationale, and AC3 holds |
| Info | Error Handling | `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py` | F2: LOD copies are moved with the root while only non-LOD meshes are measured | Keeps the LODs aligned. Shared mesh data is already rejected by authored validation |
| Info | Testing | `tests/blender/test_pivot_reseat.py` | F3: no test asserts that the `_variants` outputs carry `pivot`, or that a rigged root origin 1 to 5 mm off still fails | Both are clear from reading the code; not a defect |

---

## Positive Observations

- The re-seat transforms only mesh data through the inverse of each object's world rotation and scale. Skin binding, parenting and bones are preserved, and `test_scn002` proves it.
- The allowance is scoped tightly to the rigged Desktop variant at authored time. Export-time, Mobile and static checks keep the 1 mm contract.
- The end-to-end test `test_scn006` runs the real export and isolated re-import cores.

---

## Recommendations Summary

### Before PR (Must)
- None

### Short Term (Should)
- None

### Long Term (Could)
- [ ] Add the F3 test coverage (the `pivot` output key and a rigged root origin offset)

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py` | 2 (info) | F1, F2 |
| `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py` | 0 | |
| `docs/asset-contract.md` | 0 | |
| `tests/blender/test_pivot_reseat.py` | 1 (info) | F3 |

---

## Recommendation

**Ready for PR**

Every acceptance criterion and functional requirement is met and exercised through the real entry point. Every applicable required gate passed at the verification head, with complete coverage.
