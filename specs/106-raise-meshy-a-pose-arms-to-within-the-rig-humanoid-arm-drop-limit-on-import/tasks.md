# Tasks: Raise Meshy A-pose arms to within the rig_humanoid arm-drop limit on import

**Issue**: #106
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/98-add-optional-meshy-model-generation-and-retexturing-through-the-meshy-api/

## Implementation Tasks

### T001: Raise A-pose arms in the session import

**File(s)**: `scripts/blender/meshy_session.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `_raise_arms` implements the design's pivot, hand-tip, cone, blend, and rotation rules with the named constants (AC1, FR1, FR2).
- `import_glb` with `pose: "a-pose"` returns `arm_raise` for both sides. Any other pose or a missing pose returns `arm_raise: null` and moves no vertex (AC2, AC3).
- The module docstring documents `pose` and `arm_raise`.

### T002: Pass the pose through and report it

**File(s)**: `src/nmg_game_dev/meshy/session.py`, `src/nmg_game_dev/meshy/jobs.py`, `tests/meshy_fakes.py`, `docs/mcp/meshy.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `MeshySession.import_glb` accepts `pose` and sends it in the payload. The generate job passes `request.pose` and copies `arm_raise` into its `result` (AC3, FR3).
- The fake session records the pose and returns an `arm_raise` value.
- `docs/mcp/meshy.md` explains that A-pose imports have their arms raised to a 48° drop and documents `arm_raise`.
- `CHANGELOG.md` `[Unreleased]` has an Added bullet that ends with `(#106)`.

### T003: Tests

**File(s)**: `tests/blender/test_meshy_session.py`, `tests/blender/meshy_fixtures.py`, `tests/unit/meshy/test_jobs.py`, `tests/bdd/features/meshy.feature`, `tests/bdd/test_meshy_bdd.py`
**Type**: Create
**Depends**: T001, T002
**Acceptance**:
- `tests/blender/meshy_fixtures.py` builds a symmetric box humanoid of height 1.8 m as one welded mesh, with torso, legs, and arms hinged at the pivot rule's shoulders and dropped 55°. It returns its landmark points: shoulders at the pivots, and wrists at 0.8 of each arm's length. The fixture is exported as GLB.
- Blender tests: an A-pose import reports `drop_before_deg ≈ 55` and `drop_after_deg` within 0.5 of 48 on both sides. Vertices within `0.10·H` of the midline and every leg vertex keep their positions within `1e-6`. Vertex and face counts and face connectivity are unchanged, and no face normal's dot with its pre-raise normal is ≤ 0 (AC1). A `t-pose` import, a pose-less import, and an A-pose fixture dropped 45° move no vertex and report as specified (AC2, AC3). The fixture landmarks, with wrists moved by the same per-vertex transform, pass `rig_core.landmarks.validate` without `rig.pose_not_neutral` (AC4). The suite runs under `scripts/run-blender-tests.sh`.
- `tests/unit/meshy/test_jobs.py` asserts that the generate job passes `pose` to the session and copies `arm_raise` into its result (AC3).
- `tests/bdd/features/meshy.feature` gains scenarios SCN001–SCN004 for this issue, bound in `tests/bdd/test_meshy_bdd.py` through the fake session and job result. `pytest tests/unit tests/bdd` passes.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #106 | 2026-10-31 | Initial feature tasks |
