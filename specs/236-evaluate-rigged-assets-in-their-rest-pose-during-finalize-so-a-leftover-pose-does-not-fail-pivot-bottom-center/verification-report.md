# Verification Report: Evaluate rigged assets in their rest pose during finalize

**Date**: 2026-11-19
**Issue**: #236
**Reviewer**: nmg-sdlc verify worker (gate phase)
**Scope**: Pre-merge gate against the revised Approved spec (PR #281) as integrated from main
**Verification head**: d1b5c88648ef7f6abb8ed802148a6755609e415c

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 3 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 5 |
| Testability | 3 |
| Error Handling | 5 |
| **Overall** | 4.2 |

### Implementation Status: Fail
**Total Issues**: 2 (both must be fixed before merge)

All registered pre-merge validations that apply passed at the verification head: 8 passed, and 3 were skipped because the change does not touch their paths. The change itself is correct: the earlier review passed it, and the real-Blender proofs pass. The status is Fail because the delivery does not yet match the revised spec merged in PR #281:

1. Task T002 is incomplete. The committed BDD feature file still has the old SCN003 and SCN004 wording rather than the revised spec's `feature.gherkin`.
2. AC4 has an evidence gap. `test_scn004` never checks that the rig starts at `pose_position == 'POSE'`, so SCN004 does not show that `pose_position` is restored.

---

## Issue Scope

- Active issue: #236
- Spec: `specs/236-evaluate-rigged-assets-in-their-rest-pose-during-finalize-so-a-leftover-pose-does-not-fail-pivot-bottom-center`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5]; FR [FR1, FR2, FR3, FR4]; tasks [T001, T002]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":236,"specPath":"specs/236-evaluate-rigged-assets-in-their-rest-pose-during-finalize-so-a-leftover-pose-does-not-fail-pivot-bottom-center","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5"],"functionalRequirements":["FR1","FR2","FR3","FR4"],"tasks":["T001","T002"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Not complete. All validations pass, but T002 is incomplete and AC4's evidence has a gap.
- PR evidence: Not required

---

## Acceptance Criteria Verification

Evidence comes from the review record (`.nmg-sdlc/verification/236-review.md`), checked again against the revised spec. No criterion's tests mock the path under test: every proof runs in real headless Blender.

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | A leftover pose does not fail pivot.bottom_center | Pass | `contract_core/validate.py` wraps every check in `rest_pose`; `test_scn001` runs `validate_asset` on a posed hero (real entry point) |
| AC2 | Posed and cleared reports match | Pass | `test_scn002` compares the findings and the measured values |
| AC3 | Export and the reduce copy step do not bake the pose | Pass | `variants_core/export.py` and `reduce_core/decimate.py` `make_copy` run inside `rest_pose`; `test_scn003` checks the bounds and inverse bind matrices of the re-imported GLBs; `test_fr3_make_copy_evaluates_the_rest_pose` checks the copy's bounds |
| AC4 | The scene is left unchanged | **Partial** | `rest_pose` restores the state in `finally`, and `test_scn004` compares pose state before and after `validate_asset`, `export_variants` (including forced failures), and the `reduce.rigged` refusal. However, it never checks that the starting `pose_position` is `'POSE'`. A mutant that never restores `pose_position` passed SCN004, because the fixture's reseat already left the rig at REST. Only `test_fr3` caught it. |
| AC5 | Exporting clips does not leave a stray pose | Pass | `finalize_core/anims.py` restores each bone in `finally`; `test_scn005` |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Correct the root cause | Complete | `rest_pose.py`, `validate.py`, `decimate.py`, `export.py`, `cleanup.py` (`reseat_desktop`, FR3), `anims.py` |
| T002 | Add behavioral regression coverage | **Incomplete** | The task requires `tests/bdd/features/rest_pose_finalize.feature` to carry SCN001-SCN005 exactly as in the spec's `feature.gherkin`. It does not (see Remaining Issues R1). |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | One `rest_pose` context manager owns the evaluation state; callers only wrap it |
| Open/Closed | 4 | Existing steps are wrapped, not rewritten |
| Liskov Substitution | 5 | N/A, no inheritance |
| Interface Segregation | 4 | Two small functions: `deforming_armatures` and `rest_pose` |
| Dependency Inversion | 4 | `validate.py` imports lazily to avoid a cycle between `variants_core` and `contract_core` |

### Layer Separation

The changes stay inside the Blender add-on's step cores (`contract_core`, `variants_core`, `reduce_core`, `finalize_core`). No pipeline or skill layer changes.

---

## Security Assessment

- [x] Input validation: no new external input
- [x] Injection prevention: N/A
- [x] Data protection: no credentials or I/O changes

## Performance Assessment

- [x] Only one extra `view_layer.update()` per wrapped step, and none when there is no armature
- [x] Resource management: state is restored in `finally`

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes | Yes | Yes |
| AC2 | Yes | Yes | Yes |
| AC3 | Yes, but wording out of date (R1) | Yes | Yes |
| AC4 | Yes, but wording out of date (R1); starting state not checked (R2) | Yes | Yes |
| AC5 | Yes | Yes | Yes |

---

## Steering Doc Verification Gates

Runner: `sdlc-verify-steering.mjs --tier pre-merge`. Artifact: `.nmg-sdlc/verification/236.json`. Coverage: 11 declared, 11 recorded, complete. No validation declares a tier, so every result records `tier: null` and `selection: null`.

| Gate | Tier / Selection | Status | Evidence |
|------|------------------|--------|----------|
| repository.tests | null / null | Pass | `uv run pytest tests/unit tests/bdd -q` exited 0 |
| repository.lint | null / null | Pass | `uv run ruff check .` exited 0 |
| repository.format | null / null | Pass | `uv run ruff format --check .` exited 0 |
| repository.types | null / null | Pass | `uv run mypy src tests` exited 0 |
| gate-blender-headless | null / null | Pass | `scripts/run-blender-tests.sh` exited 0 |
| gate-godot-headless | null / null | Pass | `scripts/run-godot-tests.sh` exited 0 (`plugin.cfg` version bump) |
| gate-mcp-schema | null / null | Not applicable (skipped) | No `mcp-servers/**` paths changed |
| gate-shellcheck | null / null | Not applicable (skipped) | No `scripts/**.sh` paths changed |
| gate-ship-smoke | null / null | Not applicable (skipped) | No ship paths changed |
| plugin.validate | null / null | Pass | `claude plugin validate .` exited 0 |
| plugin.session-smoke | null / null | Pass | Plugin loaded with `--plugin-dir`; the `nmg-game-dev:blender` server connected |

**Gate Summary**: 8 of 8 applicable gates passed, 0 failed, 0 incomplete; 3 not applicable.

---

## Fixes Applied

None. Under `/sdlc-execute`, the gate phase does not edit source.

## Remaining Issues

### High Priority

| Field | Value |
|-------|-------|
| **ID** | R1 |
| **Severity** | High (task T002 incomplete) |
| **Category** | Testing |
| **Location** | `tests/bdd/features/rest_pose_finalize.feature` |
| **Issue** | The feature file does not match the revised spec's `feature.gherkin` (PR #281). In SCN003, the title "Export and reduction do not bake the pose" should be "Export and the reduce copy step do not bake the pose". The When step should end "...and make_copy copies its skinned mesh", not "...and reduce_asset reduces it". The Then step should say "And the copy has the rest-pose bounds within 1e-3 m", not "each reduced copy". In SCN004, the When step should be "When validate_asset or export_variants finishes or raises, or reduce_asset refuses it with \"reduce.rigged\"", not "validate_asset, reduce_asset, or export_variants finishes or raises". |
| **Impact** | T002's acceptance requires the scenarios to match exactly. The executable BDD describes a reduce path that the code refuses (`reduce.rigged`). |
| **Remediation** | Copy SCN001-SCN005 from the spec's `feature.gherkin` into the feature file, and update the step bindings in `tests/bdd/test_rest_pose_finalize_bdd.py` to match. |
| **Reason Not Fixed** | The gate phase does not edit source. The run returns to implement. |

| Field | Value |
|-------|-------|
| **ID** | R2 |
| **Severity** | High (AC4 evidence gap) |
| **Category** | Testing |
| **Location** | `tests/blender/test_rest_pose_finalize.py` (`test_scn004_the_scene_is_left_unchanged`, about line 268; `_pose_state`, about line 119) |
| **Issue** | `test_scn004` compares against whatever `pose_position` the fixture leaves and never checks that it is `'POSE'`. The fixture's reseat already leaves the rig at REST, so a mutant that never restores `pose_position` still passes SCN004. |
| **Impact** | SCN004 alone does not prove AC4's `pose_position` clause. |
| **Remediation** | Before each call, set the rig to `pose_position = 'POSE'` (or pin it in the fixture), and assert `before["pose_position"] == "POSE"`. Then compare after the call. |
| **Reason Not Fixed** | The gate phase does not edit source. The run returns to implement. |

### Info (carried from review)

- F1: `reseat_desktop` now measures its offset at rest. The revised spec covers this under FR3, so it is no longer a deviation.
- F2: superseded. The revised AC3 has no `reduce_asset` clause.

---

## Positive Observations

- One small context manager restores its state in `finally` on every path.
- The proofs run in real headless Blender and fail against a no-op mutant for 5 of the 6 tests.

## Recommendation

**Needs fixes.** Fix R1 and R2 in implement, then run the full registered gate again.
