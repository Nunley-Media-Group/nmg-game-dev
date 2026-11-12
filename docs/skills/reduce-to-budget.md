# Reduce to budget

A generated model (Meshy or similar) arrives at 200,000 to 1,400,000 triangles. A Desktop variant
must sit within its class budget (`docs/asset-contract.md` §6, 2,000 to 60,000 triangles), so
`validate` fails it with `budget.tris`. The reduce step fixes that in one run. It decimates each
mesh part of the asset to a share of the Desktop budget, bakes the original's look onto the reduced
mesh, and keeps the originals in a hidden collection so a rerun can start again from them.

Reduce is a separate step. Finalize never runs it. Run reduce first, then finalize the result.

## Entry points

The same implementation runs from four places, and all four return the same result shape.

| Entry point | How to call it |
|-------------|----------------|
| Panel operator | `nmggamedev.reduce_to_budget` in the add-on panel. It takes the collection, asset class, cage, ray distance, and threshold. |
| Blender MCP | `reduce_core.run_for_mcp(**kwargs)` from `execute_blender_code`. It returns the result, or `{"error": {...}}`. |
| CLI | `python -m nmg_game_dev.finalize reduce --collection N --class C` with the options below. |
| Finalize MCP | `reduce_asset`, which starts a background job. Poll it with `get_finalize_job`. |

The CLI and the MCP tool run as a background Blender job against a checkpoint of the open session,
so they do not hit the 180 s Blender MCP timeout. The panel operator and `run_for_mcp` run in the
session directly.

## Inputs

| Input | Meaning | Default |
|-------|---------|---------|
| `collection` | The asset's collection `<Name>`, PascalCase. | required |
| `asset_class` | `small_prop`, `standard_prop`, `hero_prop`, `character`, or `environment_piece`. Sets the Desktop budget and texture size. | required |
| `blend` | Optional saved `.blend` to reduce instead of the open session. | the open session |
| `budgets_path` | Optional `nmg-budgets.json`. Its `desktop` overrides apply. | `nmg-budgets.json` in the project, else contract defaults |
| `device` | `GPU` or `CPU` for the bake. `GPU` falls back to `CPU` when no compute device exists. | `GPU` |
| `cage_extrusion` | Bake cage extrusion in metres, asset-wide. | 0.03 |
| `max_ray_distance` | Bake ray distance in metres, asset-wide. | 0.10 |
| `miss_threshold` | Largest unbaked share a part may have, from 0 to 1. | 0.01 |
| `parts` | Per-part overrides keyed by object name. Each entry takes `share`, `tris`, `cage_extrusion`, and `max_ray_distance`. | none |

Cage and ray values can be set per part. A part's own value wins, then the asset-wide value, then the
default. The CLI takes the same values as `--budgets`, `--device`, `--cage`, `--ray`,
`--miss-threshold`, and `--parts` (a JSON object such as `{"Wall": {"share": 0.4}}`), plus `--wait`
seconds to wait before it prints the job status. Without `--wait` it waits until the job finishes.

Via the MCP tool, `wait_seconds` is clamped to 0 to 150. A value of 0 returns the job id at once.

## What it does

1. **Guard.** It refuses a rigged asset (an armature in `<Name>` or `<Name>_High`) with
   `reduce.rigged`, and the `terrain` class with `reduce.class_unsupported`. A collection with no
   mesh fails with `reduce.no_mesh`. Nothing changes on a refusal.
2. **Sources.** On a first run the sources are `<Name>`'s meshes. When `<Name>_High` already exists,
   the sources are its meshes, so a rerun rebuilds from the originals. An asset already within
   budget with no `<Name>_High` returns `within_budget` and changes nothing.
3. **Plan.** The Desktop budget is split between the parts by world surface area. Each part gets at
   least 12 triangles and never more than it started with. Parts with an override take their own
   value, and the rest share what remains. Overrides are checked before anything changes.
4. **Build copies.** Each part is copied, decimated to its target, cleaned, and triangulated. It is
   shaded smooth by angle at 40 degrees. The originals are not touched yet.
5. **Atlas.** All the copies are unwrapped together into one `UVMap` in 0 to 1 with no overlap.
6. **Bake.** Base color, roughness, metallic, tangent-space normal, and ambient occlusion are baked
   from each original part onto its own reduced copy only. Procedural and attribute-driven materials,
   such as vertex color, are baked as well as image textures.
7. **Coverage.** For each part the step measures the unbaked share, the share of its island texels
   that no ray from the reduced copy hit on the original. A part above `miss_threshold` fails the
   step with `reduce.bake_misses`, and the scene is left as it was.
8. **Pack.** The texture set `T_<Name>_Body_{BC,N,ORM}` is written at the class's Desktop texture
   size and packed into the `.blend`. The material `M_<Name>_Body` uses that set, and every reduced
   face uses it.
9. **Commit.** Only after every step above passes does the step change the scene. The originals move
   into a top-level `<Name>_High` collection, hidden in the viewport and in renders, with each object
   renamed `<object>_High`. The reduced copies go into `<Name>`, and `<Name>` gets the custom property
   `nmg_reduced`. A rerun deletes the previous reduced objects and their textures, and rebuilds
   `<Name>` from `<Name>_High`. It never modifies or duplicates `<Name>_High`.

A failure at any step before commit removes the datablocks the step created, so the scene is
unchanged.

## The `<Name>_High` collection

`<Name>_High` holds the original meshes and their authored materials, unchanged. It sits outside
`<Name>`, so it is never validated, hashed, or written to the Desktop or Mobile export. Finalize
reads only `<Name>` and `<Name>_Mobile`. A session load-back keeps its hidden flags.

## The `nmg_reduced` tag

The reduced `<Name>` carries `nmg_reduced` as a custom property. The bake reads it. An
`environment_piece` normally bakes in tiling mode, which assumes its UVs are placed by hand. A reduced
environment piece bakes in unique mode instead, so the one atlas layout from reduce is kept. The
validator also checks a tagged environment piece for UV overlap, as it does for other classes.

## Result

Every entry point returns:

| Field | Meaning |
|-------|---------|
| `state` | `reduced` when the scene changed, or `within_budget` when nothing needed to change. |
| `collection`, `asset_class`, `budget` | The asset, its class, and the resolved Desktop triangle budget. |
| `parts` | Per part: `source_tris`, `target`, `final_tris`, `cage_extrusion`, `max_ray_distance`, `unbaked_share`. |
| `total_tris` | The reduced asset's triangle total. |
| `textures` | The paths of the `BC`, `N`, and `ORM` PNGs. |
| `texture_px`, `device` | The Desktop texture size and the bake device used. |
| `summary` | One line for the developer. |

The background job adds `kind: "reduce"`, `loaded_back` (true when the reduced asset replaced the
session's copies), and `result_blend`, the path of the reduced `.blend`.

## Errors

| Code | Meaning | Remediation |
|------|---------|-------------|
| `reduce.rigged` | The collection has an armature. Reduce before rigging. | Reduce the mesh first, then rig it. |
| `reduce.class_unsupported` | The class is `terrain`, or not one of the five contract classes. | Use the class that matches the asset. |
| `reduce.collection_missing` | No collection named `<Name>` is in the file. | Check the name, or open the file. |
| `reduce.no_mesh` | The collection holds no mesh. | Add the meshes, then rerun. |
| `reduce.overrides_exceed_budget` | The per-part overrides leave too few triangles for the other parts, or exceed the budget. | Lower the overrides, or raise the budget in `nmg-budgets.json`. |
| `reduce.unknown_part` | An override names a part that is not in the asset. | Use an object name from the collection. |
| `reduce.invalid_override` | A part has both `share` and `tris`, or a value is out of range. | Give each part one of `share` or `tris`, within its range. |
| `reduce.unreachable_target` | A part could not be decimated to its target in the allowed passes. | Simplify the mesh by hand, or raise the budget. |
| `reduce.bake_misses` | A part's unbaked share is above `miss_threshold`. The message names the part, its share, and the cage and ray values used. | Raise `max_ray_distance` or `cage_extrusion` for that part, or fix the geometry that blocks the rays. |
| `reduce.session_changed` | `<Name>` changed in the session after the checkpoint, so nothing was loaded back. | Open the result `.blend` named in the message. Revert the session changes and rerun, or keep the result. |
| `finalize.job_crashed` | The background Blender reduce process exited before writing its result. The stage is `reduce`. | Read `blender-reduce.log` in the job directory, fix the cause, and rerun. |
| `reduce.invalid_request` | A host argument is invalid, such as a non-PascalCase collection or a non-positive distance. Nothing starts. | Fix the argument named in the message, then rerun. |

## After reduce

Run `validate` on the reduced asset, or `finalize_asset` on it. A reduced asset passes the normal
finalize run with no reduce-specific arguments. Its finalize bake keeps the atlas layout, and the run
completes through `reimport`. Rerunning finalize on an unchanged reduced asset is served from cache.

Reduce does not run inside `finalize_asset`. If the Desktop budget is exceeded, `validate` still
reports `budget.tris`, and the fix is to run reduce first.

## Out of scope

- Reducing rigged or skinned meshes while keeping their skin weights.
- Manual or quad retopology. The reduced mesh comes from decimation.
- Transparency, emission, or any channel beyond base color, roughness, metallic, normal, and ambient
  occlusion.
- More than one atlas or material on the reduced asset.
- Changes to the Mobile variant and its LODs. Mobile still comes from the Desktop mesh at finalize.
- Changes to Meshy import or generation.
