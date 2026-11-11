# Design: estimate_landmarks proposes rig_humanoid landmarks from the mesh

**Issue**: #137
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Overview

`estimate_landmarks(collection_name)` reads the world-space vertices of the collection's meshes, slices them horizontally, and derives the 19 `LANDMARK_KEYS` from the torso, arm, and leg intervals. The slicing logic is a pure-Python module that takes plain coordinates, and a thin `bpy` wrapper reads the vertices. The same change makes `rig_humanoid` read current transforms and substitute real names in its messages.

## Architecture

| Component | Path | Role |
|-----------|------|------|
| Slicing core | `plugins/nmg-game-dev-blender-addon/rig_core/slicing.py` | Pure Python, no `bpy`. `propose(points: Sequence[Vec3]) -> dict` returns the landmarks, confidence, and warnings, or raises `RigError` for `rig.arms_not_found` / `rig.crotch_not_found` |
| Blender wrapper | `plugins/nmg-game-dev-blender-addon/rig_core/estimate.py` | `estimate_landmarks(collection_name)`: checks `SM_<Name>`, calls `bpy.context.view_layer.update()`, reads every `MESH` object in the collection, and calls `propose`. Returns `ok(...)` / `fail(...)` from `rig_core/outcome.py` |
| Package export | `plugins/nmg-game-dev-blender-addon/rig_core/__init__.py` | Adds `estimate_landmarks` to the imports and `__all__` |
| Current transforms | `plugins/nmg-game-dev-blender-addon/rig_core/rig.py` `_mesh_bounds` | Calls `bpy.context.view_layer.update()` before reading `matrix_world` |
| Real names | `rig_core/landmarks.py` `validate`, `rig_core/rig.py` `_build` | `validate` gains a `collection_name` parameter and formats `SM_{name}` / `{name}` into its texts; the `rig.weights_failed` remediation does the same |

### Reading vertices

For each `MESH` object in the collection (the root `SM_<Name>` and any accessory meshes):

- read the vertex coordinates from `obj.evaluated_get(depsgraph).to_mesh()`;
- transform them by `matrix_world` (current after the view-layer update);
- call `to_mesh_clear()`.

The wrapper never changes selection, the active object, mode, or data. `view_layer.update()` only re-evaluates the depsgraph.

### Slicing algorithm (`slicing.py`)

Let `zmin`/`zmax` be the vertex z range, `H = zmax - zmin`, and `n = 200`. Slice `i` holds the vertices with `zmin + i*H/n <= z < zmin + (i+1)*H/n`.

1. **Intervals.** Sort a slice's x values and split them where consecutive values differ by more than `0.012*H`. Each interval keeps its x range, centre, and the mean y of its vertices.
2. **Crotch.** Find the lowest slice `c` with `0.15n <= c <= 0.7n` where exactly one interval contains x = 0 and slices `c..c+5` all have one. If there is none, raise `rig.crotch_not_found`. `crotch_z` is the bottom of slice `c`.
3. **Armpit and arm chains.** Scan downward from slice `0.92n`, at slices above `c`, for the highest slice with an interval containing x = 0 plus at least one interval wholly at x > 0 and one wholly at x < 0. From each side interval, follow the arm downward. The chain continues into the interval in the next lower slice whose x range overlaps the current one, takes the outermost overlapping interval, and never re-enters the central interval. The slice is accepted only when both chains last at least `0.12n` slices. Side intervals whose chain is shorter, such as a hat brim, earrings, or glasses, are skipped. If no slice qualifies, raise `rig.arms_not_found`.
4. **Arm landmarks (per side).**
   - Fit x(z) by least squares through the chain-interval centres of the middle 60% of the chain.
   - The shoulder is at `z_s = armpit_z + 0.035*H`, `x = fit(z_s)`.
   - The arm end is the lowest chain slice: its z, and `x = fit(z)`.
   - Elbow, wrist, and hand tip lie at 0.47, 0.80, and 0.985 of the way from the shoulder to the arm end.
   - y is the mean y of the chain-interval vertices.
5. **Neck.** The narrowest central interval between the shoulder slice and slice `0.95n`, at that slice's z, x = interval centre, and y = interval mean y.
6. **Head top.** `z = zmin + 0.995*H`, with x and y from the central interval of the highest slice.
7. **Pelvis.** `z = crotch_z + 0.075*H`, with x and y from the central interval at that slice.
8. **Legs (per side; x > 0 is left).**
   - Hip: `z = crotch_z + 0.03*H`, with x and y from the leg interval of that side in the slice just below the crotch.
   - Ankle: `z = zmin + 0.075*H`, with x and y from that side's interval at that slice.
   - Knee: take the measured interval centre at the height midway between hip and ankle, then blend 60% the hip–ankle line point and 40% the measured point.
   - Toe: `y = min y of that side's vertices below zmin + 0.05*H, plus 0.012*H`, with `x` = the ankle x and `z = zmin + 0.025*H`.
9. **Confidence.** For each left/right pair, compare the left point with the mirrored right point `(-x, y, z)`. A distance above `0.05*H` adds the warning `"<base>_l/<base>_r are not mirrored across X within 5% of the height"` and sets `confidence` to `low`. Landmarks are never averaged.

The work is linear in vertex count plus a per-slice sort.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `estimate_landmarks(collection_name: str) -> dict` | collection name | `{"status": "ok", "asset": name, "landmarks": {19 keys: [x, y, z]}, "confidence": "high" \| "low", "warnings": [str]}` | AC1–AC4, AC7, AC8 |
| failure | — | `fail(STATUS_FALLBACK, "rig.asset_not_found" \| "rig.arms_not_found" \| "rig.crotch_not_found", message, remediation)`, with no `landmarks` key | AC5, AC6. The `rig.asset_not_found` message names `SM_<real name>`. The other remediations say to pose the character in an A-pose with arms clear of the torso and legs apart, or to supply landmarks by hand |
| `validate(body_type, landmarks, bbox, collection_name)` | adds `collection_name` | texts use real names | AC9 |
| `rig_humanoid` | unchanged signature | unchanged result shape | AC8, AC9 |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| ghost1 slicing parameters (gap 0.012H, 6-slice crotch, 12% arm chain, 0.47/0.80/0.985 axis fractions) | Selected | Proven on 10 of 11 stylized text-to-3D characters |
| Compute `matrix_world` by hand from `matrix_basis` and parents | Rejected | `view_layer.update()` is the ghost1 workaround and covers constraints and drivers too |
| Mirror-average asymmetric pairs | Rejected | The issue requires measured landmarks and a low-confidence warning |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #137 | 2026-11-11 | Initial feature design |
