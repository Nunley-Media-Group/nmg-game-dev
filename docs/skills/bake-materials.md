# Bake materials

Bakes whatever materials the agent authored on an asset into the contract texture sets
(`docs/asset-contract.md` §4, §6, §8). Procedural nodes, triplanar or position-driven coordinates,
and image textures all bake the same way, so the exported asset looks the same in Unreal as it did
in Blender.

## Entry points

All three call one implementation, `bake_core.bake_asset`:

| Entry point | Use it when |
|-------------|-------------|
| Panel operator `nmggamedev.bake_materials` | You are working in the Blender UI and want a dialog. |
| `bake_core.bake_asset(...)` from `execute_blender_code` | The agent is authoring and reports the result itself. |
| Finalize `bake` step (`nmg_game_dev.pipeline.run_step("bake", request)`) | The finalize pipeline bakes the collection headless, as part of `finalize`. |

```python
from nmg_game_dev_blender_addon.bake_core import bake_asset

result = bake_asset("Crate", "standard_prop", "/path/to/out", device="GPU", samples=32)
print(result["summary"])
```

`run_for_mcp(**same)` returns the result, or `{"error": {...}}` instead of raising. The Blender
entry script (`scripts/blender/finalize_entry.py`) calls `bake_asset` and writes the result into the
finalize envelope. A refusal surfaces as `bake.texture.bake_failed` with stage `bake`.

## Inputs

| Input | Meaning |
|-------|---------|
| `collection` | The asset collection `<Name>` whose meshes carry the authored materials. |
| `asset_class` | One of `small_prop`, `standard_prop`, `hero_prop`, `character`, `environment_piece`. Sets the texture sizes and the material limit (§6). |
| `out_dir` | Folder that receives `Desktop/`, `Mobile/`, the proof renders, and `bake.json`. |
| `budgets_path` | Optional `nmg-budgets.json` with overrides (see below). |
| `device` | `GPU` or `CPU`. `GPU` is used only when Cycles reports a non-CPU device; otherwise `CPU`. |
| `samples` | Cycles samples per bake pass (default 32). |

The operator's fields are `collection_name`, `asset_class`, `out_dir` (a folder picker),
`budgets_path`, `device`, and `samples`.

## Modes

- **Unique bake** (every class except `environment_piece`). The layout is kept when every mesh has
  exactly one `UVMap` inside 0 to 1 and no faces overlap. Otherwise all meshes are unwrapped
  together with one Smart UV Project, into a new layer that becomes `UVMap`.
- **Merging.** When the authored material count is above the class's Mobile material limit, every
  material bakes into one atlas set `T_<Name>_Body_{BC,N,ORM}` on one non-overlapping layout, and
  every face uses `M_<Name>_Body`. An asset at or under the limit keeps one set per material.
- **Tiling** (`environment_piece`). Each tiling material bakes onto a temporary 1 m tile whose UVs
  span 0 to 1. The asset's UVs stay as they are. The bake fails unless the opposite edges of each
  texture match and each mesh meets the texel density minimum (256 px/m Desktop, 128 px/m Mobile).

Part names follow `M_<Name>_<Part>`: a material already named that way keeps `<Part>`, one authored
material otherwise becomes `Body`, and several materials take PascalCase of their names.

## Output

```
<out>/Desktop/T_<Name>_<Part>_{BC,N,ORM}.png    # 2048 px for standard_prop by default
<out>/Mobile/T_<Name>_<Part>_{BC,N,ORM}.png     # 1024 px, identical names
<out>/<Name>_prebake.png  <out>/<Name>_baked.png  <out>/<Name>_prebake.blend
<out>/bake.json
```

- BC is 8-bit sRGB. N is Non-Color with OpenGL green. ORM is Non-Color with R = AO,
  G = roughness, B = metallic.
- The authored materials are kept as `<name>_Authoring` with a fake user, so they can be
  reassigned. The asset's slots point at the rewired `M_<Name>_<Part>` materials.
- `bake.json` holds the result: `texture_bytes_desktop`, `texture_bytes_mobile`, per-variant texture
  paths, `proof`, `summary`, `source_hash`, and `baked_hash`.

The result's `summary` is one line, for example
`Baked 1 material for Crate (standard_prop): Desktop 2048 px, Mobile 1024 px, proof diff 0.012`.

## Budget overrides

`nmg-budgets.json` is keyed by asset class. Top-level metrics override the Mobile budget (the #33
format). A nested `desktop` object overrides the Desktop budget:

```json
{
  "standard_prop": {
    "max_texture_px": 1024,
    "desktop": { "max_texture_px": 4096 }
  }
}
```

`max_texture_px` must be a power of two. A class not in §6, or a size that is not a power of two,
fails with `budget_invalid`.

## Proof

The bake renders the asset's three-quarter view twice: before baking (`<Name>_prebake.png`) and
after rewiring (`<Name>_baked.png`). Both use the same camera and rig, a 512 px transparent film,
and the asset's alpha as the mask. The bake passes when, over the asset's pixels:

- the mean absolute RGB difference is at most **0.03**, and
- at most **2%** of pixels differ by more than **0.25** in any channel.

Otherwise it fails with `proof_mismatch`, and the file is restored to its authored state.

## Failure reasons

Every failure raises `texture.bake_failed` with a reason, a message naming the material or mesh, and
a remediation. A failed run restores the authored materials, UV maps, and render visibility.

| Reason | Cause | Remediation |
|--------|-------|-------------|
| `transparency` | Alpha below 1 or linked, or Transmission Weight above 0 or linked. | Set Alpha to 1 and Transmission Weight to 0, then rerun. |
| `emission` | Emission Strength above 0 with a non-black or linked Emission Color. | Set Emission Strength to 0 or Emission Color to black, then rerun. |
| `unsupported_shader` | A shader node other than Principled BSDF, Mix Shader, or Add Shader, or a node group that outputs a shader. | Replace the node with a Principled BSDF, Mix Shader, or Add Shader. |
| `volume_or_displacement` | The Volume or Displacement output is linked. | Unlink both outputs before baking. |
| `no_material` | A mesh has no material slots, or an empty slot. | Give every mesh a material in every slot. |
| `uv_unwrap_failed` | The mesh has no faces, or the unwrap yields no UV area. | Check that the mesh has faces with area. |
| `uv_missing` | A tiling mesh has no UV map. | Give every mesh at least one UV map. |
| `not_seamless` | A tiling material's opposite edges differ by more than 0.04. | Make the material periodic across 0 to 1 UV. |
| `texel_density` | A mesh is below 256 px/m (Desktop) or 128 px/m (Mobile). | Increase the UV scale or reduce the mesh area. |
| `material_limit` | A tiling asset has more materials than its Mobile limit. | Reduce the tiling materials to the class limit. |
| `proof_mismatch` | The baked render differs from the pre-bake render beyond tolerance. | Check the seams, color space, and roughness in the proof renders, fix the material, then rebake. |
| `budget_invalid` | Unknown class, or a texture size that is not a power of two. | Use a listed class and power-of-two sizes. |
| `collection_missing` | No collection with the given name. | Open the file that holds the asset. |
| `no_mesh` | The collection has no mesh objects. | Add mesh objects, then rerun. |

## Idempotency

The bake hashes the asset's meshes (geometry, UVs, material indices) and each material's node
tree, together with the class, the budgets, and the bake version. If the current hash equals the
`baked_hash` in `bake.json` and every recorded PNG exists, the bake returns the stored result with
`cache_hit: true` and writes nothing. Editing the asset or deleting a texture causes a rebake.

## Notes

- Other objects in the scene are hidden while the bake and its proof run, so set dressing and
  previews do not occlude the bake's ambient occlusion.
- The bake runs in the open Blender session. Long bakes in the background belong to #69.
- The Cycles device selection changes the add-on preferences for the session only.
