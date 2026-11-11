# Tasks: Terrain asset class — Blender heightfields finalized into Unreal Landscapes

**Issue**: #154
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/67-bake-authored-materials-to-contract-compliant-uv-texture-sets/

## Implementation Tasks

### T001: Heightfield core

**File(s)**: `plugins/nmg-game-dev-blender-addon/terrain_core/__init__.py`, `plugins/nmg-game-dev-blender-addon/terrain_core/heightfield.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- Pure Python, loadable by path, with no `bpy` import.
- Provides `VALID_SIZES`, `mobile_size`, `encode_heights`/`decode_heights` (0 = min, 65535 = max, flat = 32768), `normalize_weights`, `quantize_weights` (per-pixel sum exactly 255), `downsample` by stride, `reduce_layers` (drops the lowest-total layer and renormalizes proportionally; an all-zero pixel goes to the highest-total remaining layer), `sample_points`, and a gray8/gray16 PNG reader and writer (AC2, AC3, FR4, FR5).

### T002: Terrain budgets and class registration

**File(s)**: `plugins/nmg-game-dev-blender-addon/utils/budgets.py`, `plugins/nmg-game-dev-blender-addon/operators/_common.py`, `src/nmg_game_dev/quality/mobile_budgets.py`, `src/nmg_game_dev/pipeline/request.py`, `src/nmg_game_dev/design/model.py`, `src/nmg_game_dev/finalize/__main__.py`, `src/nmg_game_dev/finalize/mcp_tools.py`, `mcp-servers/finalize/tools.json`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `terrain` is accepted in every listed class declaration (FR1).
- The contract budgets match FR2. Overrides accept `heightmap_px`, `layers`, and `max_texture_px` for `terrain` only, and reject a `heightmap_px` outside `VALID_SIZES` with `variants.budget_override_invalid` (FR2).
- The ship gate checks a terrain `Mobile/nmg-asset.json` against `heightmap_px` 1009, `layers` 3, and `max_texture_px` 1024, merged with overrides (AC2, FR2).
- `gate-mcp-schema` passes.

### T003: Terrain contract validation

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/terrain.py`, `plugins/nmg-game-dev-blender-addon/contract_core/validate.py`, `plugins/nmg-game-dev-blender-addon/contract_core/report.py`
**Type**: Create
**Depends**: T001, T002
**Acceptance**:
- `validate_asset(..., "terrain")` emits the design's `terrain.*` and `texel.density` findings, each with a remediation (AC6, FR3, FR8).
- A passing report carries the `terrain` object for both variants: resolution, spacing, height range, layers, and per-layer density (AC1).
- `authored=True` still checks the `M_<Name>_<L>` mapping. The texture-set part of `terrain.layer_texture_missing` applies only after the bake.

### T004: Terrain bake, variants, export, and re-import

**File(s)**: `plugins/nmg-game-dev-blender-addon/bake_core/core.py`, `plugins/nmg-game-dev-blender-addon/terrain_core/variants.py`, `plugins/nmg-game-dev-blender-addon/terrain_core/export.py`, `plugins/nmg-game-dev-blender-addon/terrain_core/reimport.py`, `plugins/nmg-game-dev-blender-addon/variants_core/sidecars.py`, `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py`
**Type**: Modify
**Depends**: T001, T003
**Acceptance**:
- The bake uses tiling mode for terrain, with the Desktop material limit, producing `T_<Name>_<L>_{BC,N,ORM}` (FR3).
- Variants and export write the Desktop and Mobile heightmaps, weightmaps, and layer textures, `nmg-variants.json` with `"terrain": true` and the per-variant fields, and the terrain `Mobile/nmg-asset.json` (AC2, AC3, FR4, FR5).
- A failing pre-export contract exports nothing (AC6).
- The terrain re-import check fails on a changed resolution, a missing layer file, a weight sum other than 255, or a height off by more than 0.05 m (FR10).

### T005: Terrain Unreal import code and host routing

**File(s)**: `src/nmg_game_dev/unreal/terrain.py`, `src/nmg_game_dev/unreal/__init__.py`, `src/nmg_game_dev/pipeline/engine.py`
**Type**: Create
**Depends**: T004
**Acceptance**:
- `landscape_transform` and `ue_samples` follow the design formulas. Encoding, then decoding, then the transform reproduces every grid height within 5 cm, including flat terrain and a 0–500 m range (AC4).
- `build_terrain_code` imports only the layer BC, N, and ORM textures, builds `M_<Name>_Landscape` and `LI_<Name>_<L>`, replaces `/Game/<Category>/<Name>/<Variant>/L_<Name>`, imports the Landscape at the derived transform, compares sampled heights within 5 cm, saves, and restores the previous level (AC4, FR6).
- `import_terrain_variant` raises `import_ue.terrain_height_mismatch` or `import_ue.failed`.
- The engine routes terrain `import_ue` to it for Desktop and then Mobile, and only after every earlier step passed (FR8).

### T006: `UNmgLandscapeLibrary` C++ editor helper

**File(s)**: `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevEditor/Public/NmgLandscapeLibrary.h`, `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevEditor/Private/NmgLandscapeLibrary.cpp`, `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevEditor/NmgGameDevEditor.Build.cs`
**Type**: Create
**Depends**: none
**Acceptance**:
- Declares the BlueprintCallable statics `BuildLayeredMaterial`, `CreateLayerInfo`, `ImportLandscape` (63-quad single-section components, one import layer per weightmap), and `SampleHeights`, as specified in the design (AC4, FR6).
- `gate-ue-compile` passes. It compiles with UBT and launches no editor.

### T007: Region terrain field and scaffold

**File(s)**: `src/nmg_game_dev/design/parse.py`, `src/nmg_game_dev/design/scaffold.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- A region's `terrain` is validated: a non-string or empty value is `design.invalid_field`, and a name that matches no `environment` entry with `asset_class` `terrain` is `design.unknown_reference`. `sync` reports both (AC6, FR7).
- Scaffold reports `design.unknown_reference` for such a region and continues with the others (AC6).
- The region UE code adds the Desktop terrain level as an always-loaded streaming sublevel, with no plane, when it exists. Otherwise it spawns the plane as today. `RESULT["terrain"]` reports which (AC5, FR7).

### T008: Documentation

**File(s)**: `docs/asset-contract.md`, `docs/design-contract.md`, `docs/mcp/finalize.md`, `docs/skills/model-asset.md`, `docs/skills/bake-materials.md`, `docs/skills/ship.md`, `skills/finalize-asset/SKILL.md`, `skills/model-asset/SKILL.md`
**Type**: Modify
**Depends**: T002, T004, T005, T007
**Acceptance**:
- `docs/asset-contract.md` gains a terrain section (the grid, `Layer_<L>` to `M_<Name>_<L>`, encoding, exported files, Landscape level) and a §6 terrain row (FR9).
- The other files list `terrain` among the classes. `docs/design-contract.md` documents the region `terrain` field (FR9).

### T009: Tests

**File(s)**: `tests/unit/test_terrain_heightfield.py`, `tests/unit/test_blender_budgets.py`, `tests/unit/quality/test_mobile_budgets.py`, `tests/unit/test_unreal_terrain.py`, `tests/unit/fake_unreal.py`, `tests/unit/test_finalize_mcp.py`, `tests/unit/pipeline/test_terrain_routing.py`, `tests/unit/design/test_parse.py`, `tests/unit/design/test_scaffold.py`, `tests/unit/test_ue_landscape_library.py`, `tests/blender/terrain_fixtures.py`, `tests/blender/test_terrain.py`, `tests/bdd/features/terrain.feature`, `tests/bdd/test_terrain_bdd.py`, `tests/e2e/test_terrain_e2e.py`
**Type**: Create
**Depends**: T001, T002, T003, T004, T005, T006, T007
**Acceptance**:
- Heightfield unit tests:
  - encode and decode round-trip;
  - a flat grid encodes 32768;
  - weight sums are exactly 255 on random weights;
  - 2017 → 1009 at stride 2 keeps the corner samples;
  - layer reduction drops the lowest-total layer, renormalizes, and handles an all-zero pixel;
  - the PNG codec round-trips gray8 and gray16 (AC2, AC3).
- Budget and ship-gate unit tests cover the terrain defaults, the override rules, and the terrain `nmg-asset.json` pass and fail cases (FR2).
- Headless Blender tests (`gate-blender-headless`) build grid fixtures in code:
  - a valid 127 grid with two layers and tiling materials passes, and the report holds the `terrain` object (AC1);
  - one fixture per AC6 rule fails with that rule;
  - finalize export of a passing fixture writes every AC2 file, with weight sums of 255 and the sidecar fields;
  - a 253 grid with 4 layers and a Mobile override of `heightmap_px` 127 and `layers` 3 yields a Mobile 127 heightmap at 2 m spacing with 3 layers, and the lowest-total layer dropped (AC3);
  - a failing contract exports nothing, and the terrain re-import catches a tampered PNG (FR10).
- UE unit tests run `build_terrain_code` output against the fake `unreal` module, with a fake `NmgLandscapeLibrary`:
  - the call order and arguments, including the transform and mapping scale;
  - the Height and Layer PNGs are never imported as textures;
  - an existing level is replaced;
  - the previous level is restored after a failure;
  - a 6 cm sample error yields `import_ue.terrain_height_mismatch`;
  - host round-trip math is within 5 cm (AC4).
- A routing test with the `UnrealPythonClient` test double shows a terrain request calls `import_terrain_variant` for Desktop and then Mobile, and no Unreal call happens when validate fails (AC4, AC6).
- Design tests cover `terrain` field validation and `design.unknown_reference` in sync and scaffold. The region code is run against the fake `unreal` module with and without an existing terrain level: streaming sublevel and no plane, or the plane (AC5, AC6).
- A source guard test asserts that `NmgLandscapeLibrary.h` declares the four BlueprintCallable functions and that `Build.cs` lists `Landscape` and `ImageWrapper` (FR6).
- The BDD feature `tests/bdd/features/terrain.feature` binds SCN001–SCN008 to these fakes and to the pure-Python core.
- `tests/e2e/test_terrain_e2e.py` drives the real editors. It is marked slow, runs only with `--runslow`, and is never a required gate.
- Evidence:
  - `uv run pytest tests/unit tests/bdd -q` (`repository.tests`);
  - `repository.lint`, `repository.format`, `repository.types`;
  - `gate-blender-headless`;
  - `gate-ue-compile`;
  - `gate-mcp-schema`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #154 | 2026-11-11 | Initial feature tasks |
