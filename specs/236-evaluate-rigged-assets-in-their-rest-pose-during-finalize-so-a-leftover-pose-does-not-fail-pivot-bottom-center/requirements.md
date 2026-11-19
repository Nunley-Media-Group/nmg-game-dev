# Defect Report: Finalize measures a rigged asset in its leftover pose and fails pivot.bottom_center

**Issue**: #236
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/102-preserve-the-rig-when-finalizing-a-character-rigged-with-rig-humanoid/

## Reproduction

1. Make a rigged asset: armature `SK_<Name>` and mesh `SM_<Name>` with an Armature modifier, origin at the bottom center, which passes validation at rest.
2. With no action assigned to the rig, give several pose bones non-identity location or rotation, enough to move the mesh's bounds by a few millimeters.
3. Run validation (`validate_asset`, the finalize validate step, or `python -m nmg_game_dev.contract validate`) on the collection.
4. `pivot.bottom_center` fails on `SM_<Name>`, offset by the pose's deformation. Clearing the pose bones makes it pass with no geometry change.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | Validation, reduction, and export evaluate a rigged asset in its rest pose whatever its pose bones hold, and leave the scene's pose, `pose_position`, and action assignment as they found them |
| **Actual** | Validation measures the posed (deformed) mesh and reports a misleading `pivot.bottom_center` failure. Reduced copies can take on the pose as permanent geometry. Exporting clips can leave pose bones holding the last clip's pose |

## Acceptance Criteria

### AC1: A posed rig does not fail the pivot check

**Given** a rigged asset whose rest-pose geometry has its origin at the bottom center
**And** its rig has no action assigned but some pose bones have non-identity transforms that move the mesh bounds by more than 1 mm
**When** `validate_asset` runs on it
**Then** the report has no `pivot.bottom_center` finding, and the asset passes as it does at rest

### AC2: The mesh checks measure the rest pose

**Given** the same posed rig
**When** validation's geometry, triangle, UV, and texel checks evaluate the skinned mesh
**Then** their findings and measured values equal those from the same asset with its pose bones cleared

### AC3: Export and reduction do not bake the pose

**Given** the same posed rig
**When** `export_variants` exports the Desktop and Mobile `.glb` files and `reduce_asset` makes reduced copies
**Then** each exported skinned mesh, re-imported, has the rest-pose vertex bounds within 1e-3 m
**And** the re-imported armature's bone rest heads (from the skin's inverse bind matrices) match the source rest heads within 1e-3 m
**And** each reduced copy's bounds match the rest-pose bounds within 1e-3 m

### AC4: The scene is left unchanged

**Given** the same posed rig
**When** `validate_asset`, `reduce_asset`, or `export_variants` finishes or raises
**Then** every pose bone's rotation mode, location, rotation, and scale, the armature's `pose_position`, and the rig's assigned action equal their values before the call

### AC5: Exporting clips does not leave a stray pose

**Given** a rig with no action assigned and its pose bones at identity
**When** `export_clips` exports its clips
**Then** every pose bone is at identity afterward, and the rig still has no action assigned

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | A `rest_pose(objects)` context manager puts every armature that deforms the given mesh objects into `pose_position = 'REST'` for the duration, then restores each armature's previous `pose_position`, also on error | Must |
| FR2 | `validate_asset` evaluates the Desktop and Mobile meshes inside `rest_pose`, so pivot, geometry, triangle, UV, and texel checks see rest-pose geometry | Must |
| FR3 | `reduce_core.decimate.make_copy` and `variants_core.export.export_variants` evaluate and export inside `rest_pose` | Must |
| FR4 | `finalize_core.anims._export_one` restores every pose bone's rotation mode, location, rotation, and scale to their values before the export, also on error | Must |

## Out of Scope

- Adding a `rig.posed` validation finding
- Normals recalculation in cleanup (#232), shared clip names (#233), and the millimetre-scale pivot offset on rigged meshes (#244)
- Changing glTF export options other than evaluating in the rest pose

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #236 | 2026-11-18 | Initial defect report |
