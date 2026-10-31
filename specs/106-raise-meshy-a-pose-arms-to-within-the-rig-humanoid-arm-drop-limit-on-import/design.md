# Design: Raise Meshy A-pose arms to within the rig_humanoid arm-drop limit on import

**Issue**: #106
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/98-add-optional-meshy-model-generation-and-retexturing-through-the-meshy-api/

## Overview

The generate job passes its `pose` to the session's `import_glb`. When `pose == "a-pose"`, `scripts/blender/meshy_session.py` runs `_raise_arms(obj)` on `SM_<Name>` after the existing import steps (and after `_normalize` when that exists). It is pure vertex math on mesh coordinates. It adds no modifiers and needs no armature.

## Architecture

Constants: `TARGET_DROP_DEG = 48.0`, `SHOULDER_HEIGHT = 0.81`, `SHOULDER_HALF_WIDTH = 0.10`, `BLEND_WIDTH = 0.04`, `ARM_CONE_EXTRA_DEG = 20.0`.

`_raise_arms(obj) -> dict`:

1. Read world-space vertex positions (`obj.matrix_world @ v.co`). Compute `z_min`, `H = z_max − z_min`, `x_c`, and `y_c` (bounding-box centers).
2. For each side `s ∈ {left: +1, right: −1}`:
   - `P = (x_c + s·0.10·H, y_c, z_min + 0.81·H)`. `T` is the vertex with max `s·(x − x_c)`.
   - `drop = degrees(atan2(P.z − T.z, hypot(T.x − P.x, T.y − P.y)))`.
   - When `drop ≤ 48`: record `{drop_before_deg: drop, drop_after_deg: drop, rotation_deg: 0}` and move nothing.
   - Otherwise `θ = drop − 48`. For each vertex with lateral distance `d = s·(x − x_c) − 0.10·H > 0`, let `e` be its drop below horizontal from `P`. If `e ≤ drop + 20`, give it weight `w = min(1, d / (0.04·H))`. This arm cone keeps thighs and hips still. Rotate the vertex about `P` around the Y axis by `w·θ`, raising the arm (sign `−s` about +Y). Then recompute the drop of the rotated `T`.
3. Write the positions back through `obj.matrix_world.inverted()`, then `mesh.update()`.
4. Return `{"left": {...}, "right": {...}}`, with angles rounded to 0.01.

`_import_glb` reads `payload.get("pose")`. It sets `result["arm_raise"]` to `_raise_arms(target)` when the pose is `"a-pose"`, and to `None` otherwise. `MeshySession.import_glb(name, path, pose=None)` adds `"pose"` to the payload. `jobs.py` calls `run.session.import_glb(request.name, target, pose=request.pose)` and copies `arm_raise` into the job `result` when the job loaded into the session. The module docstring lists `pose` in the payload and `arm_raise` in the result.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `meshy_session.py` op `import_glb` | `{"name", "path", "pose"?}` | adds `arm_raise` (`{left, right}` or `null`) | Raises A-pose arms to a 48° drop |
| `MeshySession.import_glb` | `name, path, pose=None` | as above | Passes `pose` through |
| Meshy generate job `result` | — | adds `arm_raise` | Surfaces the adjustment |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Geometric pivot and hand-tip rule at import | Selected | The user's choice; no extra agent step |
| Agent-supplied landmarks in a separate op | Rejected | Adds a step outside the import |
| Loosen `_MAX_ARM_DROP_DEG` | Rejected | Out of scope; the validator stays strict |
| Temporary armature + pose bones | Rejected | Needs a rig before rigging; vertex math is enough |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #106 | 2026-10-31 | Initial feature design |
