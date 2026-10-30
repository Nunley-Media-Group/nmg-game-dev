# Requirements: Bake authored materials to contract-compliant UV texture sets

**Issue**: #67
**Date**: 2026-10-30
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/30-add-contract-validation-re-import-check-and-review-renders/

## User Story

**As an** NMG game developer
**I want** one step that bakes whatever materials the agent authored on an asset into contract-compliant UV textures
**So that** assets look the same in Unreal as they did in Blender, however they were textured during authoring

## Background

Texturing happens during freeform authoring. Sources include AI textures from the local texture backends (#7), Blender procedural materials, hand-tuned node graphs, or a mix, often with world-space triplanar or position-driven coordinates that look right in Blender but don't survive FBX export.

The asset contract (`docs/asset-contract.md` §4) requires that, at export time, each material is a Principled BSDF fed only by Image Texture nodes sampling `UVMap`, a Normal Map node, and a Separate Color node for ORM. Textures are packed as `T_<Name>_<Part>_BC` (sRGB), `_N` (Non-Color, OpenGL), and `_ORM` (R=AO, G=roughness, B=metallic, Non-Color). Section 6 sets per-class Desktop/Mobile texture sizes and material limits; environment pieces use tiling mode with a minimum texel density. This issue adds the deterministic bake step that gets any authored material there. Because it bakes whatever exists, procedural materials need no separate path.

Today `src/nmg_game_dev/pipeline/stages/texture.py` raises `PipelineError("texture.not_implemented")`. The Blender add-on's `variants_core` (#33) later copies baked images into the Mobile variant and fails when the Mobile material count exceeds the class limit. Contract validation (#30) accepts the pre-bake render this step produces.

## Acceptance Criteria

### AC1: Bake any authored material to the contract texture set

**Given** an asset collection of a unique-bake class whose materials use any mix of image textures, procedural nodes, and triplanar or position-driven coordinates
**When** the bake runs
**Then** every mesh in the collection ends with exactly one UV map `UVMap`. A valid existing non-overlapping layout is kept unchanged; otherwise all meshes are unwrapped jointly into a new one
**And** for each material, base color, normal, roughness, metallic, and AO are baked and written as `T_<Name>_<Part>_BC.png` (sRGB), `T_<Name>_<Part>_N.png` (Non-Color, OpenGL), and `T_<Name>_<Part>_ORM.png` (Non-Color, R=AO, G=roughness, B=metallic)
**And** each material is rewired to a Principled BSDF fed only by Image Texture nodes, a Normal Map node on `UVMap`, and a Separate Color node splitting ORM, and is named `M_<Name>_<Part>`
**And** a pre-bake and a post-bake render of the three-quarter view match within the documented tolerance (mean absolute difference ≤ 0.03 and at most 2% of asset pixels differing by more than 0.25 in any channel)

### AC2: Tiling mode for environment pieces

**Given** an `environment_piece` asset whose meshes have UVs that overlap or extend past 0–1
**When** the bake runs
**Then** each tiling material is baked to a seamless BC / N / ORM set at the class's per-texture resolution (opposite edges match within a mean absolute difference of 0.04)
**And** the existing UV layout is kept (only renamed to `UVMap` when needed)
**And** each mesh's texel density is checked against the contract minimum (256 px/m Desktop, 128 px/m Mobile) instead of requiring a non-overlapping layout

### AC3: Desktop and Mobile texture resolutions

**Given** the asset's class budget from the contract, or a project `nmg-budgets.json` override
**When** the bake completes
**Then** the Desktop set is written to `<out>/Desktop/` at the class's Desktop texture size and the Mobile set to `<out>/Mobile/` at its Mobile texture size, with identical file names in both folders
**And** the result records `texture_bytes_desktop`, `texture_bytes_mobile`, and the per-variant texture paths

### AC4: Materials are merged when they exceed the Mobile limit

**Given** a unique-bake asset whose material count exceeds the class's Mobile material limit (for example, three materials on a `standard_prop`, whose Mobile limit is 1)
**When** the bake runs
**Then** all materials are baked into one texture set `T_<Name>_Body_{BC,N,ORM}` on a joint non-overlapping `UVMap` and every face uses the single material `M_<Name>_Body`
**And** an asset at or under the Mobile limit keeps one baked material per authored material

### AC5: Agent-callable and pipeline-callable

**Given** an authoring session (through the Blender MCP's `execute_blender_code` or the `nmggamedev.bake_materials` operator) or the pipeline `texture` stage
**When** either invokes the bake on a named collection
**Then** the same `bake_core.bake_asset` implementation runs and returns the texture paths, texture byte totals, proof metrics, and a one-line summary the agent can report
**And** the pipeline `texture` stage returns a `StageArtifact` whose sidecar carries those fields

### AC6: Bake fails loudly

**Given** a material the bake can't represent (alpha below 1 or linked, transmission above 0 or linked, emission strength above 0 with non-black or linked color, a shader node other than Principled BSDF / Mix Shader / Add Shader, or linked Volume or Displacement outputs), a mesh whose UVs can't be generated, a tiling material that isn't seamless, texel density below the minimum, or a proof mismatch beyond tolerance
**When** the bake runs
**Then** it raises an error with code `texture.bake_failed`, naming the material or mesh and the reason, with a remediation (surfaced as `PipelineError` from the pipeline stage)
**And** the asset's original materials, UV maps, and render visibility are restored

### AC7: Idempotent

**Given** an asset that was already baked and is unchanged
**When** the bake runs again with the same output folder, class, and budgets
**Then** it is a cache hit keyed on mesh and material content, nothing is rebaked, and the PNG files are left untouched

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Replace the `texture.not_implemented` placeholder with a pipeline stage that invokes the bake through the Blender MCP and maps bake errors to `PipelineError` | Must |
| FR2 | Bake and pack BC / N / ORM per contract §4, and rewire materials for FBX export (unique-bake and tiling modes) | Must |
| FR3 | Per-variant resolutions from the contract budget table (`utils/budgets.py`), with `nmg-budgets.json` overrides for Desktop and Mobile | Must |
| FR4 | Merge all materials into one `M_<Name>_Body` atlas when the material count exceeds the class's Mobile limit (unique-bake only) | Must |
| FR5 | One implementation, `bake_core.bake_asset`, used by the operator, `execute_blender_code`, and the pipeline stage | Must |
| FR6 | Proof in Blender: render the baked materials, compare against the pre-bake render, and fail beyond tolerance. Write both renders for the #30 proof sheet | Must |
| FR7 | Content-hash cache hit on an unchanged, already-baked asset | Must |
| FR8 | Blender headless tests covering a procedural material, a triplanar material, an image-texture material, tiling, merging, failures, and the cache hit | Must |

## Out of Scope

- Generating textures (#7)
- Mesh decimation, LODs, Mobile mesh copies, and FBX export (#33)
- Contract validation, the re-import check, and the proof sheet compositor (#30)
- Wiring the bake into the reshaped finalize flow and running it as a background Blender job (#69)
- Automatic texture candidate scoring or selection
- Merging tiling materials into an atlas

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #67 | 2026-10-30 | Initial feature spec |
