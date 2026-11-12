# Requirements: Reduce a generated high-poly asset to its Desktop budget and bake its look onto the reduced mesh

**Issue**: #139
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/67-bake-authored-materials-to-contract-compliant-uv-texture-sets/

## User Story

**As a** game developer bringing a generated model (Meshy or similar) into a consumer project
**I want** one supported step that reduces the asset to its class's Desktop triangle budget and bakes the original's look onto the reduced mesh
**So that** the asset passes the normal finalize run and still looks like the model I generated

## Background

Generated models arrive at 200,000 to 1,400,000 triangles, while the Desktop budgets are 2,000 to 60,000 triangles. `validate` fails an over-budget Desktop collection with `budget.tris`.

The bake (`bake_core.bake_asset`) bakes each mesh's own materials onto that same mesh. It has no source-to-target bake, no cage or ray distance setting, and no measure of unbaked texels. Triangle reduction exists only for the Mobile variant.

Budgets come from `utils/budgets.py` (`resolve_budget(asset_class, budgets_path, variant="desktop")`), including `nmg-budgets.json` overrides. Validation, content hashing, and export read only `<Name>` and `<Name>_Mobile`. Long Blender work runs as a background job with polling, because a Blender MCP call times out at 180 s.

## Acceptance Criteria

### AC1: An over-budget asset is reduced to its Desktop triangle budget

**Given** a collection `<Name>` of unrigged meshes whose triangle total is above the Desktop budget for its asset class
**When** the reduce step runs for `<Name>` and that class
**Then** `<Name>` holds one reduced mesh per original part
**And** each reduced mesh keeps its part's object name, transform, origin, and parent
**And** their triangle total is at or below the resolved Desktop budget, including `nmg-budgets.json` Desktop overrides

### AC2: The original is kept in a non-exported `<Name>_High` collection

**Given** a completed reduce run
**When** the scene is inspected and then finalized
**Then** the original meshes and their authored materials are in a top-level collection `<Name>_High`, hidden in the viewport and in renders, with unchanged geometry and materials
**And** each original object is named `<object>_High`
**And** no object from `<Name>_High` is validated, hashed, or written to the Desktop or Mobile export

### AC3: The triangle budget is split between parts by surface area

**Given** a multi-part asset and no per-part overrides
**When** the reduce step runs
**Then** each part's triangle target is its share of the Desktop budget in proportion to its world-space surface area, with at least 12 triangles per part
**And** a part already at or below its target is not decimated
**And** the result reports each part's source triangles, target, and final triangles

### AC4: Per-part overrides win over the automatic split

**Given** a caller passes a `share` (greater than 0, at most 1) or a `tris` target for some parts
**When** the reduce step runs
**Then** those parts use the given values, and the remaining budget is split by surface area among the other parts
**And** overrides are refused before any change is made, with these errors:
  - `reduce.overrides_exceed_budget` when they exceed the Desktop budget or leave fewer than 12 triangles for any other part;
  - `reduce.unknown_part` when they name an unknown part;
  - `reduce.invalid_override` when one part has both `share` and `tris`, or a value out of range.

### AC5: All parts share one non-overlapping atlas

**Given** a completed reduce run on a multi-part asset
**When** the UVs are inspected
**Then** every reduced mesh has exactly one UV map named `UVMap`
**And** all islands of all parts lie inside 0 to 1, and no two faces overlap across the whole asset

### AC6: The original's look is baked onto the reduced mesh, per part

**Given** an original whose materials are procedural or attribute-driven (for example vertex color), image-textured, or a mix
**When** the reduce step runs
**Then** base color, roughness, metallic, tangent-space normal, and ambient occlusion are baked from each original part onto its own reduced part only
**And** they go into one texture set `T_<Name>_Body_{BC,N,ORM}` at the class's Desktop `max_texture_px`. BC is sRGB. N is Non-Color with the OpenGL convention. ORM is Non-Color with R = AO, G = roughness, and B = metallic.

### AC7: Cage and ray distance are configurable

**Given** a caller passes `cage_extrusion` and `max_ray_distance`, for the whole asset or for named parts
**When** the reduce step runs
**Then** the bake uses those values for the parts they apply to
**And** the defaults apply elsewhere: `cage_extrusion` 0.03 m and `max_ray_distance` 0.10 m
**And** the result reports the values used for each part

### AC8: Unbaked texel coverage is reported

**Given** a completed bake
**When** the result is read
**Then** it reports, for each part, `unbaked_share`: the share of that part's island texels that no ray from its reduced part hit on its original

### AC9: Too many ray misses fail the step and leave the scene unchanged

**Given** a part whose unbaked share is above `miss_threshold` (default 0.01, configurable)
**When** the reduce step runs
**Then** it fails with `reduce.bake_misses`, naming the part, its unbaked share, and the cage extrusion and ray distance used
**And** the scene's collections, objects, meshes, UV maps, materials, and images are as they were before the run

### AC10: The reduced asset passes the normal finalize run

**Given** a completed reduce run
**When** `finalize_asset` runs on `<Name>` with no reduce-specific arguments
**Then** every reduced face uses one material `M_<Name>_Body` wired to the baked texture set
**And** `validate` reports no `budget.tris`, material, or UV finding
**And** the finalize bake keeps the atlas layout, including for an `environment_piece`, which reduce tags with the custom property `nmg_reduced` so that the finalize bake uses unique mode
**And** the run completes through `reimport`

### AC11: A rerun rebuilds from `<Name>_High`

**Given** `<Name>_High` already exists from an earlier reduce run
**When** the reduce step runs again with a different cage, ray distance, shares, or threshold
**Then** the reduced meshes and textures in `<Name>` are rebuilt from `<Name>_High`
**And** `<Name>_High` is neither modified nor duplicated

### AC12: An asset already in budget is left alone

**Given** a collection whose triangle total is at or below the Desktop budget and that has no `<Name>_High`
**When** the reduce step runs
**Then** nothing in the scene changes, and the result has `state` `within_budget`

### AC13: A rigged or unsupported asset is refused

**Given** a collection that contains an armature, or a request with asset class `terrain`
**When** the reduce step runs
**Then** it fails before any change with `reduce.rigged` ("reduce before rigging") or with `reduce.class_unsupported`

### AC14: The step is reachable from the panel, the agent, the CLI, and a background job

**Given** the add-on and the finalize MCP server are installed
**When** a user runs the step from the Blender panel operator, from `execute_blender_code` (`reduce_core.run_for_mcp`), from the CLI (`python -m nmg_game_dev.finalize reduce`), or as the MCP tool `reduce_asset`
**Then** all four run the same implementation with the same inputs and result shape
**And** the MCP tool returns a job id at once, or the result within `wait_seconds` (at most 150), and reports progress through `get_finalize_job`
**And** the job runs in background Blender against a checkpoint of the open session
**And** it loads the reduced `<Name>` and `<Name>_High` back into the session only when the session's `<Name>` is unchanged since the checkpoint. Otherwise it fails with `reduce.session_changed` and the result `.blend` path.

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Decimate each mesh part of `<Name>` so the asset total is at or below the resolved Desktop triangle budget | Must |
| FR2 | Keep the originals in a hidden top-level `<Name>_High` collection that validation, hashing, variants, and export ignore | Must |
| FR3 | Split the budget between parts by world-space surface area; accept per-part `share` or `tris` overrides; refuse invalid or over-budget overrides before any change | Must |
| FR4 | Unwrap all reduced parts into one non-overlapping 0 to 1 atlas on a single `UVMap` | Must |
| FR5 | Bake base color, roughness, metallic, normal, and AO from each original part onto its reduced part, including procedural and attribute-driven materials | Must |
| FR6 | Accept `cage_extrusion` and `max_ray_distance`, asset-wide and per part, with defaults of 0.03 m and 0.10 m | Must |
| FR7 | Report the unbaked share per part, and fail above a configurable `miss_threshold` (default 0.01) with the scene unchanged | Must |
| FR8 | Leave one material `M_<Name>_Body` on the reduced meshes, wired to `T_<Name>_Body_{BC,N,ORM}`. Its images are packed into the `.blend` so they persist through save, the finalize checkpoint, and load-back | Must |
| FR9 | Rerun from `<Name>_High` when it exists; make no change when already in budget; refuse an armature or the `terrain` class | Must |
| FR10 | Expose one implementation through a panel operator, `reduce_core.run_for_mcp`, the CLI `reduce` command, and the MCP tool `reduce_asset` as a background job with polling and guarded load-back | Must |
| FR11 | Return a result with `state`, per-part source, target, and final triangles, the cage and ray distance used, the unbaked share, the texture paths, and a one-line `summary` | Must |
| FR12 | Document the step, `<Name>_High`, `nmg_reduced`, and the changed Desktop rule in `docs/asset-contract.md`, `docs/mcp/finalize.md`, `docs/skills/reduce-to-budget.md`, `docs/skills/bake-materials.md`, and the `finalize-asset` skill | Should |

## Out of Scope

- Reducing rigged or skinned meshes while preserving skin weights
- Manual or quad retopology; the reduced mesh comes from decimation
- Transparency, emission, and any channel beyond base color, roughness, metallic, normal, and ambient occlusion
- More than one atlas or material on the reduced asset
- Running the reduction automatically inside `finalize_asset`
- Changes to Mobile variant generation and its LODs
- Changes to Meshy import or generation

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #139 | 2026-11-11 | Initial feature spec |
