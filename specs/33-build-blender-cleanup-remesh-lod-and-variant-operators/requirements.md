# Requirements: Blender cleanup, decimate, LOD, and variant operators

**Issue**: #33
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As an** NMG game developer authoring assets freeform in Blender
**I want** the add-on's cleanup, optimize, and generate-variants operators to turn a finished asset into contract-compliant Desktop and Mobile FBX variants
**So that** every asset gets a full-quality Desktop variant and an in-budget Mobile variant with LODs, plus the metrics the quality gates read, without any external service

## Background

The add-on registers `nmggamedev.cleanup_desktop`, `nmggamedev.optimize_mobile`, and `nmggamedev.generate_variants`, but each is a stub that only logs. The asset contract (`docs/asset-contract.md`) defines the deliverable:

- one collection `<Name>` with root mesh `SM_<Name>` (and optional `SM_<Name>_<Part>` children);
- baked texture sets `T_<Name>_<Part>_BC/_N/_ORM` on materials `M_<Name>_<Part>`;
- per-class mobile budgets (triangles, max texture size, material count) in §6;
- FBX export to `<Category>/<Name>/Desktop/` and `<Category>/<Name>/Mobile/`, with identical object, material, and texture names in both exports.

The pipeline's `variants` stage reads `desktop_path`, `mobile_path`, `poly_count_desktop`, `poly_count_mobile`, `texture_bytes_desktop`, and `texture_bytes_mobile` from the Blender result. The ship-time budget gate (#6) reads `Mobile/nmg-asset.json` with `class`, `tris`, `max_texture_px`, and `materials`.

## Acceptance Criteria

### AC1: Desktop and Mobile variants are exported as separate assets with identical names

**Given** a collection `Crate` with root mesh `SM_Crate` (about 12,000 triangles) and a baked material `M_Crate_Body` using 2048 px `T_Crate_Body_BC/_N/_ORM` images
**When** `nmggamedev.generate_variants` runs with collection `Crate`, category `Props`, class `standard_prop`, and an export root
**Then** `<root>/Props/Crate/Desktop/SM_Crate.fbx` and `<root>/Props/Crate/Mobile/SM_Crate.fbx` exist, each beside its own `T_Crate_Body_BC.png`, `T_Crate_Body_N.png`, and `T_Crate_Body_ORM.png`
**And** importing each FBX into an empty scene yields the mesh `SM_Crate` and material `M_Crate_Body`, with no `_Mobile` suffix on any object, material, or image in the Mobile export

### AC2: Desktop cleanup preserves quality

**Given** the `Crate` collection with unapplied modifiers, duplicate vertices, loose vertices, a zero-area face, and inward normals on part of the mesh
**When** `nmggamedev.cleanup_desktop` runs on `Crate`
**Then** modifiers are applied, duplicate and loose vertices and zero-area faces are removed, and normals point outward
**And** no decimation happens: the triangle count changes only by the removed degenerate geometry, and the Desktop textures keep their original resolution

### AC3: The Mobile variant is decimated to budget with two LODs

**Given** the cleaned `Crate` and class `standard_prop` (mobile budget 3,000 triangles, 1,024 px, 1 material)
**When** `nmggamedev.optimize_mobile` runs
**Then** collection `Crate_Mobile` contains an Empty `SM_Crate_Mobile` with `fbx_type = "LodGroup"` and child meshes `SM_Crate_Mobile_LOD0`, `_LOD1`, `_LOD2`
**And** LOD0 has at most 3,000 triangles, and LOD1 and LOD2 have at most 50% and 25% of LOD0's triangles
**And** the Mobile material uses copies of the baked textures scaled to 1,024 px (textures already at or below 1,024 px keep their size)

### AC4: Sidecars record metrics and budget settings

**Given** a completed `generate_variants` run for `Crate`
**When** the export folder is read
**Then** `<root>/Props/Crate/nmg-variants.json` records the class, the applied mobile budget, Desktop and Mobile FBX paths, triangle counts per variant and per LOD, LOD level count, texture byte totals per variant, max Mobile texture size, and material counts
**And** `<root>/Props/Crate/Mobile/nmg-asset.json` contains `class`, `tris` (LOD0), `max_texture_px`, and `materials`
**And** the operator's result (also stored on `scene.nmg_game_dev.last_result`) includes `desktop_path`, `mobile_path`, `poly_count_desktop`, `poly_count_mobile`, `texture_bytes_desktop`, and `texture_bytes_mobile`

### AC5: Results are deterministic

**Given** the same input `.blend` state
**When** `generate_variants` runs twice into two export roots
**Then** the two `nmg-variants.json` files are identical apart from their paths, and the triangle counts per LOD match exactly

### AC6: Budget overrides apply

**Given** an `nmg-budgets.json` setting `standard_prop.tris` to 5,000, passed as the operator's budgets file
**When** `optimize_mobile` runs on `Crate`
**Then** LOD0 has at most 5,000 triangles and the sidecar's applied budget shows 5,000

### AC7: Unsupported inputs fail with a remediation

**Given** an asset whose material uses non-image texture nodes (unbaked), or whose Mobile copy has more materials than the class limit, or a collection or `SM_<Name>` root that doesn't exist
**When** a variant operator runs
**Then** it returns `CANCELLED` and reports `variants.unbaked_material`, `variants.mobile_material_limit`, or `variants.asset_not_found` with a message naming the material or object and a remediation
**And** no FBX or sidecar is written for that run

### AC8: Processing is local

**Given** network sockets are blocked for the Blender process
**When** `generate_variants` runs on `Crate`
**Then** it completes successfully

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Replace the three operator stubs with real operators sharing one core module that is callable from operators, `execute_blender_code`, and the finalize pipeline | Must |
| FR2 | Desktop cleanup: apply modifiers, merge by distance, delete loose geometry, dissolve degenerate faces, recalculate normals outward; no decimation | Must |
| FR3 | Mobile: copy the Desktop hierarchy into `<Name>_Mobile`, collapse-decimate to the mobile triangle budget, build LOD1/LOD2 at 50%/25%, and wrap them in an `fbx_type = "LodGroup"` Empty; assets with child parts get LOD0 only | Must |
| FR4 | Mobile textures: downscaled copies of baked images to the class's mobile max size; fail on unbaked materials or too many materials | Must |
| FR5 | Export each variant as FBX per contract §7, with names identical across variants, and PNG textures written beside the FBX | Must |
| FR6 | Budget table mirrors contract §6 (all five classes), with `nmg-budgets.json` override support | Must |
| FR7 | Write `nmg-variants.json` and `Mobile/nmg-asset.json`, and return the pipeline result keys | Must |
| FR8 | Blender headless tests on a generated fixture asset; a unit test keeps the add-on budget table in sync with `docs/asset-contract.md` | Must |
| FR9 | Update contract §5 to describe the Mobile LOD group export | Must |

## Out of Scope

- Baking authored materials or merging materials into an atlas (#67)
- Contract validation, re-import checks, and review renders (#30)
- Running the operators in a background Blender job, and pipeline stage wiring (#69)
- UE import and runtime resolver changes

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #33 | 2026-10-29 | Initial feature spec |
