# Design: Blender cleanup, decimate, LOD, and variant operators

**Issue**: #33
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## Overview

All behavior lives in one core module inside the add-on, `plugins/nmg-game-dev-blender-addon/variants_core/`, and is exposed as plain functions. The three operators are thin wrappers that read operator properties, call the core, store the JSON result on `scene.nmg_game_dev.last_result`, and report. The agent and the finalize pipeline (#69) can call the same functions through `execute_blender_code` (`from nmg_game_dev_blender_addon.variants_core import generate_variants`).

## Architecture

```
generate_variants(collection, category, asset_class, export_root, budgets_path=None) -> dict
  ├─ resolve_budget(asset_class, budgets_path)            utils/budgets.py
  ├─ cleanup_desktop(collection) -> CleanupReport         variants_core/cleanup.py
  ├─ build_mobile(collection, budget) -> MobileReport     variants_core/mobile.py
  │    copy hierarchy → <Name>_Mobile, decimate LOD0/1/2, LodGroup empty,
  │    downscale textures (variants_core/textures.py)
  ├─ export_variants(collection, mobile, category, export_root) -> ExportReport
  │    variants_core/export.py (temporary rename so both exports use identical names)
  └─ write_sidecars(...) -> result dict                   variants_core/sidecars.py
```

Validation (`variants.asset_not_found`, `variants.unbaked_material`, `variants.mobile_material_limit`) runs before any file is written. Each core function raises `VariantError(code, message, remediation)`. Operators catch it, `self.report({"ERROR"}, f"{code}: {message} — {remediation}")`, and return `{"CANCELLED"}`.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `nmggamedev.cleanup_desktop` | `collection_name` | `FINISHED`; result JSON in `last_result` | FR2 |
| `nmggamedev.optimize_mobile` | `collection_name`, `asset_class`, `budgets_path` | `FINISHED` / `CANCELLED` | FR3, FR4; rebuilds `<Name>_Mobile` from scratch each run (an existing one is removed first) |
| `nmggamedev.generate_variants` | `collection_name`, `category`, `asset_class`, `export_root`, `budgets_path` | `FINISHED` / `CANCELLED` | cleanup → mobile → export → sidecars |
| `variants_core.generate_variants(...)` | as above | `dict` result | Same implementation the operator uses |

Operator properties: `collection_name: StringProperty`, `category: StringProperty` (PascalCase), `asset_class: EnumProperty` (`small_prop`, `standard_prop`, `hero_prop`, `character`, `environment_piece`; default `standard_prop`), `export_root: StringProperty(subtype="DIR_PATH")`, `budgets_path: StringProperty(subtype="FILE_PATH", default="")`. `NmgGameDevPipelineProps` gains `last_result: StringProperty`.

### Cleanup (Desktop)

For every mesh object in collection `<Name>`:

1. Apply all modifiers (`bpy.ops.object.convert(target="MESH")` per object).
2. Run bmesh steps: `remove_doubles(dist=1e-5)`, delete loose verts/edges, `dissolve_degenerate(dist=1e-6)`, `recalc_face_normals`.

No decimation and no image changes. The report returns triangle counts before and after.

### Mobile

1. Remove any existing `<Name>_Mobile` collection with its objects, meshes, materials, and images that carry the `_Mobile` suffix.
2. Copy the root hierarchy, with mesh data and materials copied, into `<Name>_Mobile`. Suffix copies with `_Mobile`.
3. LOD0: apply a Decimate (COLLAPSE) modifier with `ratio = min(1, budget_tris / tris)`. While triangles exceed the budget, reduce the ratio by a factor of 0.95 and re-apply to a fresh copy, for at most 20 iterations, then fail with `variants.budget_unreachable`. With identical input this is deterministic.
4. When the root has no child parts: create LOD1 and LOD2 from LOD0 at ratios 0.5 and 0.25. Parent LOD0–2 (`SM_<Name>_Mobile_LOD{n}`) under Empty `SM_<Name>_Mobile` with custom property `fbx_type = "LodGroup"`. With child parts, the root mesh stays `SM_<Name>_Mobile` and `lod_levels = 1`.
5. Textures (`textures.py`): every Mobile material must be a Principled BSDF fed only by Image Texture / Normal Map / Separate Color nodes, else `variants.unbaked_material`. The material count must be ≤ the budget's `materials`, else `variants.mobile_material_limit`; its remediation says to merge materials with the bake step (#67). For each image, copy it with the `_Mobile` suffix and `scale()` it to `min(size, max_texture_px)` on both axes.

### Export

FBX per contract §7: `use_selection=True` on the variant's objects; `object_types={"EMPTY","MESH","ARMATURE"}` (Mobile) or `{"MESH","ARMATURE"}` (Desktop); `use_mesh_modifiers=True`, `mesh_smooth_type="FACE"`, `apply_scale_options="FBX_SCALE_UNITS"`, `path_mode="STRIP"`, `embed_textures=False`.

Images are saved as PNG beside the FBX under their unsuffixed names. Before the Mobile export, Desktop objects, materials, and images are renamed to `__nmg_tmp_<name>`. Mobile names then drop the `_Mobile` suffix, with LOD children becoming `SM_<Name>_LOD{n}` and the group `SM_<Name>`. Everything is renamed back in a `finally` block.

## Data / Storage Changes

`utils/budgets.py` (pure Python, no `bpy`) defines `CONTRACT_BUDGETS[class] = {"desktop": {"tris", "max_texture_px", "materials"}, "mobile": {...}}`, matching contract §6. `resolve_budget(asset_class, budgets_path)` merges `nmg-budgets.json` mobile overrides (`{class: {metric: int}}`).

`<root>/<Category>/<Name>/nmg-variants.json`:

```json
{
  "name": "Crate", "category": "Props", "class": "standard_prop",
  "budget": {"tris": 3000, "max_texture_px": 1024, "materials": 1},
  "desktop": {"fbx": "Desktop/SM_Crate.fbx", "tris": 11904, "texture_bytes": 0, "max_texture_px": 2048, "materials": 1},
  "mobile": {"fbx": "Mobile/SM_Crate.fbx", "tris": 2990, "lod_tris": [2990, 1494, 746], "lod_levels": 3,
             "texture_bytes": 0, "max_texture_px": 1024, "materials": 1}
}
```

`texture_bytes` is the sum of the PNG sizes written for that variant. Paths are relative; keys are sorted for determinism. `Mobile/nmg-asset.json` = `{"class", "tris", "max_texture_px", "materials"}` from the Mobile section. The returned result dict adds absolute `desktop_path`, `mobile_path`, `poly_count_desktop`, `poly_count_mobile`, `texture_bytes_desktop`, and `texture_bytes_mobile`.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Downscale baked images for Mobile | Selected | Interview decision; keeps baking in #67 |
| Collapse decimate + 2 LODs in an FBX LodGroup | Selected | Interview decision; preserves UVs and baked textures, and UE imports the LOD group |
| Voxel remesh | Rejected | Destroys UVs and baked textures |
| Separate Mobile .blend for name isolation | Rejected | Temporary renames within one file are simpler and keep the session state intact |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #33 | 2026-10-29 | Initial feature design |
