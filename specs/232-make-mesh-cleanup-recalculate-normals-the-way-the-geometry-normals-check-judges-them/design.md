# Root Cause Analysis: Mesh cleanup recalculates normals differently from the geometry.normals check

**Issue**: #232
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/140-fix-finalize-export-failing-the-contract-on-mobile-lods-the-variants-step-decimated/

## Root Cause

`variants_core/meshes.py` `clean_mesh()` ends with one `bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])` and then writes the mesh. It never checks the result against the contract rule. `contract_core/geometry.py` `_normal_violations()` groups faces into edge-connected islands with `_islands()`. It checks open islands for winding only. For each closed island it calls `recalc_face_normals` on that island alone (`_outward_violations`) and flags every face whose normal flips.

On a closed island with no consistent orientation, `recalc_face_normals` is not idempotent: running it again flips faces. A self-folding region can produce such an island, and a Klein bottle is the minimal case. The earlier clean steps can create such an island from a mesh that passed validate. For example, `_drop_non_manifold_faces` removes a fin, the only boundary that kept the island open, and the open island had passed the winding check. Validate passed before cleanup, and the check flips faces on the cleaned result. Every Mobile LOD is cleaned by the same routine, so the LODs fail at the same place.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `plugins/nmg-game-dev-blender-addon/variants_core/meshes.py` | `clean_mesh` | Whole-mesh recalc; no check that the result passes the rule |
| `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` | `_normal_violations`, `_islands`, `_outward_violations` | The per-island rule the clean must satisfy |
| `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py` | `cleanup_desktop` | Desktop caller (unchanged) |
| `plugins/nmg-game-dev-blender-addon/variants_core/meshes.py` | `fit_meshes` | Mobile caller (unchanged) |
| `plugins/nmg-game-dev-blender-addon/reduce_core/decimate.py` | `fit_copy`, `_decimate_to` | Reduce caller (unchanged) |

## Fix Strategy

1. **Share the routine.** In `contract_core/geometry.py`, add the public function `recalc_island_normals(bm)`. It calls `bmesh.ops.recalc_face_normals(bm, faces=island)` once for each island returned by `_islands(bm)`, in that order. Rename `_normal_violations` to `normal_violations` and update its call in `geometry_findings`. `_outward_violations` keeps its per-island call. Findings, messages, and samples do not change.
2. **Settle normals in the clean.** In `variants_core/meshes.py`, import both functions from `..contract_core.geometry`; `variants_core/material_variants.py` already imports from `contract_core`. Replace the final whole-mesh recalc in `clean_mesh()` with `_settle_normals(bm, mesh)`, which loops:
   1. `recalc_island_normals(bm)`, then `bm.to_mesh(mesh)`.
   2. Build a probe bmesh with `from_mesh(mesh)` and `normal_update()`, so it matches what `geometry_findings` builds. Collect `face.index` for every face in `normal_violations(probe)`, then free the probe.
   3. If none are flagged, stop. Otherwise call `bm.faces.ensure_lookup_table()`, delete those faces with `context="FACES_ONLY"`, call `_delete_loose(bm)`, and loop.
   `to_mesh` and `from_mesh` keep face order, so probe indices match `bm` indices. Each pass deletes at least one face, so the loop ends. Every step is deterministic. `clean_mesh()` still finishes with the mesh written and `mesh.update()`. Update its docstring to describe the shared recalculation and the deletion.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` | Add `recalc_island_normals`; make `normal_violations` public | FR1 |
| `plugins/nmg-game-dev-blender-addon/variants_core/meshes.py` | `_settle_normals` loop replaces the whole-mesh recalc | AC1–AC4, FR2, FR3 |
| `tests/blender/test_clean_normals.py` | New SCN001–SCN005 tests and the Klein bottle fixtures | FR4 |

## Blast Radius

`clean_mesh()` runs in Desktop cleanup, in Mobile LOD fitting and decimation, and in reduce-to-budget fitting. On meshes that the per-island recalc already settles, output changes only where the whole-mesh recalc's result differed. Faces are deleted only on islands that would otherwise fail `geometry.normals`, and a mesh like that could not pass finalize before this fix. `geometry_findings` output is unchanged. The existing `test_variants_clean.py` and `test_geometry_normals.py` suites must keep passing.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Per-island recalc only, no deletion | Rejected | Measured: on a Klein bottle one per-island recalc still leaves 49 flagged faces |
| Repeat the recalc until it stops flipping faces | Rejected | Measured: the flagged counts swing for up to 8 passes and may never settle |
| Shared per-island recalc, then delete flagged faces until none remain | Selected | Measured: 0 findings after 1–2 passes, deterministic, and no deletions on orientable meshes |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #232 | 2026-11-18 | Initial defect design |
