# Root Cause Analysis: Fix finalize export failing the contract on Mobile LODs the variants step decimated

**Issue**: #140
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/33-build-blender-cleanup-remesh-lod-and-variant-operators/

## Root Cause

All paths are under `plugins/nmg-game-dev-blender-addon/`.

- `variants_core/cleanup.py` `_clean_mesh` (merge doubles, delete zero-area faces, delete loose geometry, `dissolve_degenerate`, `recalc_face_normals`) runs on Desktop meshes only, from `cleanup_desktop`.
- `variants_core/meshes.py` `fit_meshes` returns `decimated_copy` results whose only post-processing is `_drop_duplicate_faces`. Its three callers in `variants_core/mobile.py` (`_build_rigged_chain`, `_build_lod_group`, `_fit_objects`) assign those meshes to the Mobile objects unchanged, so zero-area faces created by edge collapse reach the contract.
- `_clean_mesh` deletes faces with area `<= 1e-10`, while `contract_core/geometry.py` flags faces with area `< 1e-8`. A face between the two limits survives cleanup and still fails the contract.
- A tiny face on an edge shared by more than two faces survives `_clean_mesh` and decimation. `recalc_face_normals` orients it differently on the evaluated copy that `contract_core/geometry.py` `_flipped_faces` checks, so `geometry.normals` reports it on the Desktop mesh and every LOD.
- Nothing re-seats the Mobile meshes after decimation. `contract_core/validate.py` `_pivot_findings` measures the bounding-box bottom centre of the variant's non-`_LOD[1-9]` meshes against `PIVOT_TOLERANCE = 1e-3`. Losing an extreme vertex moves that centre off the origin.
- `_drop_duplicate_faces` runs only inside `decimated_copy`. `_clean_mesh` has no equivalent, and `fit_meshes` returns `mesh.copy()` when the source is already within budget, so Desktop faces with identical vertex sets reach the Desktop FBX and an undecimated Mobile LOD0. FBX import keeps one face of each set, and `contract_core/reimport.py` reports `reimport.tris`.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py` | `cleanup_desktop`, `_clean_mesh`, `_delete_loose`, `ZERO_AREA_LIMIT` | Desktop-only clean with a looser zero-area limit than the contract, and no non-manifold or duplicate-face removal |
| `plugins/nmg-game-dev-blender-addon/variants_core/meshes.py` | `fit_meshes`, `decimated_copy`, `_drop_duplicate_faces` | Returns decimated or copied meshes without the clean |
| `plugins/nmg-game-dev-blender-addon/variants_core/mobile.py` | `build_mobile`, `_build_rigged_chain`, `_build_lod_group`, `_fit_objects` | Assigns fitted meshes and never re-seats the variant |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | `_pivot_findings` (read-only reference) | Measures the bottom centre the re-seat must satisfy |
| `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` | `geometry_findings`, `_flipped_faces` (read-only reference) | Zero-area, loose and normals rules the clean must satisfy |

## Fix Strategy

1. **One shared clean routine.** Move `_clean_mesh` from `cleanup.py` to `meshes.py` as public `clean_mesh(mesh)` and merge `_drop_duplicate_faces` into it. On one bmesh, in this order:
   1. `remove_doubles` at `DUPLICATE_DISTANCE` (1e-5);
   2. `dissolve_degenerate` at `DEGENERATE_DISTANCE` (1e-6);
   3. delete faces with `calc_area() < ZERO_AREA_LIMIT`, where the variants constant becomes `1e-8`, the limit `contract_core/geometry.py` uses;
   4. delete faces on non-manifold edges: while any edge has more than two linked faces, keep that edge's two largest faces by area (ties keep the lower face index) and delete the rest;
   5. delete duplicate faces whose vertex set (frozenset of vertex indices) repeats an earlier face's set, keeping the first by face index;
   6. delete loose edges and vertices (`_delete_loose`);
   7. `recalc_face_normals` over all faces, then `to_mesh` and `mesh.update()`.

   `cleanup_desktop` calls `clean_mesh` and still reports `tris_after` from the cleaned mesh. Every step is deterministic, so identical input gives identical output.
2. **Clean every fitted mesh.** In `fit_meshes`, clean every candidate before the triangle total is compared with the target. That covers both the `mesh.copy()` under-budget branch and every `decimated_copy` result. The clean only removes geometry, so the fitted total stays at or below the target. `decimated_copy` no longer calls `_drop_duplicate_faces`. `lod_tris` in `build_mobile` is already measured from the assigned meshes, so it reports post-clean counts.
3. **Re-seat the Mobile variant.** Add `_reseat(mobile_collection)` in `mobile.py`. `build_mobile` calls it after the layout is built and before the result is returned. It does the following:
   - Call `bpy.context.view_layer.update()`.
   - Measure the world-space positions of the mesh vertices (`obj.matrix_world @ vertex.co`) of the Mobile meshes whose names do not match `_LOD[1-9]$`. This is the same mesh set `_pivot_findings` checks, measured on rest geometry.
   - Compute `offset = (centre_x, centre_y, bottom_z)`.
   - When the offset is not exactly zero, translate the mesh data of every Mobile mesh object, including LOD1/LOD2, by `-offset` in that object's local frame: `obj.data.transform(Matrix.Translation(obj.matrix_world.inverted().to_3x3() @ -offset))`, then `obj.data.update()`.

   Objects, origins, parents, `matrix_parent_inverse`, the LodGroup Empty, Armature modifiers and vertex groups are not touched. The Mobile root keeps the Desktop root's world matrix, which `validate` already put at the origin. Rigged meshes stay bound to the rig. Every LOD moves by the same offset, so the LODs stay aligned with LOD0.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `plugins/nmg-game-dev-blender-addon/variants_core/meshes.py` | Add `clean_mesh` with the constants it uses; fold in duplicate-face removal; clean every `fit_meshes` candidate before the target comparison; drop `_drop_duplicate_faces` from `decimated_copy` | AC1, AC2, AC4, AC5, AC6; FR1, FR3, FR4, FR5 |
| `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py` | `cleanup_desktop` calls `meshes.clean_mesh`; remove the local `_clean_mesh` and the 1e-10 constant | AC2, AC4, AC7; FR3, FR4 |
| `plugins/nmg-game-dev-blender-addon/variants_core/mobile.py` | Add `_reseat` and call it at the end of `build_mobile` | AC3, AC6; FR2 |
| `docs/asset-contract.md` | §5 Variants: the `variants` step cleans every Mobile mesh it produces (degenerate, zero-area, non-manifold-edge, duplicate and loose geometry) and re-seats the variant so its bottom centre is at the origin | FR7 |
| `tests/blender/test_variants_clean.py` | New headless regression tests | AC1–AC7; FR6 |

## Blast Radius

- `cleanup_desktop` now also deletes non-manifold-edge extras, duplicate faces, and faces with area in `[1e-10, 1e-8)`. Every caller (`variants_core/__init__.py`, the `nmggamedev.cleanup_desktop` operator, the finalize `variants` step) sees the cleaned counts in `tris_after`. Faces in that area band already fail the contract, so assets that pass `validate` are unaffected.
- `fit_meshes` callers get cleaned meshes. Under-budget Mobile copies lose duplicate faces, and their counts drop to match what FBX re-import keeps.
- `build_mobile` changes Mobile vertex positions by at most the pivot drift (millimetres). Sidecars and exports read the re-seated meshes.
- Contract code (`contract_core/`) is unchanged.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Shared `clean_mesh` in `meshes.py`, used by Desktop cleanup and `fit_meshes` | Selected | One routine and one threshold for both variants; `meshes.py` is already the mesh-helper module that `cleanup.py` and `mobile.py` import |
| Re-seat by moving the Mobile root object | Rejected | The root origin must stay at the world origin; moving the object would fail `transform.root_applied` and shift the rig binding |
| Import `ZERO_AREA_LIMIT` from `contract_core.geometry` | Rejected | `variants_core` keeps its own copies of contract values (as `textures.py` already does for node types); the constant is set to the same value |
| Recompute normals on the evaluated copy instead of removing non-manifold-edge faces | Rejected | The contract checks a fresh evaluated copy; only removing the face that orients unstably makes repeated validation agree |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #140 | 2026-11-11 | Initial defect report |
