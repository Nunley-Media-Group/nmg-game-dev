# Verification Report: estimate_landmarks proposes rig_humanoid landmarks from the mesh

**Date**: 2026-11-11
**Issue**: #137
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Implementation verification against spec

**Verification head**: 628b99626e1447e2094ceaf56fa0951ed1ec08c9

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
**Total Issues**: 3 (all Low, none blocking)

`estimate_landmarks(collection_name)` is in `rig_core`. A pure-Python slicing core (`rig_core/slicing.py`, no `bpy`) does the estimate, and a thin `bpy` wrapper (`rig_core/estimate.py`) reads the vertices. `rig_humanoid` now reads current transforms and names the real mesh in its failure texts. The agent flow is documented. All 10 acceptance criteria have passing tests. This is a fresh verification after `628b996 chore: merge origin/main into #137 branch`. The merge changed no #137 feature file (`rig_core/`, the estimate tests and fixtures, the docs and the docs guard are identical to the previous verification head `12c3680`). It took main's version files (0.21.3) and kept #137's CHANGELOG entry under `## [Unreleased]`. All 10 applicable registered validations passed at the verification head, and steering coverage is complete (11 declared, 11 recorded, 1 not applicable).

---

## Issue Scope

- Active issue: #137
- Spec: `specs/137-add-estimate-landmarks-to-propose-rig-humanoid-landmarks-from-the-mesh`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC10]; FR [FR1–FR13]; tasks [T001–T006]; scenarios [SCN001–SCN010]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":137,"specPath":"specs/137-add-estimate-landmarks-to-propose-rig-humanoid-landmarks-from-the-mesh","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9","AC10"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10","FR11","FR12","FR13"],"tasks":["T001","T002","T003","T004","T005","T006"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009","SCN010"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 137 --spec specs/137-… --base main --controller-run-id 20cb1e59-479a-4327-9267-2e86778a0af4`
- Artifact: `.nmg-sdlc/verification/137.json`, generated 2026-11-11T23:53:57Z
- Identity: head `628b99626e1447e2094ceaf56fa0951ed1ec08c9`, tree clean, specHash `sha256:04648d9a…6417435`, steeringHash `sha256:119992c8…5096a9`
- Result: `ok: true`, `ceiling: null`
- Coverage: declared 11, recorded 11, complete `true`; nothing missing, duplicated, or unknown
- Note: the local `main` ref used as `--base` is behind `origin/main`, so the changed-path set includes paths from earlier merges. That made more gates applicable (`gate-mcp-schema`, `gate-shellcheck`, `gate-ue-compile`), and all of them passed. It only widens the gate set.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | An A-pose humanoid gets all 19 landmarks, `ok`/`high`, each within 5% H, correct sides | Pass | `rig_core/slicing.py` `propose`; `tests/blender/test_estimate_landmarks.py::test_scn001_*` passes |
| AC2 | A high-confidence proposal rigs without edits | Pass | `test_scn002_*`: `rig_humanoid` returns `ok` on the unchanged proposal |
| AC3 | Stylized proportions and accessories do not mislead it | Pass | `_arm_chain`/`_follow` reject side intervals whose chain is shorter than 0.12n; `test_scn003_*[hat_brim, earrings, glasses]` pass |
| AC4 | An asymmetric stance gives `low`, measured per side, with a warning naming each pair | Pass | `_mirror_warnings` (no averaging); `test_scn004_*[arm, leg]` checks the warning count, the pair names, and measured-not-averaged |
| AC5 | No A-pose arms, or no crotch, is a failure with no landmarks | Pass | `_arms_missing`/`_crotch_missing` raise `RigError`, and `estimate.py` returns `error.result`; `test_scn005_*[t-pose, fused-arms, no-crotch]` pass |
| AC6 | A missing mesh is reported with the real name | Pass | `landmarks.asset_not_found` used by `estimate.py`; `test_scn006_*` checks `SM_Ghost` and `SM_Hollow` |
| AC7 | Estimating changes nothing | Pass | `estimate.py` only calls `view_layer.update()`, `evaluated_get().to_mesh()` and `to_mesh_clear()`; `test_scn007_*` snapshots objects, vertices, matrices, selection, mode, and active object for 4 cases |
| AC8 | `rig_humanoid` and the estimate use the current transform | Pass | `rig.py` `_mesh_bounds` and `estimate.py` `_world_vertices` call `view_layer.update()` first; `test_scn008_*` moves, rotates, and scales the mesh with no update |
| AC9 | `rig_humanoid` messages name `SM_Hero` / `Hero` | Pass | `landmarks.py` (`asset_not_found`, `landmarks_outside_mesh`) and `rig.py` (`weights_failed`); `test_scn009_*`. A grep of `rig_core/*.py` finds `<Name>` only in docstrings |
| AC10 | The agent flow is documented | Pass | `docs/rigging-and-animation.md` Agent flow steps 2–4, "Estimating landmarks", and Result statuses; `tests/unit/test_rigging_docs.py` passes in `repository.tests` |

### Functional requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `rig_core/__init__.py` exports `estimate_landmarks`; the result uses the `outcome.ok`/`fail` shape |
| FR2 | Pass | `propose` returns all `LANDMARK_KEYS` as float triples, plus `confidence` and `warnings` |
| FR3 | Pass | `SLICE_COUNT = 200`, `GAP_FRACTION = 0.012`, `_intervals` |
| FR4 | Pass | `_find_crotch`: band [0.15n, 0.70n], `CROTCH_HOLD = 6` |
| FR5 | Pass | `_find_armpit` from `0.92n - 1` downward, with arm chains of at least `round(0.12n)` |
| FR6 | Pass | `_arm_landmarks`: least-squares fit over the middle 60% of the chain, with fractions 0.47/0.80/0.985 |
| FR7 | Pass | `_neck`, `_leg_landmarks`, `_toe`, `_pelvis`, `_head_top` |
| FR8 | Pass | `_mirror_warnings`, `MIRROR_TOLERANCE = 0.05` |
| FR9 | Pass | A failure is a `RigError` result with no `landmarks` key |
| FR10 | Pass | SCN007 |
| FR11 | Pass | `view_layer.update()` in `_mesh_bounds` and `_world_vertices`; SCN008 |
| FR12 | Pass | SCN009 |
| FR13 | Pass | SCN010 |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Slicing core | Complete | `rig_core/slicing.py`; imports only `outcome` and `skeleton`, no `bpy` |
| T002 | `estimate_landmarks` in `rig_core` | Complete | `rig_core/estimate.py`, `rig_core/__init__.py` |
| T003 | Current transforms and real names in `rig_humanoid` | Complete | `rig.py`, `landmarks.py`; `validate` gains `collection_name`, and all callers are updated (`rig.py`, `tests/bdd/test_meshy_bdd.py`, `tests/blender/test_meshy_session.py`); symmetry, order, and pose limits are unchanged |
| T004 | Estimation fixtures | Complete | `tests/blender/landmark_fixtures.py` `build_a_pose(...)` with every listed variant; `rig_fixtures.build_hero` gains `voxel_size` |
| T005 | Blender tests | Complete | `tests/blender/test_estimate_landmarks.py`: SCN001–SCN009 and the 100,000-vertex timing test. The SCN009 test is in this file, not in `test_rig_humanoid.py` (see Remaining Issues) |
| T006 | Docs and docs guard | Complete | `docs/rigging-and-animation.md`, `tests/unit/test_rigging_docs.py` |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | The geometry (`slicing.py`) is apart from scene access (`estimate.py`). Each landmark group has its own helper |
| Open/Closed | 4 | The tuning constants are named module-level values. A new body type would need a new core, which is out of scope |
| Liskov Substitution | 5 | N/A beyond the result-dict contract, which is kept |
| Interface Segregation | 5 | `propose(points)` takes plain coordinates, so it can be tested without Blender |
| Dependency Inversion | 5 | The core depends only on `outcome`/`skeleton`, and the `bpy` adapter depends on the core |

### Layer Separation

Matches structure steering. `rig_core` is the add-on's step implementation. The pure core is headless-safe, and the `bpy` access sits in one thin wrapper. No skill, MCP, or pipeline layer is touched.

### Dependency Flow

`estimate.py` → `slicing.py` → `outcome`, `skeleton`. `estimate.py` → `landmarks.asset_not_found` reuses the same failure text as `rig_humanoid`, so the two cannot drift. There are no cycles.

---

## Security Assessment

The change is local geometry only: no network, credentials, file I/O, subprocess calls, or dynamic code.

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: an unknown collection or mesh returns `rig.asset_not_found`; an empty or zero-height point set raises `rig.crotch_not_found`
- [x] Injection prevention: N/A, since collection names are only formatted into messages
- [x] Data protection: N/A

## Performance Assessment

- [x] Async patterns: N/A. It is a synchronous call, well under the 180 s MCP limit
- [x] Caching: N/A
- [x] Resource management: `to_mesh_clear()` runs in a `finally` for each mesh
- [x] Query optimization: bucketing is linear, with a sort per slice. The 100,000-vertex test runs well under 60 s. `_toe` scans all points once per side, which is still linear. The doc notes that a pure-Python loop over very dense meshes (millions of vertices) will be slower. That is acceptable for a call made once per character

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | SCN001 | Yes (Blender pytest) | Yes |
| AC2 | SCN002 | Yes | Yes |
| AC3 | SCN003 | Yes (3 params) | Yes |
| AC4 | SCN004 | Yes (2 params) | Yes |
| AC5 | SCN005 | Yes (3 params) | Yes |
| AC6 | SCN006 | Yes | Yes |
| AC7 | SCN007 | Yes (4 params) | Yes |
| AC8 | SCN008 | Yes | Yes |
| AC9 | SCN009 | Yes | Yes |
| AC10 | SCN010 | Yes (unit) | Yes |

### Coverage Summary

- Feature file: 10 scenarios, 10 of 10 ACs covered
- Blender tests: 18 in `test_estimate_landmarks.py` (all pass; rerun alone through `scripts/run-blender-tests.sh tests/blender/test_estimate_landmarks.py`: 18 passed in 21.15 s). Full Blender suite: 231 passed in the registered gate
- Unit tests: 11 in `test_rigging_docs.py`. Full `tests/unit tests/bdd`: 1064 passed, 9 skipped

### Blender test isolation (lane host evidence)

Six lane worktrees share one Blender user add-on link, and `scripts/blender/_runner.py` re-links it to the running checkout before tests start. Every test in `test_estimate_landmarks.py` imports `rig_core.estimate`, which exists only on this branch, so the 18 passes (in the full gate and in the targeted rerun) could only come from lane-5's code. The previous verification also ran an isolated `BLENDER_USER_RESOURCES` pass (193 passed, 4 host-only skips). The feature files have not changed since then.

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 1064 passed, 9 skipped in 124.00 s |
| `repository.lint` | Pass | `uv run ruff check .`: All checks passed |
| `repository.format` | Pass | `uv run ruff format --check .`: 324 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: no issues found in 205 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 231 passed in 177.18 s |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against UE 5.8 (`Build.sh DogfoodEditor Mac Development`) |
| `gate-mcp-schema` | Pass | `uv run python scripts/validate-mcp-tools.py`: passed |
| `gate-shellcheck` | Pass | `shellcheck -S style` on every `scripts/**.sh`: passed |
| `plugin.validate` | Pass | `claude plugin validate .`: validation passed (with warnings) |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir`, and `nmg-game-dev:blender` connected |
| `gate-ship-smoke` | Not applicable | No ship-path change |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

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
| **Location** | `tests/blender/test_estimate_landmarks.py:255` |
| **Issue** | T005 lists `tests/blender/test_rig_humanoid.py` as a file to modify. SCN009 and SCN008 were put in `test_estimate_landmarks.py` instead |
| **Impact** | None on coverage. The `rig_humanoid` message tests sit beside the estimate tests, not with the other `rig_humanoid` tests |
| **Reason Not Fixed** | Cosmetic. The publication scope for verify allows writing only the verification report |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Architecture |
| **Location** | `plugins/nmg-game-dev-blender-addon/rig_core/slicing.py:350` (`_neck`) |
| **Issue** | The design says "the narrowest central interval". The code counts widths within one gap (0.012H) of the narrowest as equal and takes the lowest, which places the neck at its base |
| **Impact** | A small, documented refinement. It is covered by the AC1/AC3 tolerance checks |
| **Reason Not Fixed** | It is intended behaviour, explained in the docstring. A spec note could record it later |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `plugins/nmg-game-dev-blender-addon/rig_core/estimate.py:33` |
| **Issue** | Only `RigError` is turned into a result dict. An unexpected exception from the core would propagate to the caller |
| **Impact** | None found. All degenerate inputs that were reviewed (empty, zero height, missing legs, missing neck candidates) raise `RigError`. `_fit_line` always has at least 14 distinct z values |
| **Reason Not Fixed** | This matches the other `rig_core` entry points, and nothing currently triggers it |

---

## Positive Observations

- The pure geometry core can be reasoned about and tested without Blender. All tuning values are named constants that match the design.
- `asset_not_found` is shared between `estimate_landmarks` and `rig_humanoid`, so the AC6 and AC9 texts stay identical.
- The AC7 snapshot test is strong: it covers vertices, both matrices, selection, mode, modifiers, the mesh datablock list, and the active object, across ok, failure, and missing cases.
- The SCN004 test proves the landmarks are measured, not averaged, by comparing the result with both the known point and the mirror average.
- The docs explain the remesh-density failure mode (empty slices lead to `rig.crotch_not_found`).

---

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- None.

### Long Term (Could)
- [ ] Move the SCN008 and SCN009 `rig_humanoid` assertions into `test_rig_humanoid.py`, or update T005's file list, so the spec and the tests line up.
- [ ] Record the neck-base tie-break rule in design.md.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/rig_core/slicing.py` | 1 (Low) | New pure core |
| `plugins/nmg-game-dev-blender-addon/rig_core/estimate.py` | 1 (Low) | New `bpy` wrapper |
| `plugins/nmg-game-dev-blender-addon/rig_core/__init__.py` | 0 | Export |
| `plugins/nmg-game-dev-blender-addon/rig_core/landmarks.py` | 0 | `asset_not_found`; `validate(collection_name)` |
| `plugins/nmg-game-dev-blender-addon/rig_core/rig.py` | 0 | `view_layer.update()`; `weights_failed` text |
| `docs/rigging-and-animation.md` | 0 | Flow and contract |
| `tests/blender/landmark_fixtures.py` | 0 | Fixtures |
| `tests/blender/test_estimate_landmarks.py` | 1 (Low) | SCN001–SCN009, timing |
| `tests/blender/rig_fixtures.py` | 0 | `voxel_size` parameter |
| `tests/unit/test_rigging_docs.py` | 0 | SCN010 |
| `tests/bdd/test_meshy_bdd.py`, `tests/blender/test_meshy_session.py` | 0 | `validate` signature update |
| `VERSION`, `CHANGELOG.md`, `.claude-plugin/plugin.json`, `blender_manifest.toml`, `nmg-game-dev.uplugin` | 0 | After the merge of `origin/main`: main's values (0.21.3); the #137 entry sits under `## [Unreleased]`, and deliver prepares the version again |

---

## Recommendation

**Ready for PR**

Every acceptance criterion, functional requirement, and task is met, with passing tests at the verification head. `origin/main` has moved one commit (`0e2fa86`, a spec approval for #189) beyond the merged base; that is for deliver to reconcile and does not touch #137's code. All applicable registered gates passed and steering coverage is complete. The remaining items are Low and do not block.
