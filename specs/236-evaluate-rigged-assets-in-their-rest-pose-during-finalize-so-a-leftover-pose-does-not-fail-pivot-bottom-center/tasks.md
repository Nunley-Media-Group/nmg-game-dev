# Tasks: Finalize measures a rigged asset in its leftover pose and fails pivot.bottom_center

**Issue**: #236
**Date**: 2026-11-19
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/102-preserve-the-rig-when-finalizing-a-character-rigged-with-rig-humanoid/

## Implementation Tasks

### T001: Correct the Root Cause

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/rest_pose.py`, `plugins/nmg-game-dev-blender-addon/contract_core/validate.py`, `plugins/nmg-game-dev-blender-addon/reduce_core/decimate.py`, `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py`, `plugins/nmg-game-dev-blender-addon/variants_core/export.py`, `plugins/nmg-game-dev-blender-addon/finalize_core/anims.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- FR1: `rest_pose(objects)` sets every deforming armature's `pose_position` to `'REST'` and restores the prior value on exit and on error. With no deforming armature it changes nothing
- AC1/AC2/FR2: `validate_asset` runs its checks inside `rest_pose`, so a posed rig with a correct rest pivot gets no `pivot.bottom_center` finding
- AC3/FR3: `make_copy`, `reseat_desktop`, and `export_variants` evaluate, measure, and export inside `rest_pose`. `reduce_asset` still refuses rigged collections with `reduce.rigged`
- AC4: none of these writes pose-bone transforms or the action assignment
- AC5/FR4: `_export_one` restores every pose bone's rotation mode, location, rotation, and scale after each clip, also on error

### T002: Add Behavioral Regression Coverage

**File(s)**: `tests/blender/test_rest_pose_finalize.py`, `tests/blender/rig_fixtures.py`, `tests/bdd/features/rest_pose_finalize.feature`, `tests/bdd/test_rest_pose_finalize_bdd.py`, `CHANGELOG.md`
**Type**: Create
**Depends**: T001
**Acceptance**:
- A `pose_hero(offset)` fixture helper in `tests/blender/rig_fixtures.py` gives `build_hero`'s rig non-identity pose-bone transforms that move the skin's bounds by more than 1 mm, with no action assigned
- AC1: `validate_asset` on the posed hero has no `pivot.bottom_center` finding. Without the T001 change the same setup produces that finding, so the test fails before the fix and passes after it
- AC2: the posed hero's validation findings and measured values equal those of the same hero with pose bones cleared
- AC3: `export_variants` on the posed hero writes Desktop and Mobile `.glb` files whose re-imported mesh bounds and armature rest heads match the source rest pose within 1e-3 m. `reduce_core.decimate.make_copy` called directly on the posed hero's skinned mesh stores a copy whose bounds match the rest bounds within 1e-3 m
- AC4: after each of `validate_asset` and `export_variants` (including one forced failure), and after `reduce_asset` refuses the rigged collection with `reduce.rigged`, every pose bone's transforms, `pose_position`, and action assignment equal their prior values
- AC5: `export_clips` on a rig with no action and identity pose bones leaves every bone at identity and no action assigned
- `tests/bdd/features/rest_pose_finalize.feature` carries SCN001–SCN005 exactly as in this spec's `feature.gherkin`. `tests/bdd/test_rest_pose_finalize_bdd.py` binds them with pytest-bdd and runs the matching Blender proofs in `tests/blender/test_rest_pose_finalize.py` through `scripts/run-blender-tests.sh`, as `tests/bdd/test_shared_clip_names_bdd.py` does
- `scripts/run-blender-tests.sh` passes (`gate-blender-headless`), `uv run pytest tests/unit tests/bdd -q` passes (`repository.tests`), and the existing rigged tests (`test_variants_rigged.py`, `test_reduce.py`, `test_finalize_anims.py`, `test_contract_validate.py`) still pass
- `CHANGELOG.md` `[Unreleased]` has a `### Fixed` bullet describing rest-pose evaluation of rigged assets that ends with `(#236)`

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #236 | 2026-11-18 | Initial defect tasks |
| #236 | 2026-11-19 | Spec revised before delivery |
