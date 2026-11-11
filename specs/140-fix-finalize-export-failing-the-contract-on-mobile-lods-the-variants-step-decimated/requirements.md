# Defect Report: Fix finalize export failing the contract on Mobile LODs the variants step decimated

**Issue**: #140
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/33-build-blender-cleanup-remesh-lod-and-variant-operators/

## Reproduction

1. Author a rigged character collection whose Desktop mesh is above the Mobile triangle budget and contains a tiny face on a non-manifold edge (and, for the `reimport.tris` case, two faces with the same vertex set).
2. Run the finalize `validate` step. It passes.
3. Run the finalize `variants` step, then the `export` step.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | Every mesh the `variants` step produces passes the same geometry and pivot rules the Desktop mesh passed, so `export` and `reimport` succeed without hand edits to `<Name>_Mobile`. |
| **Actual** | `export` fails its pre-export contract with `pivot.bottom_center` on `SM_<Name>_Mobile` (bottom centre moved 0.3 to 1.0 mm by decimation) and with `geometry.zero_area` and `geometry.normals` on every LOD. Assets with duplicate Desktop faces fail `reimport` with `reimport.tris`. |

## Acceptance Criteria

### AC1: Decimated LODs have no degenerate or loose geometry

**Given** a rigged asset whose Desktop mesh is above the Mobile budget and whose decimation produces a zero-area face
**When** the `variants` step builds `<Name>_Mobile`
**Then** contract validation reports no `geometry.zero_area` and no `geometry.loose` finding on any Mobile LOD

### AC2: Decimated LODs have stable normals

**Given** a Desktop mesh containing a tiny face on a non-manifold edge
**When** `cleanup_desktop` and then the `variants` step run
**Then** contract validation reports no `geometry.normals` finding on the Desktop mesh or on any Mobile LOD, and repeating the validation gives the same result

### AC3: The Mobile root is re-seated after decimation

**Given** an asset where decimation removes a bounding-box extreme vertex
**When** the `variants` step builds `<Name>_Mobile`
**Then** the Mobile variant's origin and bounding-box bottom centre are within the contract pivot tolerance of the world origin and no `pivot.bottom_center` finding is reported

### AC4: Desktop cleanup removes non-manifold-edge faces and duplicate faces

**Given** a Desktop mesh with a face on a non-manifold edge and two faces that share an identical vertex set
**When** `cleanup_desktop` runs
**Then** the offending non-manifold face is removed, one face remains for the shared vertex set, and the reported `tris_after` reflects the removals

### AC5: Re-import triangle counts match

**Given** the asset from AC4 taken through `variants`, `export`, and `reimport`
**When** the reimport check compares each FBX with its report
**Then** no `reimport.tris` finding is reported for the Desktop or any Mobile mesh

### AC6: Budgets, skinning, and layout are preserved

**Given** rigged, unrigged single-mesh, and multi-part assets
**When** the `variants` step runs with the post-decimation clean
**Then** every LOD stays within its triangle target, rigged LODs keep their Armature modifier and vertex groups, the LOD layout (rigged chain, LodGroup, or LOD0-only parts) is unchanged, and the `lod_tris` in the step result equal the cleaned meshes' counts

### AC7: Clean meshes are unchanged

**Given** an asset whose Desktop mesh and decimated LODs already satisfy the contract
**When** `cleanup_desktop` and the `variants` step run
**Then** triangle counts and pivots match the previous behavior and identical input yields identical output

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Every mesh `fit_meshes` returns is cleaned with the same routine Desktop cleanup uses: merge doubles, degenerate dissolve, delete of faces whose area is below the contract's zero-area limit, loose delete, and a normal recalculation that gives the same orientation on the stored mesh and its evaluated copy. This covers the rigged chain, the LodGroup, and the multi-part path. | Must |
| FR2 | After the Mobile meshes are fitted and cleaned, the Mobile variant is re-seated so its bounding-box bottom centre and origin are on the world origin within the contract pivot tolerance, without breaking rigged skinning or the LodGroup hierarchy. | Must |
| FR3 | The shared clean routine removes faces on non-manifold edges (edges with more than two faces) that cause unstable normal orientation, keeping the two largest faces on each such edge. | Must |
| FR4 | The shared clean routine removes duplicate faces (identical vertex sets), keeping one, for Desktop meshes and for Mobile meshes that were not decimated. | Must |
| FR5 | Triangle totals after the clean stay at or below the fit target, and reported `lod_tris` and `tris_after` are measured after the clean. | Must |
| FR6 | Blender regression tests cover: a zero-area face after decimation, a non-manifold tiny face, a pivot shift from a lost extreme vertex, duplicate Desktop faces through reimport, and an already-clean asset. | Must |
| FR7 | `docs/asset-contract.md` states that the `variants` step cleans and re-seats the meshes it produces. | Should |

## Out of Scope

- Changing contract tolerances (`contract_core/validate.py` `PIVOT_TOLERANCE`, `contract_core/geometry.py` `ZERO_AREA_LIMIT`) or relaxing any contract rule for Mobile.
- Changing the decimation algorithm, ratios, or LOD targets.
- Repairing non-manifold topology beyond removing the offending faces.
- Cleanup of authored geometry before the `validate` step.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #140 | 2026-11-11 | Initial defect report |
