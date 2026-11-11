# Design: Terrain asset class — Blender heightfields finalized into Unreal Landscapes

**Issue**: #154
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/67-bake-authored-materials-to-contract-compliant-uv-texture-sets/

## Overview

`terrain` is a new asset class that runs through the same six finalize steps. Each step branches on the class:

- **validate** checks the grid, layer, and budget rules.
- **bake** uses the existing tiling mode on the layer materials.
- **variants** derives Desktop and Mobile heightfields instead of cleanup, decimation, and LODs.
- **export** writes PNGs instead of FBX.
- **reimport** decodes those PNGs.
- **import_ue** builds a Landscape level through a small C++ editor library.

The heightfield math lives in one pure-Python module, so it is unit-testable outside Blender.

## Architecture

### Heightfield core (`plugins/nmg-game-dev-blender-addon/terrain_core/heightfield.py`, new, pure Python)

It has no `bpy` import and no relative imports. It is loadable by path, like `utils/budgets.py`.

- `VALID_SIZES = (127, 253, 505, 1009, 2017, 4033)`.
- `mobile_size(desktop, budget_px)`: halve `desktop` along `VALID_SIZES` (2017→1009→505…) until the size is ≤ `budget_px`. Returns `(size, stride)`.
- `encode_heights(heights, n) -> (bytes16, zmin, zmax)`.
  - `v = round((z - zmin) / (zmax - zmin) * 65535)`. A flat grid encodes 32768.
  - Row 0 is the Blender +Y edge and column 0 the Blender -X edge (Unreal +Y is Blender -Y).
- `decode_heights(bytes16, n, zmin, zmax)` is the inverse.
- `normalize_weights(layers)`: per vertex, divide by the sum. An all-zero vertex goes wholly to the layer with the highest total.
- `quantize_weights(normalized)`: 8-bit with largest-remainder rounding, so every pixel sums to exactly 255.
- `downsample(grid, n, stride)` takes every `stride`-th sample. `reduce_layers(weights, limit)` drops the lowest-total layers and renormalizes (AC3).
- `sample_points(heights, n, spacing)` returns 9 samples (corners, edge midpoints, center) plus the minimum and maximum vertex. Each is `[x_m, y_m, z_m]` in Blender space.
- `write_png_gray16` / `write_png_gray8` / `read_png_gray` form a minimal PNG codec (zlib, filter 0). It is used both in Blender and in CPython tests.

### Budgets (`utils/budgets.py`)

- `ASSET_CLASSES` gains `terrain`.
- `CONTRACT_BUDGETS["terrain"]` is `desktop {"heightmap_px": 2017, "layers": 4, "max_texture_px": 2048, "materials": 4}` and `mobile {"heightmap_px": 1009, "layers": 3, "max_texture_px": 1024, "materials": 3}`.
- `METRICS` gains `heightmap_px` and `layers`.
- `_checked_metrics` accepts `heightmap_px` and `layers` only for `terrain`, and `tris` only for other classes. A `heightmap_px` that is not in `VALID_SIZES` raises `variants.budget_override_invalid`.

`quality/mobile_budgets.py`:
- `AssetClass` and `ASSET_CLASSES` gain `terrain`.
- `DEFAULT_MOBILE_BUDGETS["terrain"] = {"heightmap_px": 1009, "layers": 3, "max_texture_px": 1024}`.
- `_AssetReport` validates the terrain fields for class `terrain` (instead of `tris` and `materials`).
- `ship.mobile_budget_exceeded` fires per terrain metric.

### Validator (`contract_core/terrain.py`, new; `contract_core/validate.py`)

`validate_asset(..., asset_class="terrain")` keeps `_unit_findings` and the structure and basis checks. It replaces `_mesh_findings` and `_budget_findings` with `terrain_findings(collection, budgets)`, which works on an evaluated copy and emits:

| Rule | When |
|------|------|
| `terrain.structure` | the collection holds anything other than the one mesh `SM_<Name>` |
| `terrain.resolution_invalid` | the vertex count is not n² for an n in `VALID_SIZES`, or the vertices are not one per grid point |
| `terrain.spacing` | adjacent unique X or Y coordinates differ from 1.0 m by more than 1 mm |
| `terrain.not_centered` | the X or Y extent is not symmetric about 0 within 1 mm |
| `terrain.layer_missing` | there is no `Layer_*` float POINT attribute |
| `terrain.layer_range` | a layer value is outside [0, 1] |
| `terrain.over_budget` | n > Desktop `heightmap_px`, or the layer count > Desktop `layers` |
| `terrain.layer_texture_missing` | `Layer_<L>` has no material `M_<Name>_<L>` on the mesh (always checked). After the bake (non-authored), the material also lacks `T_<Name>_<L>_{BC,N,ORM}` images |
| `texel.density` | a layer's texture density is < 256 px/m on Desktop, or < 128 px/m at its Mobile size. Same formula as `_texel_findings` |

- The report gains a `terrain` object: `{"desktop": {...}, "mobile": {...}}`. Each holds `heightmap_px`, `spacing_m`, `height_min_m`, `height_max_m`, `layers`, and `texel_density` (layer → px/m). The Mobile values are computed from the planned downsample.
- `build_report` gains an optional `extra` mapping that is merged into the report.
- Each rule gets a remediation entry in `contract_core/report.py` RULES.
- UV overlap is not checked (tiling).

### Bake (`bake_core/core.py`)

- Tiling mode applies when `asset_class in ("environment_piece", "terrain")`.
- For terrain, the material-limit check uses the Desktop `materials`. The Mobile layer reduction happens in variants.
- Part names come from `M_<Name>_<L>`, so the textures are `T_<Name>_<L>_*`.

### Variants and export (`terrain_core/variants.py`, new; `finalize_core/steps.py`)

- `_variants` with terrain calls `terrain_variants(collection, budgets)`.
  - It reads the evaluated grid into heights and layer weights and normalizes them.
  - It computes the Mobile size, stride, and layer set.
  - It saves `variants.blend` unchanged, because no `_Mobile` collection is created.
  - It returns the `metrics` for both variants (`heightmap_px`, `spacing_m`, `height_min_m`, `height_max_m`, `layers`, `max_texture_px`, `materials`) and the per-variant `samples`.
- `_export` with terrain runs the full validation as today. On a pass it calls `export_terrain(collection, category, export_root, metrics)`, which writes:
  - `T_<Name>_Height.png`;
  - the `T_<Name>_Layer_<L>.png` weightmaps;
  - the layer textures. Mobile copies go through `variants_core.textures.mobile_image_copy` and `write_png`.

  `_sidecar_payload` writes `"terrain": true` with the per-variant fields and samples. `write_sidecars` writes the terrain `Mobile/nmg-asset.json` shape. There is no `fbx` key.
- `_reimport` with terrain calls `terrain_reimport_check(variant_dir, pre_report)`. For each variant it decodes the PNGs and checks the resolution, the layer files, the per-pixel sum of 255, and every decoded height against the evaluated pre-export heights within 0.05 m. It returns a standard `reimport` report, whose findings use the rule `reimport.terrain`.
- `load_back` already skips a missing `<Name>_Mobile`, so no change is needed there.

### Pipeline host (`src/nmg_game_dev/pipeline/`)

- `request.AssetClass` gains `terrain`.
- `engine` routes `import_ue` for a terrain request to `import_terrain_variant` for each variant: Desktop first, then Mobile.

### Unreal import (`src/nmg_game_dev/unreal/terrain.py`, new)

- `landscape_transform(n, spacing_m, zmin_m, zmax_m) -> {"location": [x, y, z], "scale": [sx, sy, sz]}` in cm:
  - `sx = sy = spacing_m * 100`;
  - `x = y = -(n - 1) / 2 * sx`;
  - `sz = (zmax - zmin) * 100 * 128 / 65535` (1.0 when flat);
  - `z = zmin * 100 + 32768 * sz / 128` (`zmin * 100` when flat).
- `ue_samples(samples)` converts Blender `[x, y, z]` m to UE cm `[x*100, -y*100, z*100]`.
- `build_terrain_code(variant_dir, dest, name, sidecar_variant) -> str` produces UE Python that prints one `NMG_RESULT`. It does these steps:
  1. Import only the `T_<Name>_<L>_{BC,N,ORM}` PNGs, using the same texture settings as `_import_textures`.
  2. `NmgLandscapeLibrary.build_layered_material(dest, "M_<Name>_Landscape", layers, bc, n, orm, mapping_scale)`, where `mapping_scale = uv_tile_m / spacing_m`.
  3. `create_layer_info(dest, "LI_<Name>_<L>", L)` for each layer.
  4. Delete an existing `L_<Name>` (re-import replaces it). Then remember the open level, `LevelEditorSubsystem.new_level(level)`, and call `NmgLandscapeLibrary.import_landscape(world, heightmap, weightmaps, layer_infos, material, n, location, scale)`.
  5. Call `sample_heights(landscape, xy)` and compare it with the expected z within 5 cm. A mismatch sets the error `terrain_height_mismatch`.
  6. Save the level and reload the previous level in a `finally`.

  The result is `{"ok", "variant", "name", "dest", "level", "material", "layer_infos", "textures", "height_errors_cm", "error"}`.
- `import_terrain_variant(client, *, variant_dir, dest, name, sidecar_variant)` runs the code and parses it with `parse_nmg_result`. A height failure raises `import_ue.terrain_height_mismatch`, and any other failure raises `import_ue.failed`. Pivot checks do not apply.

### C++ editor library (`plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevEditor/{Public,Private}/NmgLandscapeLibrary.{h,cpp}`, new)

`UNmgLandscapeLibrary : UBlueprintFunctionLibrary` has these `UFUNCTION(BlueprintCallable)` statics:

- `BuildLayeredMaterial`: creates a `UMaterial` with three `UMaterialExpressionLandscapeLayerBlend` nodes (BC, N, ORM; `LB_WeightBlend`). Their texture samples use `UMaterialExpressionLandscapeLayerCoords` with `MappingScale`. ORM R/G/B wire to AO, Roughness, and Metallic. Saves the material.
- `CreateLayerInfo`: creates a `ULandscapeLayerInfoObject` with `LayerName`, and saves it.
- `ImportLandscape`:
  - reads the 16-bit and 8-bit PNGs with `IImageWrapper`;
  - spawns an `ALandscape` at the transform;
  - calls `ALandscape::Import` with 63-quad, single-section components (`(n - 1) / 63` per side) and one `FLandscapeImportLayerInfo` per layer;
  - assigns the material and returns the actor.
- `SampleHeights`: returns `GetHeightAtLocation` for each XY.

`NmgGameDevEditor.Build.cs` adds the private dependencies `Landscape`, `ImageWrapper`, `MaterialEditor`, `AssetTools`, and `UnrealEd`.

### Region scaffold (`src/nmg_game_dev/design/`)

- `parse._check_optional_fields`: a region's `terrain` must be a non-empty string (otherwise `design.invalid_field`).
- `_reference_errors`: it must name an `environment` entry whose `asset_class` is `terrain` (otherwise `design.unknown_reference`, field `terrain`).
- `model.ASSET_CLASSES` gains `terrain`.
- `scaffold._constants` for a region adds `TERRAIN_LEVEL = /Game/<Category>/<Terrain>/Desktop/L_<Terrain>`, or `None` when the field is absent.
  - When the field names no terrain entry in the backlog, `run_scaffold` records an error line with the code `design.unknown_reference` for that region and sets `failed`.
  - `ScaffoldLine` gains an optional `code`, defaulting to `design.scaffold_failed`.
- `_REGION_BODY`: when `TERRAIN_LEVEL` exists, it calls `unreal.EditorLevelUtils.add_level_to_world(world, TERRAIN_LEVEL, unreal.LevelStreamingAlwaysLoaded)` and spawns no plane. Otherwise it spawns the plane as today. `RESULT["terrain"]` holds the level path or `None`.

### Interfaces

| Interface | Change |
|-----------|--------|
| `finalize_asset` / `run_finalize_step` MCP and CLI `--class` | accept `terrain`. `tools.json` enum and help text updated |
| `nmg-variants.json` (terrain) | `{"terrain": true, "name", "category", "class": "terrain", "budget", "desktop"/"mobile": {"heightmap": "Desktop/T_<Name>_Height.png", "heightmap_px", "spacing_m", "height_min_m", "height_max_m", "uv_tile_m", "layers": [...], "max_texture_px", "texture_bytes", "samples": [[x,y,z], ...]}}` |
| `Mobile/nmg-asset.json` (terrain) | `{"class": "terrain", "heightmap_px", "layers", "max_texture_px"}` |
| `nmg-budgets.json` | `terrain` accepts `heightmap_px`, `layers`, and `max_texture_px` (top level = Mobile; `desktop` object = Desktop) |
| Design frontmatter | region `terrain: <environment entry name>` |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Thin C++ `UNmgLandscapeLibrary` called from generated UE Python | Selected | `ALandscape::Import` and landscape layer-blend materials need C++. The Python orchestration stays testable with the fake `unreal` module |
| Pure UE Python Landscape creation | Rejected | UE 5.8 Python has no dependable heightmap-import API |
| Resample the Mobile heightmap with filtering | Rejected | Valid sizes halve exactly, so stride sampling keeps the same extent and an exact round trip |
| Separate `terrain` finalize step chain | Rejected | Branching inside the existing six steps keeps caching, jobs, gates, and the MCP surface unchanged |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #154 | 2026-11-11 | Initial feature design |
