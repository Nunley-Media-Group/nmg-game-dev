# Requirements: Material variants for finalized assets

**Issue**: #148
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As a** game developer finalizing an asset that ships in several looks
**I want** to declare a list of material variants for the asset and have finalize import each one into Unreal as `T_`/`MI_` assets beside the main ones
**So that** recolours of one mesh reach Content through the pipeline, with contract checks, instead of through a hand-written editor script

## Background

Finalize produces one texture set (`T_<Name>_<Part>_{BC,N,ORM}`) and one material instance (`MI_<Name>_<Part>`, parented to `M_NmgORM`) per material. An asset that ships in several colours of the same mesh and UVs has nowhere to declare the extra looks. "Variant" already means Desktop/Mobile throughout the contract and code, so this feature uses the term **material variant**.

The bake merges authored materials into one Body atlas for Desktop and Mobile alike, so after the bake both variants have the same `M_<Name>_<Part>` materials.

## Acceptance Criteria

### AC1: An asset declares its material variants

**Given** an authored asset `<Name>` with material `M_<Name>_<Part>`
**When** the author writes `<Name>.material-variants.json` beside the asset's `.blend`, declaring material variants `Red` (a replacement base-colour texture) and `Blue` (a `Tint` parameter value on `M_NmgORM`) for that material
**Then** finalize uses that file, either found beside the `.blend` passed as `--blend` or passed explicitly as the material-variants path
**And** the `validate` step's report lists each declared material variant with its material and its texture file or parameter values

### AC2: Finalize imports texture-based material variants for Desktop and Mobile

**Given** `<Name>` declares material variant `Red` on `M_<Name>_<Part>` with a replacement base-colour texture
**When** `finalize all` runs
**Then** the Desktop and Mobile export folders each hold `T_<Name>_<Part>_BC_Red.png`, at the size of that folder's `T_<Name>_<Part>_BC.png`
**And** `import_ue` imports it into `/Game/<Category>/<Name>/<Desktop|Mobile>/` beside the main textures
**And** `import_ue` creates `MI_<Name>_<Part>_Red` in the same folder, parented to `M_NmgORM`, with `BaseColor` set to the variant texture and `Normal` and `ORM` set to the main set's textures

### AC3: Finalize imports parameter-based material variants

**Given** `<Name>` declares material variant `Blue` on `M_<Name>_<Part>` with a `Tint` value and no texture
**When** `finalize all` runs
**Then** `import_ue` creates `MI_<Name>_<Part>_Blue` in each of the Desktop and Mobile folders, using the main texture set and setting `Tint` to the declared value
**And** no extra texture is exported or imported for `Blue`
**And** `M_NmgORM` multiplies its base colour by a `Tint` vector parameter whose default is white (1, 1, 1, 1), and the main `MI_<Name>_<Part>` does not set `Tint`

### AC4: The main asset is unchanged

**Given** an asset that declares material variants
**When** `finalize all` runs
**Then** the mesh's material slots are still bound to the main `MI_<Name>_<Part>`
**And** an asset with no declaration file produces the same exports, the same `nmg-variants.json` (no `material_variants` key), and the same `import_ue` material bindings as before

### AC5: The contract checks material variants

**Given** a declaration with one of the following:
- a material variant name that is not PascalCase letters and digits, or whose `MI_<Name>_<Part>_<Variant>` would equal another part's material instance;
- a duplicate material variant name on the same material;
- a material that is not one of the asset's `M_<Name>_<Part>` materials;
- a replacement texture that is missing, not a PNG, not power-of-two square, or not the size of the main base colour;
- a parameter `M_NmgORM` does not have, or a malformed `Tint` value;
- an entry with neither a texture nor parameters

**When** `validate` runs
**Then** it fails with a contract finding whose rule id starts with `material_variant.` and whose message names the asset, the material variant, and the rule
**And** nothing is baked, exported, or imported

### AC6: Material merging is handled

**Given** an asset whose bake merges several authored materials into `M_<Name>_Body`
**When** it declares a material variant on one of the merged authored materials
**Then** `validate` fails with a `material_variant.material_merged` finding that names `M_<Name>_Body` as the material to declare it on
**And** a material variant declared on `M_<Name>_Body` is produced for both Desktop and Mobile

### AC7: The sidecar and import result record material variants

**Given** finalize ran on an asset with material variants
**When** the run finishes
**Then** `nmg-variants.json` has a `material_variants` object that lists, for `desktop` and `mobile`, each material variant with its name, its material, its texture file or parameter values, and its material instance name
**And** the `import_ue` result for each variant lists the imported variant textures and material instance paths

### AC8: Material variants can be listed from Unreal

**Given** `<Name>` was finalized in category `<Category>` with material variants `Red` and `Blue`
**When** the caller runs the finalize MCP tool `list_material_variants` or `python -m nmg_game_dev.finalize material-variants` for `<Category>` and `<Name>`
**Then** the answer gives each material variant's name, the material slot it applies to, and its material instance path for Desktop and for Mobile
**And** an asset with no material variants, or not in Content, returns an empty list, not an error

### AC9: Re-running finalize is idempotent and removes stale material variants

**Given** `<Name>` was finalized with material variants `Red` and `Blue`
**When** `Blue` is removed from the declaration and `finalize all` runs again
**Then** `Red`'s material instance and texture are reused, with no duplicate assets
**And** `import_ue` deletes the `Blue` material instance and any `Blue` texture from both Content folders and lists them as removed in its result
**And** the export folders no longer hold a `Blue` texture

### AC10: The contract and skills document material variants

**Given** the feature is merged
**When** a contributor reads `docs/asset-contract.md`, `skills/finalize-asset/SKILL.md`, and `docs/mcp/finalize.md`
**Then** they find the declaration file name, location, and format, the `T_`/`MI_` naming for material variants, the validation rules, the stale-deletion behavior, and how to list material variants from Unreal

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | A per-asset declaration file `<Name>.material-variants.json`, found beside the `.blend` or passed explicitly, whose entries name a material and a replacement base-colour texture, `M_NmgORM` parameter values, or both | Must |
| FR2 | Contract naming `T_<Name>_<Part>_BC_<Variant>` and `MI_<Name>_<Part>_<Variant>` in `docs/asset-contract.md` | Must |
| FR3 | `validate` (and the export pre-check) checks the declaration and fails with `material_variant.*` findings before any bake or export | Must |
| FR4 | `export` writes variant base-colour textures for Desktop and Mobile at each variant's main base-colour size, and removes stale ones | Must |
| FR5 | `import_ue` imports variant textures and creates or reuses the variant material instances beside the main ones, and deletes stale tagged material-variant assets | Must |
| FR6 | A `Tint` vector parameter on `M_NmgORM`, default white, multiplying the base colour | Must |
| FR7 | `nmg-variants.json` and the `import_ue` result record material variants | Must |
| FR8 | The finalize MCP tool `list_material_variants` and the CLI command `material-variants` list an asset's material variants from Unreal | Must |
| FR9 | The `validate` and `export` step cache keys include the declaration and its texture bytes | Must |

## Out of Scope

- Generating the recoloured textures. The author supplies them, or uses `Tint`.
- Replacement normal or ORM textures for a material variant.
- Masked tinting, and per-instance random tinting in the master material.
- Mesh or UV differences between material variants.
- Runtime selection of a material variant in gameplay code or Blueprints.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #148 | 2026-11-11 | Initial feature spec |
