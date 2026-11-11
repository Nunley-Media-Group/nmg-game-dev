# Design: Material variants for finalized assets

**Issue**: #148
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Overview

A material variant is an alternate look of one baked material `M_<Name>_<Part>`: a replacement base-colour texture, `M_NmgORM` parameter values (`Tint`), or both. It shares the main set's normal and ORM maps. The author declares material variants in `<Name>.material-variants.json` beside the asset's `.blend`. Finalize reads the declaration on the host, passes its path to the Blender steps through `request.json`, and validates it with the contract. The export step writes the variant textures, and `import_ue` creates the variant material instances and tags them, so they can be listed and stale ones deleted. Mesh slots stay bound to the main instances.

## Architecture

Data flow:

1. **Host request** (`src/nmg_game_dev/pipeline/request.py`, `src/nmg_game_dev/finalize/service.py`)
   - `FinalizeRequest` gains `material_variants_path: Path | None`.
   - `build_request` takes an explicit path. Without one, when `blend` is set and `<blend.parent>/<collection>.material-variants.json` exists, it uses that file.
   - An explicit path that does not exist raises `finalize.material_variants_not_found`.
   - The absolute path goes into `request.json`.
2. **Cache keys** (`src/nmg_game_dev/pipeline/steps.py`)
   - `material_variants_fingerprint(path)` hashes the declaration bytes plus the bytes of every texture file it references (paths resolved relative to the declaration). A missing file hashes as absent.
   - `settings_hash` adds that fingerprint to the `validate` and `export` settings. `bake` and `variants` are unchanged.
   - `_STEP_VERSION` goes to `"4"`, so results cached before this feature miss.
3. **Validate** (`plugins/nmg-game-dev-blender-addon/contract_core/material_variants.py`, called from `validate.py`)
   - `validate_asset` gains the keyword `material_variants_path: str | None = None`.
   - It parses the declaration, adds `material_variant.*` findings, and adds a top-level report key `material_variants` with the parsed entries. Extra report keys are ignored by `quality/contract.py`.
   - A file that is not valid JSON, or is not the documented schema, raises `ContractError("material_variant.declaration_invalid", ...)`.
   - The `authored=True` filter does not remove `material_variant.*` findings.
4. **Export** (`plugins/nmg-game-dev-blender-addon/variants_core/material_variants.py`, called from `finalize_core/steps.py` `_export`)
   - Removes `T_<Name>_*_BC_*.png` files from both variant folders.
   - For each texture-based material variant, writes `Desktop/T_<Name>_<Part>_BC_<Variant>.png` (the declared file at the Desktop main base-colour size).
   - Writes `Mobile/T_<Name>_<Part>_BC_<Variant>.png`, scaled to the size of the Mobile `T_<Name>_<Part>_BC`, the same way `variants_core/textures.mobile_image_copy` scales.
   - The sidecar payload gains `material_variants`, but only when a declaration exists.
5. **UE import** (`src/nmg_game_dev/unreal/import_asset.py`, `src/nmg_game_dev/pipeline/engine.py`)
   - `_run_import` reads `material_variants[<variant>]` from the export sidecar and passes it to `import_variant(..., material_variants=...)`.
   - The UE template treats `_BC_<Variant>` stems as base colour (sRGB).
   - After `_bind_materials`, the template creates or reuses each variant MI, sets its textures and parameters, and tags the MI and its texture with metadata. It then deletes tagged assets in `dest` that are no longer declared.
6. **Listing** (`src/nmg_game_dev/unreal/material_variants.py`)
   - `list_material_variants(client, category, name)` runs UE Python that reads the metadata tags in `/Game/<Category>/<Name>/{Desktop,Mobile}`.
   - It is exposed as the finalize MCP tool `list_material_variants` and the CLI command `material-variants`.
7. **Master material** (`scripts/unreal/build_master_material.py`)
   - Adds the `Tint` vector parameter (default (1, 1, 1, 1)) and a Multiply node between `BaseColor` RGB and Base Color.
   - The builder is proven by running its UE code against an in-memory fake `unreal` module in a unit test. The fake records the expressions, parameter defaults, and connections. No live editor is used.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `<Name>.material-variants.json` | `{"schema": 1, "material_variants": [{"name": "Red", "material": "M_<Name>_<Part>", "base_color": "<path relative to this file>"}, {"name": "Blue", "material": "M_<Name>_<Part>", "parameters": {"Tint": [r, g, b] or [r, g, b, a]}}]}` | — | One entry per material variant; `base_color`, `parameters`, or both. `Tint` components are finite and ≥ 0, and alpha defaults to 1. |
| `FinalizeRequest.material_variants_path` / `build_request(..., material_variants_path=)` | `Path \| None` | `finalize.material_variants_not_found` | Explicit path, or discovery beside `blend` |
| CLI `python -m nmg_game_dev.finalize <step> --material-variants PATH` | path | as above | Passes the explicit path |
| MCP `finalize_asset` / `run_finalize_step` arg `material_variants_path` | optional string | as above | Passes the explicit path |
| `validate_asset(collection, asset_class, budgets_path=None, *, authored=False, material_variants_path=None)` | path | Report with `material_variants`; `material_variant.*` findings; `ContractError` `material_variant.declaration_invalid` | FR3 |
| `nmg-variants.json` `material_variants` | — | `{"desktop": [entry], "mobile": [entry]}`; entry = `{"name", "material", "base_color": "T_..._BC_<Variant>.png" \| null, "parameters": {...}, "material_instance": "MI_<Name>_<Part>_<Variant>"}` | Present only when declared |
| `import_variant(..., material_variants=None)` result | list of sidecar entries for this variant | Adds `"material_variants": {"<Variant>": {"material": "M_...", "instance": "/Game/.../MI_...", "texture": "/Game/.../T_..." \| null}}` and `"removed": [paths]` | FR5, FR7 |
| `list_material_variants(client, category, name)`; MCP `list_material_variants(category, collection)`; CLI `material-variants --category C --collection N [--json]` | category, name | `[{"name", "material", "desktop": path \| null, "mobile": path \| null}]`, sorted by material then name; `[]` when none or the folders are missing | FR8 |
| `M_NmgORM` | — | Vector parameter `Tint`, default (1, 1, 1, 1) | Base Color = `BaseColor`.RGB × `Tint`.RGB |

## Data / Storage Changes

Validation rules:

| Rule id | Fails when |
|---------|------------|
| `material_variant.name` | name not `^[A-Z][A-Za-z0-9]*$`, or `<Part>_<Variant>` equals another part name |
| `material_variant.duplicate` | two entries share a name on one material |
| `material_variant.material_missing` | material is not one of the asset's predicted post-bake `M_<Name>_<Part>` |
| `material_variant.material_merged` | material is an authored material that the bake merges into `M_<Name>_Body` |
| `material_variant.texture_missing` | `base_color` file is absent or not a PNG |
| `material_variant.texture_size` | not power-of-two square, or not the Desktop main base-colour size |
| `material_variant.parameter` | parameter not in `M_NmgORM`'s parameter table, or malformed value |
| `material_variant.empty` | no `base_color` and no `parameters` |

Rule details:

- Predicted parts come from `bake_core/rewire.part_names(sources, Name, merged)`, with `merged` computed exactly as the bake computes it: unique mode and more source materials than the Mobile material budget.
- The Desktop main base-colour size is the existing `T_<Name>_<Part>_BC` image on a baked asset, or otherwise the resolved Desktop `max_texture_px` the bake writes at.
- Texture sizes are read from the PNG IHDR.
- The parameter table `MASTER_PARAMETERS = {"Tint": "vector"}` lives in the pure-Python `plugins/nmg-game-dev-blender-addon/utils/master_material.py`. A unit test keeps it in sync with `build_master_material.py`.

Unreal metadata tags on each material-variant MI and texture:

- `nmg.asset` = `<Name>`
- `nmg.material_variant` = `<Variant>`
- `nmg.material_slot` = `M_<Name>_<Part>`

Stale deletion deletes only assets in `dest` whose `nmg.asset` tag matches and whose (`material_slot`, `material_variant`) pair is no longer declared.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| JSON file beside the `.blend` | Selected | Interview decision; readable and diffable outside Blender |
| Collection custom property in the `.blend` | Rejected | Interview decision |
| Whole-base-colour multiply `Tint` | Selected | Interview decision; partial recolours use a replacement base-colour texture |
| Delete stale tagged assets | Selected | Interview decision; tags limit deletion to assets finalize created |
| Derive variant and slot from asset names when listing | Rejected | Part names may contain underscores; metadata tags are unambiguous |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #148 | 2026-11-11 | Initial feature design |
