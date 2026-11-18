# Defect Report: Mesh cleanup recalculates normals differently from the geometry.normals check

**Issue**: #232
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/140-fix-finalize-export-failing-the-contract-on-mobile-lods-the-variants-step-decimated/

## Reproduction

1. Build a closed mesh with no consistent orientation that passes `geometry_findings` with no geometry findings. Example: a figure-8 Klein bottle with one fin triangle on an edge, wound so that the open-island winding check passes.
2. Run `cleanup_desktop` on it, or `optimize_mobile` after it. Both call `clean_mesh()`.
3. Run contract validate on the cleaned Desktop mesh and on the Mobile LODs.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | A mesh that passes validate before cleanup passes it after cleanup. Desktop cleanup and every Mobile LOD have no `geometry.normals` finding. |
| **Actual** | `clean_mesh()` drops the fin and recalculates normals over the whole mesh. The per-island check then flips faces on the result, so validate reports `geometry.normals` on the Desktop mesh and on the Mobile LODs derived from it. |

## Acceptance Criteria

### AC1: Cleanup output never fails geometry.normals

**Given** a closed mesh where normals recalculated the way `clean_mesh()` does today leave faces that the per-island `geometry.normals` check flags
**When** `clean_mesh()` runs on it
**Then** `geometry_findings` on the cleaned mesh reports no `geometry.normals` finding

### AC2: A mesh that passes validate still passes after Desktop cleanup

**Given** an asset whose source mesh has no geometry findings in contract validate, and which today's clean leaves with `geometry.normals` faces
**When** `cleanup_desktop` runs on it
**Then** contract validate on the cleaned Desktop mesh reports no `geometry.*` finding

### AC3: Mobile LODs never introduce geometry.normals failures

**Given** the same asset after Desktop cleanup
**When** `optimize_mobile` fits and decimates its Mobile LODs
**Then** contract validate reports no `geometry.normals` finding on any Mobile LOD

### AC4: Faces with no consistent orientation are removed deterministically

**Given** a closed island whose faces are still flagged after the shared per-island recalculation
**When** `clean_mesh()` runs on two identical copies of that mesh
**Then** it deletes the flagged faces and adds or reshapes none, and both copies end with identical vertex positions, face vertex lists, and face normals

### AC5: Normals rule and existing clean behavior are preserved

**Given** a correctly facing open surface, an inside-out closed cube, and a clean closed crate
**When** the contract check runs on them, and `clean_mesh()` runs on the cube and the crate
**Then** the open surface passes and the inside-out cube is flagged before cleanup. Cleanup turns the cube outward without deleting faces, and the cleaned crate keeps its triangle count and has no geometry findings.

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `clean_mesh()` and the `geometry.normals` check recalculate normals through one shared per-island routine in `contract_core/geometry.py`, with the same island grouping and face order | Must |
| FR2 | After the shared recalculation, `clean_mesh()` deletes every face the `geometry.normals` rule flags on the written mesh, then any loose geometry, and repeats until no face is flagged. The result is deterministic. | Must |
| FR3 | Desktop cleanup and Mobile LOD fitting/decimation produce meshes with no `geometry.normals` findings | Must |
| FR4 | Blender headless tests reproduce the failure with a Klein bottle fixture and cover AC1–AC5 | Must |

## Out of Scope

- Changing what the `geometry.normals` rule accepts (open-island winding and closed-island outward rules)
- The whole-mesh normal recalculation in `scripts/blender/meshy_session.py`
- Other geometry rules (duplicates, zero-area, non-manifold, loose)

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #232 | 2026-11-18 | Initial defect report |
