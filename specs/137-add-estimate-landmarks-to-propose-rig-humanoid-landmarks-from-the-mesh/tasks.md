# Tasks: estimate_landmarks proposes rig_humanoid landmarks from the mesh

**Issue**: #137
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Implement the slicing core

**File(s)**: `plugins/nmg-game-dev-blender-addon/rig_core/slicing.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- `propose(points)` implements design.md's slicing algorithm with its parameters (200 slices, 0.012H gaps, crotch in [0.15n, 0.7n] held 6 slices, armpit below 0.92n with arm chains of at least 0.12n slices, the 0.47/0.80/0.985 axis fractions, and the leg, neck, head, and pelvis rules) (FR3–FR7).
- It returns all 19 `LANDMARK_KEYS` as `[x, y, z]` floats, `confidence` `high` with empty `warnings`, or `low` with one warning per asymmetric pair. Landmarks are never mirror-averaged (FR2, FR8).
- It raises `RigError` with `rig.arms_not_found` or `rig.crotch_not_found` (STATUS_FALLBACK), each with a message naming what was not found and a remediation (FR9).
- The module imports no `bpy` and uses only relative imports of `outcome` and `skeleton`.

### T002: Add estimate_landmarks to rig_core

**File(s)**: `plugins/nmg-game-dev-blender-addon/rig_core/estimate.py`, `plugins/nmg-game-dev-blender-addon/rig_core/__init__.py`
**Type**: Create, Modify
**Depends**: T001
**Acceptance**:
- `estimate_landmarks(collection_name)` is importable from `rig_core` (FR1).
- A missing collection, or a collection without the mesh `SM_<Name>`, returns the `rig.asset_not_found` failure naming `SM_<Name>` with the real name (AC6).
- It calls `bpy.context.view_layer.update()`, reads the world-space evaluated vertices of every `MESH` object in the collection with `to_mesh_clear()` after each, and returns `ok(asset=..., landmarks=..., confidence=..., warnings=...)` or the failure from T001 (FR2, FR11).
- Objects, mesh data, transforms, selection, active object, and mode are unchanged afterwards for every status (FR10).

### T003: Make rig_humanoid read current transforms and name the mesh

**File(s)**: `plugins/nmg-game-dev-blender-addon/rig_core/rig.py`, `plugins/nmg-game-dev-blender-addon/rig_core/landmarks.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `_mesh_bounds` calls `bpy.context.view_layer.update()` before reading `matrix_world` (FR11).
- `validate` takes the collection name and formats `SM_<real name>` and `<real name>` into the `rig.asset_not_found` and `rig.landmarks_outside_mesh` messages and remediations. The `rig.weights_failed` remediation does the same, and no `rig_humanoid` result contains the literal `SM_<Name>` or `<Name>` (FR12).
- Symmetry, vertical-order, and pose limits are unchanged.

### T004: Add humanoid fixtures for estimation

**File(s)**: `tests/blender/landmark_fixtures.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- `build_a_pose(name, *, stylized=False, accessory=None, asymmetric=None, fused_arms=False, no_crotch=False)` builds collection `<name>` with a voxel-remeshed single mesh `SM_<name>`, posed like `tests/blender/rig_fixtures.py` `build_hero`, and returns its known joint positions as 19 landmarks.
  - The default is a realistic-proportion A-pose (arms about 40° below horizontal, straight elbows and knees, legs apart).
  - `stylized` gives a large head with shoulders at about 0.6H.
  - `accessory` is one of `hat_brim`, `earrings`, or `glasses`, sticking out sideways above the shoulders.
  - `asymmetric` is `arm` or `leg`, offsetting one side by more than 5% of the height.
  - `fused_arms` joins the arms to the torso.
  - `no_crotch` makes one column with no leg split.

### T005: Blender tests for estimate_landmarks and the rig_humanoid fixes

**File(s)**: `tests/blender/test_estimate_landmarks.py`, `tests/blender/test_rig_humanoid.py`
**Type**: Create, Modify
**Depends**: T002, T003, T004
**Acceptance**:
- SCN001 (AC1): on the default A-pose fixture, the result is `ok` and `high`, `warnings` is empty, all 19 keys are within 0.05H of the known joints, `_l` x > 0, and `_r` x < 0.
- SCN002 (AC2): those landmarks passed unchanged to `rig_humanoid(name, "humanoid", landmarks)` return `ok`.
- SCN003 (AC3): for the stylized fixture with each of `hat_brim`, `earrings`, and `glasses`, the shoulders are within 0.05H of the known shoulders (not at the accessory), and AC1's checks pass.
- SCN004 (AC4): for `asymmetric="arm"` and `asymmetric="leg"`, the result is `ok` and `low`, the landmarks equal the measured per-side positions (not mirror-averaged), and `warnings` names each asymmetric pair.
- SCN005 (AC5): the T-pose `build_hero` fixture and the `fused_arms` fixture return `rig.arms_not_found`, and the `no_crotch` fixture returns `rig.crotch_not_found`, each with a message, a remediation, and no `landmarks` key.
- SCN006 (AC6): a missing collection, and a collection without `SM_<Name>`, return `rig.asset_not_found` whose message contains `SM_` followed by the real name.
- SCN007 (AC7): for an `ok` result and for each failure, a snapshot of the scene (objects, mesh vertex data, transforms, selection, active object, and mode) taken before and after the call is equal.
- SCN008 (AC8): after `SM_<Name>`'s location, rotation, and scale are changed with no view-layer update, `rig_humanoid` with landmarks transformed to the new pose returns `ok`, and `estimate_landmarks` returns landmarks within 0.05H of the transformed joints.
- SCN009 (AC9): for collection `Hero`, the `rig.asset_not_found`, `rig.landmarks_outside_mesh`, and `rig.weights_failed` results mention `SM_Hero` and `Hero` and contain neither `SM_<Name>` nor `<Name>`.
- `propose` on a fixture subdivided to at least 100,000 vertices returns within 60 seconds.
- All tests pass through `scripts/run-blender-tests.sh` (`gate-blender-headless`), in headless background Blender, with no live Blender or Unreal editor.

### T006: Document the estimate, review, rig flow

**File(s)**: `docs/rigging-and-animation.md`, `tests/unit/test_rigging_docs.py`
**Type**: Modify, Create
**Depends**: T002
**Acceptance**:
- The Agent flow says: call `estimate_landmarks(collection)`, review and correct the proposal (always when `confidence` is `low`), then call `rig_humanoid`. The sentence "never detects anatomy itself" is replaced (FR13).
- The doc documents the result fields (`landmarks`, `confidence`, `warnings`), the meaning of `high` and `low`, the A-pose limit (no T-pose; arms clear of the torso; legs apart), and the failure codes `rig.asset_not_found`, `rig.arms_not_found`, and `rig.crotch_not_found` in its Result statuses list (AC10).
- SCN010 (AC10): `tests/unit/test_rigging_docs.py` asserts that the doc names `estimate_landmarks`, `confidence`, `warnings`, `rig.arms_not_found`, and `rig.crotch_not_found`, and that the estimate step comes before `rig_humanoid` in the Agent flow. `uv run pytest tests/unit tests/bdd -q` (`repository.tests`) passes.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #137 | 2026-11-11 | Initial feature tasks |
