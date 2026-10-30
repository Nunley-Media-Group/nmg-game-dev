# Design: Bake authored materials to contract-compliant UV texture sets

**Issue**: #67
**Date**: 2026-10-30
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/30-add-contract-validation-re-import-check-and-review-renders/

## Overview

All bake logic lives in a new add-on package, `plugins/nmg-game-dev-blender-addon/bake_core/`, next to `contract_core/` (#30) and `variants_core/` (#33), and is exposed as plain functions. A thin operator, `nmggamedev.bake_materials`, wraps it. The agent calls the same function through the Blender MCP's `execute_blender_code` (`from nmg_game_dev_blender_addon.bake_core import bake_asset`). The pipeline `texture` stage sends a script through `ctx.mcp_clients.blender.run_script` that calls `bake_core.run_for_mcp`, which returns the result dict or a structured error.

## Architecture

```
bake_asset(collection, asset_class, out_dir, budgets_path=None, device="GPU", samples=32) -> dict
  ├─ resolve_budget(asset_class, budgets_path)                  utils/budgets.py
  ├─ hash_asset(collection, settings) → cache check             bake_core/cache.py
  ├─ inspect_materials(objects) → BakeError on unsupported      bake_core/inspect.py
  ├─ checkpoint: save copy <out>/<Name>_prebake.blend
  ├─ make_render_enabled(collection) (restored in finally)      bake_core/state.py
  ├─ render pre-bake three-quarter → <out>/<Name>_prebake.png   bake_core/proof.py
  ├─ unique:  ensure_uvmap (keep or joint smart-unwrap)         bake_core/uv.py
  │           plan sets: per material, or merged Body atlas
  │  tiling:  keep UVs; bake each material on a 1×1 UV plane    bake_core/tiling.py
  ├─ bake channels (Cycles) → pack BC / N / ORM → Desktop PNGs  bake_core/bake.py, bake_core/pack.py
  ├─ downscale to Mobile size → Mobile PNGs                     bake_core/pack.py
  ├─ rewire materials M_<Name>_<Part>                           bake_core/rewire.py
  ├─ render post-bake → <out>/<Name>_baked.png; compare         bake_core/proof.py
  └─ write <out>/bake.json; return result
On any BakeError or exception after mutation starts: restore originals (state.py) and re-raise.
```

`BakeError(code="texture.bake_failed", message, remediation, target, reason)` is the single error type. `run_for_mcp(**kwargs)` returns `bake_asset(...)` or `{"error": {"code", "message", "remediation", "target", "reason"}}`.

### Modules

| Path | Contents |
|------|----------|
| `bake_core/__init__.py` | Re-exports `bake_asset`, `run_for_mcp`, `BakeError` |
| `bake_core/errors.py` | `BakeError`; `REASONS` (reason → default remediation) |
| `bake_core/inspect.py` | Walks each material's tree from Material Output; rejects unsupported content (AC6 reasons) |
| `bake_core/state.py` | Snapshot/restore of material slots, UV layers, `hide_render`, view-layer collection `exclude`; removes images/materials/temp objects created by a failed run |
| `bake_core/uv.py` | UV validity and overlap (512×512 rasterization; overlap when > 0.5% of covered cells are hit by two or more faces, the #30 rule), joint Smart UV Project, texel density |
| `bake_core/bake.py` | Cycles bake of each channel into float buffers; device selection with CPU fallback |
| `bake_core/pack.py` | ORM packing with NumPy, PNG writes, Mobile downscale, byte totals |
| `bake_core/tiling.py` | Temporary UV plane bake and the edge seam check |
| `bake_core/rewire.py` | Builds export-ready materials, renames originals, part naming |
| `bake_core/proof.py` | Temporary scene `__nmg_bake_proof`, render, and image comparison |
| `bake_core/cache.py` | Content hash and `bake.json` read/write |
| `bake_core/core.py` | `bake_asset` / `run_for_mcp` orchestration |
| `utils/budgets.py` | `CONTRACT_BUDGETS` and `resolve_budget` (shared with #30/#33; created here if not present) |
| `operators/bake_materials.py` | `NMGGAMEDEV_OT_bake_materials` |
| `src/nmg_game_dev/pipeline/stages/texture.py` | Pipeline stage calling `run_for_mcp` |

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `bake_core.bake_asset(collection, asset_class, out_dir, budgets_path=None, device="GPU", samples=32)` | collection name, class id (`small_prop`, `standard_prop`, `hero_prop`, `character`, `environment_piece`), output folder | result dict / `BakeError` | AC1–AC4, AC6, AC7 |
| `bake_core.run_for_mcp(**same)` | as above | result dict or `{"error": {...}}` | AC5 |
| `nmggamedev.bake_materials` | `collection_name`, `asset_class` (enum, default `standard_prop`), `out_dir` (DIR_PATH, required), `budgets_path` (FILE_PATH, default ""), `device` (`GPU`/`CPU`), `samples` (int, default 32) | `FINISHED`, with result JSON in `scene.nmg_game_dev.last_result` / `CANCELLED`, with `self.report({"ERROR"}, "texture.bake_failed: <message> — <remediation>")` | AC5, AC6 |
| `nmg_game_dev.pipeline.stages.texture.texture(ctx)` | `StageContext` | `StageArtifact(stage="texture", blob_path=<out>/bake.json, sidecar=...)` / `PipelineError` | AC5, AC6, FR1 |

`NmgGameDevPipelineProps` gains `last_result: StringProperty` if #33 hasn't already added it.

### Pipeline stage

- Collection `ctx.prompt.name`; class `standard_prop` for tier `standard` and `hero_prop` for tier `hero`.
- `out_dir = ctx.cache_dir / "work" / "texture" / <Category> / <Name>`.
- `budgets_path` is `<CLAUDE_PROJECT_DIR or cwd>/nmg-budgets.json` when that file exists, else `None`.
- Script: `from nmg_game_dev_blender_addon.bake_core import run_for_mcp\nresult = run_for_mcp(collection=..., asset_class=..., out_dir=..., budgets_path=...)`, sent inside `translate_mcp_errors(server="blender", stage="texture")`.
- A result with `error` raises `PipelineError(code=error["code"], message=error["message"], remediation=error["remediation"], stage="texture")`. A missing `manifest_path` raises `mcp.blender.invalid_response` via `require_str_field`.
- Sidecar: `upstream_stage`, `name`, `category`, `class`, `mode`, `cache_hit`, `desktop_dir`, `mobile_dir`, `desktop_textures`, `mobile_textures`, `texture_bytes_desktop`, `texture_bytes_mobile`, `materials`, `proof`, `summary`.

### Material inspection (AC6 reasons)

Walk from the active Material Output's Surface input:

- `unsupported_shader`: any shader-socket node other than Principled BSDF, Mix Shader, or Add Shader (including node groups that output a shader)
- `transparency`: Principled Alpha linked or < 1.0, or Transmission Weight linked or > 0
- `emission`: Emission Strength linked, or > 0 with Emission Color linked or non-black
- `volume_or_displacement`: Material Output Volume or Displacement linked
- `no_material`: a mesh with no material slots or an empty slot

Texture and vector nodes of any kind (procedural, Geometry/Position, Object/Generated, Box projection) are allowed upstream. That is what the bake removes.

### UVs (unique-bake)

Overlap is checked per texture set: faces using the same material across all meshes are rasterized together, or all faces at once when merging. The layout is kept when every mesh has exactly one UV map named `UVMap` and no set overlaps. Otherwise every mesh gets a new UV layer, made active (not active-render, so authoring coordinates still evaluate), filled by one Smart UV Project across all meshes in multi-object edit mode (angle 66°, island margin 0.01). After baking, the other UV layers are removed and the new one is renamed `UVMap`. A mesh with no faces, or one whose unwrap yields zero UV area, fails with `uv_unwrap_failed`.

### Baking

- Each mesh gets one Image Texture target node per set, active and selected; the target image is a float buffer at the Desktop size. Cycles runs with `samples`, `margin = max(4, size // 128)`, and `device` GPU (Metal) when available, otherwise CPU. `result["device"]` records the device used.
- BC, roughness, metallic: a temporary copy of each material where every Principled BSDF becomes an Emission shader fed by that Principled's Base Color / Roughness / Metallic input (link or value), with Mix/Add Shader structure preserved; bake type `EMIT`.
- N: bake type `NORMAL`, `normal_space="TANGENT"`, swizzle `POS_X, POS_Y, POS_Z` (OpenGL), on the original materials.
- AO: bake type `AO`.
- Packing: BC saved as 8-bit sRGB PNG; N as Non-Color PNG; ORM = (AO, roughness, metallic) as Non-Color PNG. Mobile copies are scaled to the Mobile size (`Image.scale`) and saved under the same file names.

### Part naming

When a material is named `M_<Name>_<Part>`, `<Part>` is kept. A single material otherwise becomes `Body`. Multiple materials take PascalCase of the alphanumeric words of their names, with `2`, `3`, … appended on collision. A merged atlas is always `Body`. Originals are renamed `<original>_Authoring` with `use_fake_user = True` so they can be reassigned.

### Rewire

New material `M_<Name>_<Part>` (Principled BSDF → Material Output). Image Texture BC (sRGB) → Base Color. Image Texture ORM (Non-Color) → Separate Color (RGB): G → Roughness, B → Metallic. Image Texture N (Non-Color) → Normal Map (tangent, `uv_map="UVMap"`) → Normal. No UV Map or Mapping nodes; image vectors are unlinked and so sample the only UV map. Images reference the Desktop PNGs. Merging assigns the single material to every face.

### Tiling mode (`environment_piece`)

- UVs: every mesh must have at least one UV map, else `uv_missing`. The active-render map is kept, renamed `UVMap`, and the others are removed after baking.
- Each material is baked onto a temporary 1 m plane with UVs spanning 0–1 at the class's per-texture Desktop size, so the image is one UV period. Seam check: mean absolute difference between the first and last pixel column, and between the first and last row, ≤ 0.04 for BC, N, and ORM, else `not_seamless`.
- Texel density per mesh: `size * sqrt(uv_area / world_area)` ≥ 256 (Desktop) and ≥ 128 (Mobile), else `texel_density` (message includes the measured value).
- Material count above the Mobile limit fails with `material_limit` (tiling materials are not merged).

### Proof

Temporary scene `__nmg_bake_proof` that links the collection: a 50 mm camera at 20° elevation from the −Y+X 45° three-quarter azimuth, framing the bounding sphere with 10% margin; three suns; a gray world; EEVEE; 512×512; transparent film. The scene is deleted afterward. Comparison over asset pixels (alpha > 0.5 in either render): `mean_abs_diff` ≤ 0.03 and `outlier_ratio` (pixels with max channel diff > 0.25) ≤ 0.02, else `proof_mismatch` with both values and both PNG paths. `result["proof"] = {"pre_bake", "baked", "mean_abs_diff", "outlier_ratio"}`.

## Data / Storage Changes

Output layout:

```
<out>/Desktop/T_<Name>_<Part>_{BC,N,ORM}.png
<out>/Mobile/T_<Name>_<Part>_{BC,N,ORM}.png
<out>/<Name>_prebake.png  <out>/<Name>_baked.png  <out>/<Name>_prebake.blend
<out>/bake.json
```

`utils/budgets.py` (pure Python): `CONTRACT_BUDGETS[class] = {"desktop": {"tris", "max_texture_px", "materials"}, "mobile": {...}}` per contract §6. `resolve_budget(asset_class, budgets_path)` returns `{"desktop": {...}, "mobile": {...}}`. Override file `nmg-budgets.json`: `{class: {metric: int, ..., "desktop": {metric: int}}}`. Top-level metrics override Mobile (the #33 format); the optional `desktop` object overrides Desktop. An unknown class or a non-power-of-two `max_texture_px` fails with `texture.bake_failed`, reason `budget_invalid`.

`bake.json` (sorted keys) and the returned result:

```json
{"asset": "Crate", "class": "standard_prop", "mode": "unique", "merged": false,
 "cache_hit": false, "device": "GPU", "manifest_path": "<out>/bake.json",
 "source_hash": "…", "baked_hash": "…",
 "desktop_dir": "<out>/Desktop", "mobile_dir": "<out>/Mobile",
 "desktop_px": 2048, "mobile_px": 1024,
 "materials": [{"name": "M_Crate_Body", "source": ["Wood"],
   "desktop": {"BC": "…/Desktop/T_Crate_Body_BC.png", "N": "…", "ORM": "…"},
   "mobile": {"BC": "…/Mobile/T_Crate_Body_BC.png", "N": "…", "ORM": "…"}}],
 "desktop_textures": ["…"], "mobile_textures": ["…"],
 "texture_bytes_desktop": 0, "texture_bytes_mobile": 0,
 "proof": {"pre_bake": "…", "baked": "…", "mean_abs_diff": 0.0, "outlier_ratio": 0.0},
 "summary": "Baked 1 material for Crate (standard_prop): Desktop 2048 px, Mobile 1024 px, proof diff 0.012"}
```

`texture_bytes_*` is the sum of the PNG file sizes in that variant's folder.

Content hash (`cache.py`): SHA-256 over, for each mesh object in the collection sorted by name, `matrix_world`, vertex coordinates, polygon vertex indices, material indices, and every UV layer's data, plus each slot's material node tree in canonical form (node `bl_idname`, name, unlinked input default values, node properties including image file bytes hash and projection/interpolation, and links), plus `asset_class`, the resolved budget, mode, and `BAKE_VERSION`. `source_hash` is taken before baking and `baked_hash` after rewiring. A run whose current hash equals the recorded `baked_hash`, with every recorded PNG present, returns the stored result with `cache_hit: true` and writes nothing.

## State and UI Behavior

- Before baking, the bake sets `hide_render = False` on the collection's objects and clears the collection's view-layer `exclude`. It restores both afterward, on success and on failure.
- Mutations happen only after inspection passes. On failure, `state.restore()` reassigns the original materials and names, removes created UV layers, images, materials, the proof scene, and the tiling plane, and leaves the original UV layers untouched.
- The panel lists `nmggamedev.bake_materials`.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Emission-substitution bakes for BC / roughness / metallic | Selected | Works through Mix/Add Shader trees and any coordinates; DIFFUSE color passes miss metallic |
| Bake Mobile separately at Mobile size | Rejected | Downscaling the Desktop bake is deterministic, halves bake time, and matches #33's approach |
| Merge into one atlas only above the Mobile material limit | Selected | Interview decision; keeps per-material Desktop detail when the limit allows and lets #33's Mobile step pass |
| Rewire materials in place | Rejected | Keeping `_Authoring` originals preserves the authored look for re-authoring |
| Run the bake as a background Blender job | Rejected here | Background execution of long steps belongs to #69 |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #67 | 2026-10-30 | Initial feature design |
