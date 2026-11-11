# Root Cause Analysis: Meshy a-pose arm raise destroys legs on stylized characters

**Issue**: #135
**Date**: 2026-11-11
**Status**: Approved
**Author**: Claude Code
**Related Spec**: specs/106-raise-meshy-a-pose-arms-to-within-the-rig-humanoid-arm-drop-limit-on-import/

## Root Cause

`_raise_arms` in `scripts/blender/meshy_session.py` (#106) derives everything from the world bounding box:

1. **Pivot position.** Each pivot is `(x_c ± SHOULDER_HALF_WIDTH·H, y_c, z_min + SHOULDER_HEIGHT·H)` with `0.10` and `0.81`. A stylized body with a big head has real shoulders at 0.55–0.67·H, so the pivot lands in the head. The drop from there to `_hand_tip` (the farthest vertex on that side) is far larger than the real drop, so `excess = drop − TARGET_DROP_DEG` over-rotates the arm toward a T-pose.
2. **Arm selection.** A vertex moves when it is outboard of the pivot x and its drop from the pivot is at most `ARM_CONE_EXTRA_DEG` (20°) below the hand tip's. That is an angular window, not an arm. With the pivot too high, wide legs, boots, and skirts beyond 0.10·H fall inside the window. Nothing limits the selection by distance from the shoulder.

`_import_glb` calls `_raise_arms` whenever `payload["pose"] == "a-pose"`. `GenerateRequest`, `generate_model`, the CLI, the job runner, and `MeshySession.import_glb` carry no input that turns the raise off. The only fixture, `build_humanoid`, has realistic proportions, so tests never exercised a stylized body.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `scripts/blender/meshy_session.py` | `_raise_arms`, `_hand_tip`, `SHOULDER_HEIGHT`, `SHOULDER_HALF_WIDTH`, `ARM_CONE_EXTRA_DEG`, `_import_glb` | Fixed-proportion pivot and angular-window selection |
| `src/nmg_game_dev/meshy/request.py` | `GenerateRequest` | No skip field |
| `src/nmg_game_dev/meshy/jobs.py` | `start_generate` fields, `_run_generate` | Stores and replays the request; passes pose to the import |
| `src/nmg_game_dev/meshy/session.py` | `MeshySession.import_glb` | Builds the `import_glb` payload |
| `mcp-servers/meshy/src/meshy_mcp/server.py`, `mcp-servers/meshy/tools.json` | `generate_model` | Tool surface |
| `src/nmg_game_dev/meshy/__main__.py` | `generate` subcommand | CLI surface |
| `tests/blender/meshy_fixtures.py`, `tests/meshy_arm_geometry.py` | `build_humanoid`, geometry helpers | Realistic fixture only |

## Fix Strategy

Replace the bounding-box pivot and angular window in `scripts/blender/meshy_session.py` with mesh-derived slice analysis, in world space after normalization (the mesh then has identity transform, feet on z = 0, bottom center at the origin, so `x_c = 0`).

**Slices.** Sample horizontal planes from the top of the mesh down to z_min in steps of `SLICE_STEP = 0.005·H`. For each plane, intersect every polygon that straddles it, giving one segment per polygon; project each segment onto X and union overlapping X ranges (merging ranges closer than `SLICE_GAP = 0.002·H`). The result is that slice's sorted list of X intervals (the silhouette of the slice). Precompute per polygon its z range so each slice only visits straddling polygons.

**Torso and arm intervals.** In a slice, the torso interval is the one containing `x_c`. On side `sign`, the arm candidate is the outermost interval on that side that does not contain `x_c`. A slice with no torso interval (for example between wide-stance legs) has no armpit.

**Armpit (FR1, AC3).** Scanning downward, the armpit on a side is the highest slice z where the torso interval and a separate arm candidate exist and remain separate (torso interval present, arm candidate present and not merged into it) for every slice over the following `ARMPIT_RUN = 0.05·H`. No such slice → that side is undetected with `reason` `no_armpit` (FR6, AC6). Record the torso interval's outboard edge `x_edge` at the armpit slice.

**Arm tracking (FR2, AC4).** Starting at the armpit slice's arm candidate, walk down slice by slice. The arm interval in the next slice is the interval that overlaps the previous arm interval and does not contain `x_c`. Tracking stops when no interval overlaps (the hand ended), when more than one interval overlaps, or when the overlapping interval is wider than `ARM_GROWTH = 2.0` times the previous arm interval (the arm touched a skirt, hip, or other geometry). The tracked intervals, keyed by slice z, define the arm below the armpit.

**Shoulder.** Fit a least-squares line `x = a + b·z` through the midpoints of the tracked intervals (for a symmetric slanted limb the midpoints of horizontal chords lie on its axis). The shoulder is the point on that line with `x = x_edge`: `z_s = (x_edge − a)/b`; when `|b| < 1e-6` (a vertical arm) use the armpit z. Its y is the midpoint of the y-range of the tracked arm vertices.

**Arm vertices and hand tip (FR2, FR3).** A vertex below the armpit is an arm vertex when its z lies within the tracked z range (or at most one `SLICE_STEP` below the lowest tracked slice) and its x lies inside the tracked interval of the nearest tracked slice. A vertex at or above the armpit belongs to the arm cap when it is outboard of `x_edge` and within `r` of the shoulder, where `r` is the width of the arm interval in the armpit slice. The hand tip is the arm vertex farthest from the shoulder; the arm length `L` is that distance. Every selected vertex must also lie within `L` of the shoulder; nothing else moves.

**Raise (FR4, FR8).** `drop = _drop_deg(shoulder, hand_tip)`. When `drop ≤ TARGET_DROP_DEG` the side keeps every vertex. Otherwise each selected vertex rotates about the Y axis through the shoulder by `−sign·weight·(drop − 48°)` using the existing `_raise_point`, with `weight = min(1, sign·(x − x_edge)/BLEND)` and `BLEND = 0.04·H` (vertices with `sign·(x − x_edge) ≤ 0` get weight 0 and do not move). Only vertex coordinates change, so counts, connectivity, and face winding are unchanged.

**Report (FR5, AC5, AC6).** Each side of `arm_raise` is:

- detected: `{"detected": true, "shoulder": [x, y, z], "hand_tip": [x, y, z], "drop_before_deg", "drop_after_deg", "rotation_deg"}` — points after the raise, rounded to 6 decimals (the shoulder is the pivot, so it does not move);
- undetected: `{"detected": false, "reason": "no_armpit", "shoulder": null, "hand_tip": null, "drop_before_deg": null, "drop_after_deg": null, "rotation_deg": 0.0}`.

**Skip option (FR7, AC7).** Add `raise_arms: bool = True` to `GenerateRequest`; `start_generate` stores it in `request.json`; `_run_generate` reads `stored.get("raise_arms", True)` and passes it to `MeshySession.import_glb(..., raise_arms=...)`, which adds `"raise_arms": false` to the payload only when false. `_import_glb` runs the raise only when `pose == "a-pose"` and `payload.get("raise_arms", True)` is true; otherwise `arm_raise` is `null`. `raise_arms=False` with another pose or no pose is accepted and has no effect. Meshy's `pose_mode` is unaffected.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `scripts/blender/meshy_session.py` | Remove `SHOULDER_HEIGHT`, `SHOULDER_HALF_WIDTH`, `ARM_CONE_EXTRA_DEG`, `_hand_tip`; add slice, armpit, tracking, shoulder, selection helpers; rewrite `_raise_arms`; gate on `raise_arms`; update module docstring | AC1–AC6, AC8, AC9; FR1–FR6, FR8 |
| `src/nmg_game_dev/meshy/request.py` | `raise_arms: bool = True` on `GenerateRequest` | AC7; FR7 |
| `src/nmg_game_dev/meshy/jobs.py` | Store and replay `raise_arms`; pass to `import_glb` | AC7 |
| `src/nmg_game_dev/meshy/session.py` | `import_glb(..., raise_arms: bool = True)` payload key | AC7 |
| `mcp-servers/meshy/src/meshy_mcp/server.py`, `mcp-servers/meshy/tools.json` | `raise_arms: bool = True` parameter and schema property; description names it | AC7 |
| `src/nmg_game_dev/meshy/__main__.py` | `--no-arm-raise` (`dest="raise_arms"`, `store_false`) | AC7 |
| `tests/meshy_arm_geometry.py`, `tests/blender/meshy_fixtures.py` | Stylized and fused-arm fixtures with true landmarks and per-part vertex sets; `raise_arm_landmarks` accepts per-side pivots | FR9; AC1–AC6 |
| `tests/meshy_fakes.py` | `ARM_RAISE` carries the new fields; `arm_raise` is null when `raise_arms` is false | AC5, AC7 |
| `docs/mcp/meshy.md` | Pose, Arm raise, Tools, Status document, CLI sections | FR10 |

## Blast Radius

- `arm_raise` side objects gain `detected`, `shoulder`, `hand_tip`, and (undetected) `reason`, and undetected sides carry `null` drops. Consumers reading `drop_*` must tolerate `null` on an undetected side; the job runner copies `arm_raise` through unchanged.
- The realistic box humanoid now pivots about its detected shoulder, which lies on the arm axis, so its reported drops and 48° result are unchanged; `rotation_deg` stays about 7°.
- `t-pose`, no-pose, retexture, and export paths are untouched.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Retune `SHOULDER_HEIGHT` / `SHOULDER_HALF_WIDTH` | Rejected | Any fixed proportion fails one of realistic or stylized bodies |
| Mesh-connectivity (island) selection | Rejected | Meshy arms are welded into the torso surface; islands do not separate them |
| Slice-interval armpit detection with tracked selection | Selected | Works on welded single-surface meshes and limits selection to the arm |
| Caller-supplied shoulders | Rejected | Out of scope per the issue |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #135 | 2026-11-11 | Initial defect design |
