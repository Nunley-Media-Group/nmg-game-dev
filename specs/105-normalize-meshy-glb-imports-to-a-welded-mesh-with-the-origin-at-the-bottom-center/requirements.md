# Requirements: Normalize Meshy GLB imports to a welded mesh with the origin at the bottom center

**Issue**: #105
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/98-add-optional-meshy-model-generation-and-retexturing-through-the-meshy-api/

## User Story

**As an** agent authoring a Meshy-generated asset
**I want** the imported `SM_<Name>` to arrive welded, with its origin at the bottom center at the world origin
**So that** it passes the contract pivot checks and skins as one connected mesh without manual cleanup

## Background

The glTF importer splits vertices along every UV seam, so a Meshy character arrives as hundreds of disconnected islands. Its origin sits at the bounding-box center rather than at the feet, and it carries imported custom split normals. `scripts/blender/meshy_session.py` op `import_glb` imports the GLB into collection `<Name>` as `SM_<Name>` with `M_<Name>_Body` and does no geometry normalization. `src/nmg_game_dev/meshy/jobs.py` calls it.

## Acceptance Criteria

### AC1: Welded single mesh

**Given** a GLB whose mesh is split at UV seams (vertices duplicated at the same position)
**When** `import_glb` runs
**Then** `SM_<Name>` has every pair of vertices within `1e-5` m merged, so its connected-island count equals the source model's, and its face count, per-face-corner UV coordinates, and material slots are unchanged

### AC2: Bottom-center origin

**Given** any imported GLB, including one whose objects carry a non-identity transform
**When** `import_glb` runs
**Then** `SM_<Name>` has identity location, rotation, and scale, and its world bounding box has its X and Y center and its minimum Z each within `1e-3` m of 0, so the contract's `pivot.bottom_center` check passes

### AC3: Normals

**Given** an imported mesh with custom split normals
**When** `import_glb` runs
**Then** the mesh has no custom split normals, faces are smooth-shaded with edges sharper than 30° marked sharp, and on a closed mesh every face normal points away from the mesh's interior

### AC4: Result reports the normalization

**Given** a successful `import_glb`
**When** its result is returned
**Then** it carries `merged_vertices` (vertices removed by the merge, an integer ≥ 0) and `origin_offset` (the `[x, y, z]` translation applied to the geometry, in meters) alongside `collection`, `mesh`, and `material`. A succeeded Meshy generate job's `result` carries the same two keys

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Merge vertices within `1e-5` m after GLB import, keeping UVs and materials | Must |
| FR2 | Bake object transforms into the mesh, then translate the geometry so the bottom center sits at the world origin, leaving identity transforms | Must |
| FR3 | Clear custom normals, smooth by a 30° angle, and recalculate normals outward | Should |
| FR4 | Report `merged_vertices` and `origin_offset` in the `import_glb` and generate-job results, and document them in `docs/mcp/meshy.md` | Should |

## Out of Scope

- Decimation or retopology
- Changing the Meshy API request parameters
- Normalizing collections that were not imported through `import_glb`

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #105 | 2026-10-31 | Initial feature spec |
