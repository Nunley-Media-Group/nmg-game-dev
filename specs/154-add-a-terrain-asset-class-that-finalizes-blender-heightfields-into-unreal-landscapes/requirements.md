# Requirements: Terrain asset class — Blender heightfields finalized into Unreal Landscapes

**Issue**: #154
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/67-bake-authored-materials-to-contract-compliant-uv-texture-sets/

## User Story

**As a** game developer authoring region ground with nmg-game-dev
**I want** to author sloped or hilly ground in Blender and finalize it into an Unreal Landscape with paint layers, budgets, and texel-density checks
**So that** regions get real terrain with native LOD and collision, and I no longer fake hills with props beside flat roads

## Background

Every finalized asset ships as an FBX Static Mesh, and region ground is a flat sheet. Non-flat ground has no supported route:

- no asset class describes it;
- the validator has no budget for it;
- the Unreal import step cannot create a Landscape.

Terrain needs a heightmap, paint-layer weightmaps, and per-layer tiling texture sets. Its budgets are a heightmap resolution and a layer count, not triangles and texture sizes.

Asset classes are declared in:

- `plugins/nmg-game-dev-blender-addon/utils/budgets.py`
- `src/nmg_game_dev/quality/mobile_budgets.py`
- `src/nmg_game_dev/pipeline/request.py`
- `src/nmg_game_dev/design/model.py`
- `mcp-servers/finalize/tools.json`
- the finalize CLI and MCP help
- the add-on enum in `operators/_common.py`
- the docs

Only `environment_piece` uses tiling mode, in both the validator and the bake. `src/nmg_game_dev/unreal/import_asset.py` imports Static and Skeletal Meshes only. `src/nmg_game_dev/design/scaffold.py` gives every region level a `/Engine/BasicShapes/Plane` scaled 100×.

## Acceptance Criteria

### AC1: Terrain validates against its own contract

**Given** a collection `<Name>` whose only object is a grid mesh `SM_<Name>` with these properties:
- it is centered on the origin;
- its vertex spacing is 1 m;
- its vertex count per side is a valid Landscape resolution (127, 253, 505, 1009, 2017, or 4033);
- it carries one or more `Layer_<LayerName>` float point attributes with values in 0–1;
- for each layer, the mesh has the material `M_<Name>_<LayerName>`.

**When** the contract validator runs with class `terrain`
**Then** the report passes
**And** its `terrain` object records, for Desktop and Mobile: the heightmap resolution, the height range in metres, the layer names, and the texel density of each layer

### AC2: Finalize exports heightmap, weightmaps, and layer textures

**Given** a terrain collection that passes validation
**When** `finalize_asset` runs with `asset_class` `terrain`
**Then** `<Category>/<Name>/Desktop/` and `<Category>/<Name>/Mobile/` each hold these files:
- a 16-bit grayscale PNG `T_<Name>_Height.png` at that variant's resolution;
- one 8-bit grayscale weightmap `T_<Name>_Layer_<LayerName>.png` per layer of that variant;
- each of that variant's layers' tiling `T_<Name>_<LayerName>_BC`, `_N`, and `_ORM` PNGs.

**And** at every pixel, the weightmap values of a variant sum to exactly 255
**And** `nmg-variants.json` records `"terrain": true` and, for each variant, the resolution, spacing in metres, world-space height range, layer list, and height samples
**And** `Mobile/nmg-asset.json` records `class` `terrain`, `heightmap_px`, `layers`, and `max_texture_px`

### AC3: Mobile variant meets the mobile terrain budget

**Given** a Desktop terrain at 2017×2017 with 4 layers
**When** finalize builds the Mobile variant
**Then** the Mobile heightmap is 1009×1009, takes every 2nd Desktop sample, and covers the same world extent at 2 m spacing
**And** the Mobile variant carries 3 layers. The dropped layer is the one with the lowest total Desktop weight. At every pixel, its weight is redistributed proportionally into the remaining layers. A pixel whose remaining weights are all zero goes wholly to the remaining layer with the highest total weight.
**And** Mobile layer textures are no larger than 1024 px

### AC4: Unreal import creates a Landscape level per variant

**Given** exported Desktop and Mobile terrain variants
**When** the `import_ue` step runs
**Then** for each variant it imports the layer textures and does these steps:
- creates `M_<Name>_Landscape`, a landscape material that blends one paint layer per weightmap;
- creates one layer info `LI_<Name>_<LayerName>` per layer;
- creates the level `/Game/<Category>/<Name>/<Variant>/L_<Name>`.

The level holds a Landscape built from that variant's heightmap and weightmaps through `unreal.NmgLandscapeLibrary`. The Landscape is centered on the origin. Its XY scale is the variant's spacing in centimetres, and its Z scale and Z location reproduce the recorded height range.
**And** the import samples Landscape heights at the sidecar's sample points and fails with `import_ue.terrain_height_mismatch` when any sample differs from the recorded Blender height by more than 5 cm
**And** the heightmap encoding together with the derived Z scale and Z location reproduces every grid height within 5 cm

### AC5: Region scaffold uses a named terrain

**Given** a `region` design entry whose `terrain` field names an `environment` entry with `asset_class` `terrain`, and whose Desktop terrain level exists in Unreal
**When** `/design` scaffold creates the region level
**Then** `L_<Region>` has that terrain level as an always-loaded streaming sublevel and has no flat ground plane
**And** a region entry without `terrain`, or whose terrain level does not exist yet, gets today's flat plane

### AC6: Out-of-contract terrain fails with named findings

**Given** a terrain collection that breaks one of these rules:
- its resolution is not a valid Landscape size;
- its vertex spacing is not 1 m;
- it is not centered on the origin;
- it holds more than one object;
- it has no layers, or a layer has values outside 0–1;
- it exceeds the class budget for resolution or layer count;
- a layer has no mapped material or tiling texture set.

**When** validation or finalize runs
**Then** the run fails with a finding that names the rule (`terrain.resolution_invalid`, `terrain.spacing`, `terrain.not_centered`, `terrain.structure`, `terrain.layer_missing`, `terrain.layer_range`, `terrain.over_budget`, or `terrain.layer_texture_missing`) and states the remediation
**And** no file is exported and no Unreal asset is created
**And** a region entry whose `terrain` names no `environment` entry with `asset_class` `terrain` is reported as `design.unknown_reference` by `design sync`, and by `design scaffold` for that region

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `terrain` is accepted everywhere asset classes are: the add-on budget table and enum, validator, bake, finalize request, MCP schema and CLI help, the ship mobile budget gate, the design `asset_class` values, and the model-asset and finalize-asset skill class lists | Must |
| FR2 | Terrain budgets, overridable through `nmg-budgets.json` like the other classes: Desktop `heightmap_px` ≤ 2017, `layers` ≤ 4, `max_texture_px` 2048; Mobile `heightmap_px` ≤ 1009, `layers` ≤ 3, `max_texture_px` 1024; 1 m vertex spacing. Valid resolutions are 127, 253, 505, 1009, 2017, and 4033. A `heightmap_px` override must be one of them | Must |
| FR3 | Terrain layer materials bake in tiling mode. Each layer's texture must reach ≥ 256 px/m on Desktop and ≥ 128 px/m on Mobile, measured with the terrain mesh's `UVMap` | Must |
| FR4 | Finalize encodes grid heights as a 16-bit grayscale PNG, where 0 is the minimum and 65535 the maximum (a flat terrain encodes 32768), and encodes normalized layer weights as 8-bit weightmaps that sum to 255 per pixel. It records the terrain data in `nmg-variants.json` and `Mobile/nmg-asset.json` | Must |
| FR5 | The Mobile variant is produced in the same run: the heightmap and weightmaps are downsampled by sample stride to the largest valid size within the Mobile budget, layers are reduced to the Mobile limit, and layer textures are resized to the Mobile maximum | Must |
| FR6 | `import_ue` creates the layered landscape material, the layer infos, and a per-variant level holding the Landscape, and checks sampled heights within 5 cm | Must |
| FR7 | A `region` design entry accepts an optional `terrain` field. When the named terrain's Desktop level exists, scaffold adds it as a streaming sublevel instead of the flat plane | Must |
| FR8 | Terrain failures are named findings with remediation, and they stop before any export or Unreal mutation | Must |
| FR9 | `docs/asset-contract.md` gains a terrain section and a §6 budget row. `docs/design-contract.md`, `docs/mcp/finalize.md`, the `finalize-asset` and `model-asset` skills, and `docs/skills/{model-asset,bake-materials,ship}.md` document the class and the region `terrain` field | Must |
| FR10 | The terrain re-import check decodes each variant's exported PNGs. It fails `reimport` when the resolution, layer count, weight sums, or decoded heights (beyond 5 cm) differ from the pre-export report | Must |

## Out of Scope

- Static-mesh terrain export (a sculpted terrain FBX with mesh collision)
- World Partition, multi-landscape tiling, or terrain larger than one Landscape
- Runtime selection between the Desktop and Mobile terrain levels
- Landscape splines, foliage, grass types, and procedural foliage
- Holes or visibility layers in the Landscape
- Replacing the ground of a region level that was already scaffolded

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #154 | 2026-11-11 | Initial feature spec |
