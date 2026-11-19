# Verification Report: Evaluate rigged assets in their rest pose during finalize

**Date**: 2026-11-19
**Issue**: #236
**Reviewer**: nmg-sdlc verify worker (gate phase)
**Scope**: Pre-merge gate at the head of the merge queue, with main integrated and the version prepared (0.30.1)

**Verification head**: 18d6f4264042a479991a59a40e38182bd0a96bc0

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 5 |
| Performance | 5 |
| Testability | 5 |
| Error Handling | 5 |
| **Overall** | 4.8 |

### Implementation Status: Pass
**Total Issues**: 0 blocking, major or minor; 1 info note

At the verification head, every applicable registered pre-merge validation passed. Eight ran and passed, and three were skipped because the change does not touch their paths. Coverage is complete: 11 declared, 11 recorded.

The review passed at `f73ed15` (scoped mode). It resolved both items that made the earlier gate at `d1b5c88` fail:
- T002: the BDD feature now has the revised SCN001-SCN005 wording.
- AC4: `test_scn004` now pins the starting `pose_position` to `POSE`.

Since `f73ed15`, the only changes are the main merges and the version preparation.

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

- Local verification: Pass
- PR evidence: Not required

---

## Acceptance Criteria Verification

Evidence comes from the passed review record (`.nmg-sdlc/verification/236-review.md`). No criterion's tests mock the path under test. Every proof drives the real entry point in headless Blender.

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | A leftover pose does not fail pivot.bottom_center | Pass | `contract_core/validate.py` wraps every variant check in `rest_pose`; `test_scn001` runs `validate_asset` on a posed hero |
| AC2 | Posed and cleared reports match | Pass | `test_scn002` compares findings and snapshots for the posed and cleared-pose runs |
| AC3 | Export and the reduce copy step do not bake the pose | Pass | `variants_core/export.py`, `variants_core/cleanup.py` (re-seat) and `reduce_core/decimate.py` `make_copy` run inside `rest_pose`. `test_scn003_*` checks re-imported GLB bounds, IBM joint heads, and the copy's bounds |
| AC4 | The scene is left unchanged | Pass | `rest_pose` restores in `finally`. `test_scn004` pins `POSE`, then compares the pose state across `validate_asset`, the `reduce.rigged` refusal, and `export_variants`, including forced failures |
| AC5 | Exporting clips does not leave a stray pose | Pass | `finalize_core/anims.py` `_export_one` restores every pose bone in `finally`; `test_scn005` and `test_scn005_a_failed_clip_export_puts_every_pose_bone_back` |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Correct the root cause | Complete | `rest_pose.py`, `validate.py`, `decimate.py`, `export.py`, `cleanup.py`, `anims.py` |
| T002 | Add behavioral regression coverage | Complete | `tests/bdd/features/rest_pose_finalize.feature` scenarios match the spec's `feature.gherkin` (checked with diff); `tests/blender/test_rest_pose_finalize.py` |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | One `rest_pose` context manager owns the evaluation state; callers only wrap it |
| Open/Closed | 4 | Existing steps are wrapped, not rewritten |
| Liskov Substitution | 5 | N/A |
| Interface Segregation | 4 | Two small functions: `deforming_armatures` and `rest_pose` |
| Dependency Inversion | 4 | A function-local import in `validate.py` avoids the `variants_core`/`contract_core` cycle |

### Layer Separation

The changes stay inside the Blender add-on's step cores. No pipeline, MCP or skill layer changes.

---

## Security Assessment

- [x] Input validation: no new external input
- [x] Injection prevention: N/A
- [x] Data protection: no credential or I/O changes

## Performance Assessment

- [x] At most one extra `view_layer.update()` per wrapped step, and none when no armature deforms
- [x] Resource management: state is restored in `finally`; read-only armature data is skipped

---

## Test Coverage

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes | Yes | Yes |
| AC2 | Yes | Yes | Yes |
| AC3 | Yes | Yes | Yes |
| AC4 | Yes | Yes | Yes |
| AC5 | Yes | Yes | Yes |

---

## Steering Doc Verification Gates

- Runner: `sdlc-verify-steering.mjs --tier pre-merge`
- Artifact: `.nmg-sdlc/verification/236.json`
- Coverage: 11 declared, 11 recorded, complete
- Ceiling: none
- Tiers: no validation declares one, so every result records `tier: null` and `selection: null`

| Gate | Tier / Selection | Status | Evidence |
|------|------------------|--------|----------|
| repository.tests | null / null | Pass | `uv run pytest tests/unit tests/bdd -q`: 2057 passed, 24 skipped |
| repository.lint | null / null | Pass | `uv run ruff check .` exited 0 |
| repository.format | null / null | Pass | `uv run ruff format --check .` exited 0 |
| repository.types | null / null | Pass | `uv run mypy src tests` exited 0 |
| gate-blender-headless | null / null | Pass | `scripts/run-blender-tests.sh`: 436 passed, 4 skipped |
| gate-godot-headless | null / null | Pass | `scripts/run-godot-tests.sh`: 28 passed, 0 failed; import, add-on tests and probes passed |
| gate-mcp-schema | null / null | Not applicable (skipped) | No `mcp-servers/**` paths changed |
| gate-shellcheck | null / null | Not applicable (skipped) | No `scripts/**.sh` paths changed |
| gate-ship-smoke | null / null | Not applicable (skipped) | No ship paths changed |
| plugin.validate | null / null | Pass | `claude plugin validate .` exited 0 |
| plugin.session-smoke | null / null | Pass | Plugin loaded with `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 8 of 8 applicable gates passed, 0 failed, 0 incomplete; 3 not applicable.

---

## Fixes Applied

None in this phase. Under `/sdlc-execute`, the gate phase does not edit source.

## Remaining Issues

None blocking, major or minor.

- Info (F1, review): `docs/asset-contract.md` lists the reduce copy among the steps that measure a rigged asset at rest. However, `reduce_asset` refuses rigged collections (`reduce.rigged`), so for consumers that clause never applies. The sentence is accurate to FR3 and only the wording is in question.

---

## Recommendation

**Ready for merge.** Every acceptance criterion and task is complete, and every applicable registered gate passed at the verification head.
