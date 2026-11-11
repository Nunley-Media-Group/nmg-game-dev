# Requirements: Measure texel density per material slot and exempt trim-atlas and flat-colour slots

**Issue**: #151
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As a** game developer finalizing environment pieces that mix tiling surfaces with trim-atlas and flat-colour parts
**I want** texel density measured per material slot, with atlas and flat-colour slots exempt
**So that** an asset passes or fails on the density of its tiling surfaces, and a failure tells me which slot to fix

## Background

The contract asks environment pieces for at least 256 px/m on Desktop and 128 px/m on Mobile. Two checks compute one number per mesh, `sqrt(UV area / world area) × texture px`, over every face:
- `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` `_texel_findings()`;
- `bake_core/tiling.py` `check_density()`.

Faces mapped to a trim-atlas swatch, or collapsed onto a flat-colour cell, cover almost no UV area for their world area. They pull the mesh aggregate down even though texel density does not describe how they look. Fences, barriers, signs, rail corridors, sidewalks, and ground chunks dominated by painted pieces measure around 50 px/m, while every tiling surface on them is above the minimum.

## Acceptance Criteria

### AC1: Density is measured per material slot

**Given** an environment piece whose mesh has several material slots
**When** contract validation or the tiling bake checks texel density
**Then** each slot's density is computed from the UV area and world area of the faces assigned to that slot only, and each slot is compared with the variant minimum on its own

### AC2: A mesh dominated by atlas and flat-colour faces passes when its tiling slots are dense enough

**Given** a mesh where one tiling slot meets the minimum, and a declared trim-atlas slot and a flat-colour slot together cover most of the surface, so that the whole-mesh aggregate is below the minimum
**When** the density check runs
**Then** it produces no texel-density finding or error for that mesh

### AC3: A failing slot is named

**Given** a mesh with two tiling slots, one above and one below the minimum
**When** the density check runs
**Then** the `texel.density` finding and the `texel_density` bake error each name the mesh and the failing slot's material, and state the measured px/m, the minimum, and the variant

### AC4: A flat-colour slot is exempt without any marking

**Given** a slot whose faces all have UVs collapsed to a point or a single cell, so that the slot's total UV area is effectively zero
**When** the density check runs
**Then** the slot is treated as flat-colour and exempt, with no marker required from the author

### AC5: A trim-atlas slot is exempt when the author declares it

**Given** a material carrying the documented trim-atlas marker
**When** the density check runs on a mesh using that material
**Then** the slot is exempt regardless of its measured density

### AC6: An undeclared low-density slot still fails

**Given** a slot with non-zero UV area, no trim-atlas marker, and a density below the minimum (for example a large surface mapped once across 0 to 1)
**When** the density check runs
**Then** the slot fails, and the remediation text names both ways out: raise the density, or declare the material as trim-atlas if it is one

### AC7: The report shows what was measured and what was exempt

**Given** a density check that has run on an environment piece
**When** the validation report and the bake report are read
**Then** each slot is listed with its Desktop and Mobile px/m, or with its exemption and the reason (`flat_colour` or `trim_atlas`)

### AC8: The declaration holds through finalize and on the Mobile variant

**Given** an asset with a declared trim-atlas material
**When** finalize runs validate, bake, and variants, and validation runs on the Mobile variant
**Then** the slot is exempt at every step, including on the baked contract material and its `_Mobile` counterpart

### AC9: Single-slot tiling meshes behave as before

**Given** a mesh with one undeclared tiling slot
**When** the density check runs
**Then** it passes or fails at the same density as today, with the same `texel.density` code and `texel_density` reason

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Contract validation computes texel density per material slot for `environment_piece` meshes, from the faces assigned to each slot. | Must |
| FR2 | The tiling bake's density check computes the same per-slot measure. | Must |
| FR3 | A slot whose total UV area is effectively zero is classified as flat-colour and exempt. The cut-off is a named constant. | Must |
| FR4 | A material-level marker declares a material as trim-atlas, and slots using it are exempt. The marker is documented and can be set in Blender's UI and from a script. | Must |
| FR5 | The marker carries over to the baked contract material and to the Mobile variant material. | Must |
| FR6 | The `texel.density` finding and the `texel_density` bake error name the mesh and the failing slot's material, with the measured px/m, the minimum, and the variant. One finding is reported per failing slot. | Must |
| FR7 | The validation report and the bake report list every slot with its densities or its exemption reason. | Must |
| FR8 | Validation and the bake classify and measure slots identically, so a slot cannot pass one and fail the other for a reason other than texture size. | Must |
| FR9 | Remediation text in `contract_core/report.py` and `bake_core/errors.py` describes the per-slot rule and the trim-atlas declaration. | Must |
| FR10 | `docs/asset-contract.md` and `docs/skills/bake-materials.md` state that density applies per tiling slot, define the flat-colour and trim-atlas exemptions, and document the marker. | Must |
| FR11 | The `/model-asset` skill guidance tells the author to set the trim-atlas marker on atlas materials of environment pieces. | Should |
| FR12 | Tests cover AC1 to AC9, including a multi-slot mesh whose whole-mesh aggregate is below the minimum but whose tiling slot passes. | Must |
| FR13 | The finding code `texel.density`, the bake reason `texel_density`, and the 256 / 128 px/m minimums are unchanged. | Must |

## Out of Scope

- A separate, lower density minimum for trim-atlas slots; they are exempt.
- Detecting a trim-atlas slot automatically from its UV layout.
- Checking the texel density of atlas or flat-colour slots for visual quality.
- Density checks for asset classes other than `environment_piece`.
- Changing the minimums, or making them configurable.
- The tiling seam check and the UV overlap check.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #151 | 2026-11-11 | Initial feature spec |
