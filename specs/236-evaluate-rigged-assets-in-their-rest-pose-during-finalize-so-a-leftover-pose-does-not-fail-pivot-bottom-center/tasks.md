# Tasks: Finalize measures a rigged asset in its leftover pose and fails pivot.bottom_center

**Issue**: #236
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/102-preserve-the-rig-when-finalizing-a-character-rigged-with-rig-humanoid/

## Implementation Tasks

### T001: Correct the Root Cause

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/rest_pose.py`, `plugins/nmg-game-dev-blender-addon/contract_core/validate.py`, `plugins/nmg-game-dev-blender-addon/reduce_core/decimate.py`, `plugins/nmg-game-dev-blender-addon/variants_core/export.py`, `plugins/nmg-game-dev-blender-addon/finalize_core/anims.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- FR1: `rest_pose(objects)` sets every deforming armature's `pose_position` to `'REST'` and restores the prior value on exit and on error. With no deforming armature it changes nothing
- AC1/AC2/FR2: `validate_asset` runs its checks inside `rest_pose`, so a posed rig with a correct rest pivot gets no `pivot.bottom_center` finding
- AC3/FR3: `make_copy` and `export_variants` evaluate and export inside `rest_pose`
- AC4: none of these writes pose-bone transforms or the action assignment
- AC5/FR4: `_export_one` restores every pose bone's rotation mode, location, rotation, and scale after each clip, also on error

### T002: Add Behavioral Regression Coverage

**File(s)**: `tests/blender/test_rest_pose_finalize.py`, `tests/blender/rig_fixtures.py`, `tests/bdd/features/rest_pose_finalize.feature`
**Type**: Create
**Depends**: T001
**Acceptance**:
- A `pose_hero(offset)` fixture helper in `tests/blender/rig_fixtures.py` gives `build_hero`'s rig non-identity pose-bone transforms that move the skin's bounds by more than 1 mm, with no action assigned
- AC1: `validate_asset` on the posed hero has no `pivot.bottom_center` finding. Without the T001 change the same setup produces that finding, so the test fails before the fix and passes after it
- AC2: the posed hero's validation findings and measured values equal those of the same hero with pose bones cleared
- AC3: `export_variants` on the posed hero writes Desktop and Mobile `.glb` files whose re-imported mesh bounds and armature rest heads match the source rest pose within 1e-3 m. A `reduce_asset` copy's bounds match the rest bounds within 1e-3 m
- AC4: after each of `validate_asset`, `reduce_asset`, and `export_variants` (including one forced failure), every pose bone's transforms, `pose_position`, and action assignment equal their prior values
- AC5: `export_clips` on a rig with no action and identity pose bones leaves every bone at identity and no action assigned
- `tests/bdd/features/rest_pose_finalize.feature` carries SCN001–SCN005 from this spec's `feature.gherkin`. `tests/blender/test_rest_pose_finalize.py` binds them with pytest-bdd and skips under plain CPython via `pytest.importorskip("bpy")`
- `scripts/run-blender-tests.sh` passes (`gate-blender-headless`), and the existing rigged tests (`test_variants_rigged.py`, `test_reduce.py`, `test_finalize_anims.py`, `test_contract_validate.py`) still pass
- `CHANGELOG.md` `[Unreleased]` has a `### Fixed` bullet describing rest-pose evaluation of rigged assets that ends with `(#236)`

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #236 | 2026-11-18 | Initial defect tasks |
