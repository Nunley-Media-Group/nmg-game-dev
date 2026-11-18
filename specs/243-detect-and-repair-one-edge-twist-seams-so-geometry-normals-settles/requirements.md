# Defect Report: geometry.normals never settles on a mesh with a twist seam

**Issue**: #243
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/232-make-mesh-cleanup-recalculate-normals-the-way-the-geometry-normals-check-judges-them/

## Reproduction

1. Build a closed mesh that joins a surface back to itself with reversed winding through a narrow seam, so that no winding of the island is consistent. Every edge has exactly two faces. Example: a figure-8 Klein bottle with a three-edge tube, 32 x 3 quads.
2. Run contract validate on it, or run Desktop cleanup and then validate.
3. `geometry.normals` reports a large face count (76 of 96 faces) at a location away from the seam. Cleanup never removes the seam, so the finding never clears.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | Cleanup deletes only the faces at the twist seam edges and leaves a mesh that passes and stays stable. Validate reports the seam itself as `geometry.twist_seam`, giving the seam edge count and the seam locations. |
| **Actual** | Cleanup leaves the seam in place. Validate reports a large `geometry.normals` face count at an unrelated location, and the flagged set moves between passes. |

## Acceptance Criteria

### AC1: Cleanup repairs a twist seam with a minimal deletion

**Given** a closed mesh with a twist seam
**When** `clean_mesh()` runs on it
**Then** only the faces linked to the twist seam edges are deleted, and the edges are the ones found after the shared per-island recalculation (6 faces on the `klein(32, 3)` fixture). The contract geometry check on the cleaned mesh reports no `geometry.normals` or `geometry.twist_seam` finding.

### AC2: The repaired mesh is stable

**Given** the mesh cleaned in AC1
**When** `clean_mesh()` and the contract geometry check run on it again, three more times
**Then** the vertex positions and face vertex lists do not change, and no `geometry.normals` or `geometry.twist_seam` finding appears

### AC3: The validator names the seam

**Given** an uncleaned closed mesh with a twist seam
**When** the contract geometry check runs on it
**Then** it reports `geometry.twist_seam` with the number of seam edges (5 on the `klein(32, 3)` fixture). Each sample position is the midpoint of a seam edge, and the twisted island adds no `geometry.normals` finding.

### AC4: The repair is deterministic

**Given** two identical copies of a mesh with a twist seam
**When** `clean_mesh()` runs on each
**Then** both copies end with identical vertex positions, face vertex lists, and face normals

### AC5: Meshes without a twist seam are unaffected

**Given** the clean crate fixture, a correctly facing open quad, and an inside-out closed cube
**When** `clean_mesh()` and the contract geometry check run on them
**Then** twist repair deletes no faces, no `geometry.twist_seam` finding appears, and their other findings are unchanged: the inside-out cube is flagged `geometry.normals` before cleanup, the quad passes, and the crate keeps its triangle count

### AC6: Cleanup reports the twist repair

**Given** asset `Twist` whose `SM_Twist` is the twist-seam fixture, and the clean crate asset
**When** `cleanup_desktop` runs on each
**Then** each object entry carries `twist_repair` with `faces` (deleted face count), `edges` (seam edge count), and `samples` (world-space seam edge midpoints, at most 5). `Twist` reports 6 faces and 5 edges, and the crate reports 0, 0, and an empty list.

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | After the shared per-island recalculation, `clean_mesh()` finds the twist seam edges: edges with two linked faces whose loops walk them in the same direction. It deletes the faces at those edges and any loose geometry, then recalculates, repeating until none remain. | Must |
| FR2 | The contract geometry check detects twist seam edges on each closed island after its recalculation and reports them as `geometry.twist_seam`, with the edge count and edge-midpoint samples. It leaves that island out of `geometry.normals`. | Must |
| FR3 | Twist repair runs before #232's delete-still-flagged step, so a twisted island loses only its seam faces | Must |
| FR4 | Blender headless tests build a closed twist-seam fixture and cover AC1–AC6 | Must |
| FR5 | `cleanup_desktop` reports twist-repair faces, edges, and seam locations per object, and they appear in the finalize variants step output | Should |
| FR6 | `docs/asset-contract.md` section 3, `docs/skills/model-asset.md`, and `skills/model-asset/SKILL.md` describe `geometry.twist_seam`, and a unit test checks that they do | Must |

## Out of Scope

- Changing what `geometry.normals` accepts for open islands or orientable closed islands
- Twist detection on open islands in the validator
- Preventing generators or import sessions from producing twist seams
- Other geometry rules (duplicates, zero-area, non-manifold, loose)

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #243 | 2026-11-18 | Initial defect report |
