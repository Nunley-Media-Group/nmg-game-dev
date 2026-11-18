# Root Cause Analysis: geometry.normals never settles on a mesh with a twist seam

**Issue**: #243
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/232-make-mesh-cleanup-recalculate-normals-the-way-the-geometry-normals-check-judges-them/

## Root Cause

A twist seam leaves an island with no consistent winding, yet every edge has exactly two faces. `_drop_non_manifold_faces()` in `variants_core/meshes.py` never removes it. `bmesh.ops.recalc_face_normals` has to break consistency somewhere on such an island, and where it breaks depends on the starting state. `contract_core/geometry.py` `_outward_violations()` flags every face the check's recalculation flips. That set is large, it moves between passes, and it is not at the seam. Neither routine looks for the condition that identifies the defect. After recalculation, an orientable island has no edge whose two faces walk it in the same direction, and a twisted island always has at least one; those edges are the seam. `_walk_direction()` already computes this for the open-island winding check. #232's `_settle_normals` deletes every still-flagged face, so on a twisted island it deletes almost all faces (90 of 96 on `klein(32, 3)`) where 6 are enough.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` | `normal_violations`, `_outward_violations`, `geometry_findings` | Flags flipped faces; never detects the seam |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | `RULES` | Remediation catalogue; needs the new rule |
| `plugins/nmg-game-dev-blender-addon/variants_core/meshes.py` | `clean_mesh`, `_settle_normals` (#232) | Never removes the seam; deletes faces broadly |
| `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py` | `cleanup_desktop` | Per-object report that the finalize variants step returns |

## Fix Strategy

1. **Seam detection.** In `contract_core/geometry.py`, add the public function `twist_seam_edges(faces)`. It returns, in edge-index order, every edge with exactly two linked faces that are both in `faces`, where `_walk_direction` of the two faces' loops on that edge is equal.
2. **Validator.** `normal_violations(bm)` returns `(faces, seam_edges)`. Open islands keep the winding check. For a closed island, recalculate it as today and compute `twist_seam_edges(island)`. If the island has seam edges, add them to `seam_edges` and flag none of its faces. Otherwise flag its flipped faces as today. Both lists are sorted by index. `geometry_findings` builds the `geometry.normals` finding from `faces`, unchanged. When `seam_edges` is non-empty, it adds a `geometry.twist_seam` finding through `_located`:
   - message: `{name} has {n} twist seam edge(s) where no winding is consistent`;
   - `count`: the number of seam edges;
   - `samples`: the lowest 5 edges, each with `index`, `position` (world-space edge midpoint, rounded to 6 decimals), and `vertex_groups` (both vertices' groups), from a new `_edge_sample`.
3. **Remediation.** Add `geometry.twist_seam` to `RULES`: "A narrow seam joins this part back to itself with reversed winding, so no outward direction is consistent. Delete the faces at the reported seam edges and rebuild that join, or let finalize cleanup delete them."
4. **Cleanup.** In `variants_core/meshes.py` `_settle_normals`, after `recalc_island_normals(bm)`, write, and probe, compute `twist_seam_edges(probe.faces)` on the probe before any further recalculation.
   - If there are seam edges: delete the faces linked to them from `bm` by index, then call `_delete_loose(bm)`. Record the deleted face count, the seam edge count, and each seam midpoint in mesh space, then loop.
   - Otherwise: continue with #232's `normal_violations` step, which uses `faces` from the new tuple.

   Twist repair therefore always runs before the broader deletion (FR3). `clean_mesh()` returns a `TwistRepair` dict with `faces`, `edges`, and `midpoints`. Existing callers that ignore the return value are unchanged.
5. **Report.** `cleanup_desktop` adds `twist_repair: {"faces", "edges", "samples"}` to each object entry. `samples` are the first 5 midpoints, transformed by `obj.matrix_world` and rounded to 6 decimals. The finalize variants step already returns `cleanup["objects"]` under `tris.Desktop.objects`, so the report reaches finalize output.
6. **Docs.** Name `geometry.twist_seam` and what it means in `docs/asset-contract.md` section 3, in the `docs/skills/model-asset.md` geometry entries, where samples use the edge index, and in `skills/model-asset/SKILL.md`.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` | `twist_seam_edges`, tuple from `normal_violations`, `geometry.twist_seam` finding, `_edge_sample` | AC3, FR2 |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | `geometry.twist_seam` remediation | FR2 |
| `plugins/nmg-game-dev-blender-addon/variants_core/meshes.py` | Twist step in `_settle_normals`; `clean_mesh` returns `TwistRepair` | AC1, AC2, AC4, FR1, FR3 |
| `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py` | `twist_repair` per object | AC6, FR5 |
| `docs/asset-contract.md`, `docs/skills/model-asset.md`, `skills/model-asset/SKILL.md` | Describe the rule | FR6 |
| `tests/blender/normals_fixtures.py` | Shared `klein(nu, nv)` builder | FR4 |
| `tests/blender/test_twist_seams.py` | SCN001–SCN006 | FR4 |
| `tests/blender/test_clean_normals.py` | Import `klein` from the shared module; SCN004's removed-face oracle includes twist seam faces | Keeps #232's suite true after FR3 |
| `tests/unit/test_geometry_rule_docs.py` | The docs name `geometry.twist_seam` | FR6 |

## Blast Radius

Every `clean_mesh()` caller: Desktop cleanup, Mobile LOD fitting and decimation, and reduce-to-budget fitting. Twist repair deletes faces only on islands that have same-direction edges after recalculation, and orientable islands never do. `geometry_findings` output changes only for twisted closed islands: `geometry.twist_seam` replaces their `geometry.normals` faces. #232's tests built on the `klein(16, 8)` fixture still reach zero findings. The removed faces there now come from twist repair, so #232's SCN004 oracle is widened to "twist seam faces, then faces still flagged".

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Rely on #232's delete-still-flagged loop | Rejected | Measured: deletes 90 of 96 faces on `klein(32, 3)` |
| Report the seam inside `geometry.normals` | Rejected | Interview chose a separate `geometry.twist_seam` rule |
| Delete faces at same-direction edges after recalculation, before the broader step | Selected | Measured: 6 faces, zero findings afterwards, stable and deterministic |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #243 | 2026-11-18 | Initial defect design |
