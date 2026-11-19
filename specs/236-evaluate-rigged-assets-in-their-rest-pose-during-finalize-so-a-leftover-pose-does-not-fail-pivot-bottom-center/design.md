# Root Cause Analysis: Finalize measures a rigged asset in its leftover pose and fails pivot.bottom_center

**Issue**: #236
**Date**: 2026-11-19
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/102-preserve-the-rig-when-finalizing-a-character-rigged-with-rig-humanoid/

## Root Cause

Contract checks, the reduce copy step, cleanup's Desktop re-seat, and export read the depsgraph-evaluated mesh or its `bound_box`. For a skinned mesh, the Armature modifier deforms it to the rig's current pose. With no action assigned, that pose is whatever the pose bones hold. So validation measures deformed bounds and geometry, the re-seat moves mesh data by the pose offset, and a reduce copy can store the deformed geometry permanently. One source of a leftover pose is `finalize_core/anims.py::_export_one`. It assigns each clip's action to export it, then restores only the saved action. When no action was assigned, it sets `None`, which leaves the pose bones at the last clip's evaluated pose.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | `validate_asset`, `_pivot_findings`, `_mesh_findings` | Reads posed `bound_box` and posed evaluated copies |
| `plugins/nmg-game-dev-blender-addon/contract_core/texel.py` | `evaluated_copy` | Evaluates with the Armature modifier at the current pose |
| `plugins/nmg-game-dev-blender-addon/reduce_core/decimate.py` | `make_copy` | Stores `evaluated_mesh(source)` as the copy's geometry |
| `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py` | `reseat_desktop` | Re-seats Desktop mesh data from the posed `bound_box` |
| `plugins/nmg-game-dev-blender-addon/variants_core/export.py` | `export_variants` | Exports with `export_apply` and evaluates meshes for records |
| `plugins/nmg-game-dev-blender-addon/finalize_core/anims.py` | `_export_one` | Leaves pose bones at the last clip pose |

## Fix Strategy

Evaluate rigged meshes with their armatures set to the rest pose, through one shared context manager, and make clip export restore pose-bone transforms. The rest-pose path never writes pose-bone transforms or action assignments. It changes only `pose_position`, and restores it. `reduce_asset` still refuses rigged collections (`reduce.rigged`, #139), so the guard in `make_copy` protects the copy step itself rather than a rigged `reduce_asset` run.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `plugins/nmg-game-dev-blender-addon/variants_core/rest_pose.py` (new) | `deforming_armatures(objects) -> list[Object]`: armatures named by Armature modifiers on the given objects, plus an ARMATURE parent, deduplicated in order. `@contextmanager rest_pose(objects)`: save each armature's `data.pose_position`, set `'REST'`, call `bpy.context.view_layer.update()`, `yield`, then in `finally` restore each value and update again | FR1 |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | `validate_asset` collects the Desktop and Mobile mesh objects it checks and runs its checks inside `rest_pose(meshes)`. It imports `rest_pose` inside the function to avoid a package import cycle | AC1, AC2, AC4, FR2 |
| `plugins/nmg-game-dev-blender-addon/reduce_core/decimate.py` | `make_copy` calls `evaluated_mesh(source)` inside `rest_pose([source])` | AC3, FR3 |
| `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py` | `reseat_desktop` measures the bottom center inside `rest_pose` | AC3, AC4, FR3 |
| `plugins/nmg-game-dev-blender-addon/variants_core/export.py` | `export_variants` runs its record measurement and both `.glb` exports inside `rest_pose(desktop_objects + mobile_objects)` | AC3, AC4, FR3 |
| `plugins/nmg-game-dev-blender-addon/finalize_core/anims.py` | `_export_one` snapshots each pose bone's `rotation_mode`, `location`, `rotation_quaternion`, `rotation_euler`, `rotation_axis_angle`, and `scale` before assigning the clip, and restores them in `finally` after the action, slot, mutes, and name | AC5, FR4 |

## Blast Radius

Unrigged assets have no deforming armature, so `rest_pose` is a no-op for them and their results do not change. Rigged assets at rest give identical results, because REST and POSE evaluate the same geometry when every bone is at identity. The finalize validate, cleanup, and export steps, the reduce copy step, and the contract CLI all go through the changed functions. `reduce_asset`'s `reduce.rigged` refusal and `variants_core/mobile.py` are unchanged.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Report a `rig.posed` finding instead of evaluating at rest | Rejected | It would still fail a correctly authored asset. The issue prefers rest-pose evaluation |
| Clear pose bones to identity before measuring | Rejected | It writes user data; `pose_position` gives the same evaluation and is trivially restored |
| Wrap `evaluated_mesh` itself | Rejected | `mobile.py` handles rigs on purpose already; wrapping the affected entry points keeps the change local |
| Lift #139's `reduce.rigged` refusal so `reduce_asset` reduces posed rigs | Rejected | #139 deliberately scopes rigged reduction out; this fix keeps that refusal |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #236 | 2026-11-18 | Initial defect design |
| #236 | 2026-11-19 | Spec revised before delivery |
