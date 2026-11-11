# Root Cause Analysis: geometry.normals rejects correctly facing open surfaces

**Issue**: #144
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Root Cause

`geometry_findings` in `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` calls `_flipped_faces`. That function copies every face normal, runs `bmesh.ops.recalc_face_normals` over all faces of the mesh copy, and counts faces whose normal reversed.

Recalculation orients each region toward an "outside", which only exists for a closed island:

- For a single planar quad, Blender's choice is numerically arbitrary and depends on position. On Blender 5.2.3, 391 of 2,000 random axis-aligned floor quads and 1,185 of 2,000 tilted quads were reported.
- For an open sheet that deliberately faces into a space (floor plus back wall facing the room), recalculation orients it away from its own centre, so every face is counted.

Closed islands, including welded boxes, are judged correctly.

The remediation in `contract_core/report.py` ("Recalculate normals outside (Shift+N)") can turn a correct floor face down.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` | `_flipped_faces` | Whole-mesh recalculation applied to open sheets |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | `geometry.normals` remediation | Tells authors to recalculate outside |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | `geometry_findings` caller | Finalize validate step, export pre-check, validate operator (unchanged) |
| `plugins/nmg-game-dev-blender-addon/inspect_core/spatial.py` | `geometry_findings` caller | `/model-asset` `geometry` entries (unchanged) |

## Fix Strategy

Replace `_flipped_faces(bm)` with a per-island count on the same bmesh copy:

1. **Islands.** Group faces into islands by flood fill across edges shared by faces (`edge.link_faces`). Faces that touch only at a vertex are separate islands.
2. **Open or closed.** An island is open when any of its edges has exactly one linked face.
3. **Open island: winding only.**
   - Choose the island's lowest-index face as the seed and propagate an orientation across edges with exactly two linked faces.
   - Two faces agree when they traverse the shared edge in opposite vertex order (compare the order of the edge's two vertices in each face's loop sequence).
   - A face whose winding disagrees with its propagated orientation is marked. The island's count is `min(marked, island_size - marked)`, the minority, so the result does not depend on which face seeded it or which way the sheet faces.
   - Edges with more than two linked faces do not propagate.
   - No normal direction is compared against any outside, so position never matters.
4. **Closed island: outward.** Copy the island's face normals, run `bmesh.ops.recalc_face_normals(bm, faces=island_faces)` on the island alone, and count the faces that reversed. This keeps today's behavior for closed islands, including an island turned entirely inside out.
5. **Total.** Sum the island counts. A non-zero total yields the existing `geometry.normals` finding with the same rule id, target, and message shape.

The bmesh is the caller-owned copy, freed afterwards, so the scene is never mutated (FR5).

New remediation text for `geometry.normals` in `report.py`:

> Closed parts: recalculate normals outside (Shift+N) on that part only, so every face points outward. Open sheets such as floors, roof planes, and decals: do not recalculate outside; flip only the faces wound opposite to their neighbours (Mesh > Normals > Flip), so the sheet is wound consistently and faces the viewer.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` | Per-island count replacing `_flipped_faces` | AC1–AC6, FR1–FR5 |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | `geometry.normals` remediation | AC7, FR7 |
| `docs/asset-contract.md` §3 | Open-sheet, closed-part, and touching-primitive rules | AC8, FR8 |
| `skills/model-asset/SKILL.md`, `docs/skills/model-asset.md` | Same authoring rule and current `geometry.normals` behavior | AC8, FR8 |

The touching-primitive guidance follows the ghost1 envkit practice: either merge by distance so the primitives share vertices, or keep them at least about 0.6 mm apart (well above the 1e-5 m `DUPLICATE_DISTANCE`), so no unmerged vertices coincide.

## Blast Radius

The fix affects both `geometry_findings` callers: `validate_asset` (finalize validate step, export pre-check, `nmggamedev.validate_contract`) and `inspect_asset` (`geometry` entries).

- Closed islands are judged exactly as before.
- Open islands lose position-dependent false positives but still report inconsistent winding.
- The other geometry rules are untouched.
- No step key or report schema changes.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Per-island: winding for open, outward for closed | Selected | Matches FR1–FR4 and is position-independent |
| Skip normals for `environment_piece` only | Rejected | Would also skip closed-island checks, and the rules must apply to every asset type |
| Per-asset open-surface marker | Rejected | Out of scope |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #144 | 2026-11-11 | Initial defect design |
