# Design: Reduce a generated high-poly asset to its Desktop budget and bake its look onto the reduced mesh

**Issue**: #139
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/67-bake-authored-materials-to-contract-compliant-uv-texture-sets/

## Overview

A new add-on core, `reduce_core`, builds reduced copies of each source part and works only on those copies:

1. Decimate each copy to its planned target.
2. Unwrap all copies into one atlas.
3. Bake each source part onto its copy with selected-to-active.
4. Measure the ray misses.
5. Pack the contract texture set.

Only when all of that succeeds does it commit. Committing moves the sources into `<Name>_High` and the copies into `<Name>`. A failure removes the datablocks it created, so the scene is unchanged.

The math (budget split, overrides, bake settings, coverage) lives in a pure-Python module, so CPython can test it. The host side adds a `reduce` job kind to the existing finalize job runner, plus a CLI command and an MCP tool.

## Architecture

### Plan module (`plugins/nmg-game-dev-blender-addon/reduce_core/plan.py`, pure Python)

It has no `bpy` import and no relative imports, so it loads by path like `utils/budgets.py`.

- `DEFAULTS`: `cage_extrusion` 0.03, `max_ray_distance` 0.10, `miss_threshold` 0.01, `smooth_angle_deg` 40, `min_part_tris` 12, `samples {"BC": 4, "R": 4, "M": 4, "N": 8, "AO": 48}`.
- `ReduceError(code, message, remediation, target="")` with `as_dict()`.
- `split_budget(parts: dict[str, PartStats], budget: int, overrides: dict[str, dict]) -> dict[str, int]`, where `PartStats` holds `area_m2` and `tris`.
  - It validates the overrides: `reduce.unknown_part`, `reduce.invalid_override`, `reduce.overrides_exceed_budget`.
  - An override part's target is `tris`, or `floor(share * budget)`.
  - The remainder is split by area: `floor(remaining * area / area_total)`, at least `min_part_tris`.
  - A part's target never exceeds its source triangles.
- `bake_settings(part_names, asset_wide, per_part) -> dict[str, {"cage_extrusion", "max_ray_distance"}]` resolves, in order: per part, then asset-wide, then `DEFAULTS`. Values must be > 0 (`reduce.invalid_override`).
- `unbaked_share(island_px, missed_px) -> float` returns 0.0 when `island_px` is 0.
- `check_misses(shares, threshold, settings)` raises `reduce.bake_misses` for the first part above the threshold. The message lists the part, its share, and its settings.

### Reduce core (`reduce_core/core.py`, `decimate.py`, `transfer.py`, `commit.py`)

`reduce_asset(collection, asset_class, budgets_path=None, *, device="GPU", cage_extrusion=None, max_ray_distance=None, parts=None, miss_threshold=None, out_dir=None, progress=None) -> dict`, in order:

1. **Guard** (no change on failure):
   - a missing collection is `reduce.collection_missing`;
   - an armature in `<Name>` or `<Name>_High` is `reduce.rigged`;
   - `asset_class == "terrain"` is `reduce.class_unsupported`;
   - a collection with no mesh is `reduce.no_mesh`.
2. **Sources.** When `<Name>_High` exists, the sources are its meshes, mapped back to their reduced names by the custom property `nmg_source_name`. Otherwise the sources are `<Name>`'s meshes. If the source total is at or below the budget and `<Name>_High` does not exist, return `{"state": "within_budget", ...}` unchanged.
3. **Plan.** Run `resolve_budget(asset_class, budgets_path, variant="desktop")`, then `split_budget` (world area from `bake_core.uv.world_area`), then `bake_settings`.
4. **Build copies** (`decimate.py`). For each source:
   - an evaluated copy (`variants_core.meshes.evaluated_mesh`) goes into a temporary collection `__nmg_reduce`, with the source's transform and its parent mapped to the copy;
   - it is fitted to its target with `variants_core.meshes.decimated_copy` and `clean_mesh`, repeated until it is at or below the target, else `reduce.unreachable_target`;
   - it is triangulated and shaded smooth by angle at 40°.
5. **Atlas.** `bake_core.uv.joint_unwrap(copies)` and then `finalize_unwrap`, giving one `UVMap` in 0–1 with no overlap.
6. **Bake** (`transfer.py`). This runs under `bake.select_device(device)`.
   - For each channel BC, roughness, metallic, N, and AO, and for each (source, copy) pair, it runs one selected-to-active `bpy.ops.object.bake` into a shared float image at the Desktop `max_texture_px`. Its settings are `use_selected_to_active=True`, `use_cage=False`, `cage_extrusion`, `max_ray_distance`, and `margin=bake_margin(size)`, with the image cleared on the first pass only.
   - BC, roughness, and metallic bake as `EMIT` through the existing channel copies in `bake_core/bake.py` (`_channel_copy` / `_emit_in_place`). N bakes tangent space and AO bakes `AO`, with per-channel samples from `DEFAULTS`.
   - The copy carries a temporary material with the active target image node.
   - The new helper `bake_core.bake.bake_transfer(source, copy, channel, target, size, cage_extrusion, max_ray_distance)` holds this shared logic.
7. **Coverage.** For each pair, bake a constant-white EMIT from the copy onto itself into a cleared black mask image with margin 0, which gives the island texels. Then bake a constant-white EMIT from the source to the copy (selected-to-active, same settings, margin 0) into a second cleared image, which gives the hit texels. Count the island texels that were not hit, using numpy in Blender, and call `unbaked_share`, then `check_misses`.
8. **Pack.**
   - `bake_core.pack.write_png` writes `T_<Name>_Body_{BC,N,ORM}` to `out_dir` (default `<blend dir>/Reduced/<Name>/`, or the job directory for a background job). ORM uses `orm_rgb`.
   - `bake_core.rewire.build_material("M_<Name>_Body", <Name>, "Body", paths)` builds the material, its images are packed (`image.pack()`), and it is assigned as each copy's only slot.
9. **Commit** (`commit.py`, only after every step above passed):
   - Create or reuse a top-level `<Name>_High` with `hide_viewport` and `hide_render` set.
   - On a first run, move each source into it, rename it `<obj>_High` (its mesh `<mesh>_High`), and set `nmg_source_name`.
   - On a rerun, delete the previous reduced objects in `<Name>` and their meshes, materials, and images.
   - Link the copies into `<Name>` with the source names, and set `<Name>["nmg_reduced"] = True`.
10. **Failure.** Any exception removes every datablock created since step 4: the temporary collection, copies, meshes, images, and materials. Datablocks are recorded with `bake_core.state._datablock_pointers` and `_remove_created`, which are made public. Sources are never edited before step 9, so the scene is unchanged.

Result: `{"state": "reduced"|"within_budget", "collection", "asset_class", "budget", "parts": {name: {"source_tris", "target", "final_tris", "cage_extrusion", "max_ray_distance", "unbaked_share"}}, "total_tris", "textures": {"BC", "N", "ORM"}, "texture_px", "device", "summary"}`.

`run_for_mcp(**kwargs)` returns the result, or `{"error": ReduceError.as_dict()}`.

### Finalize integration (existing modules)

- `bake_core/core.py`: `mode = "tiling"` only when `asset_class == "environment_piece"` and `not collection.get("nmg_reduced")`.
- `contract_core/validate.py`: a tagged `environment_piece` runs `uv_findings(..., check_overlap=True)`. The texel-density rule still applies.
- `finalize_core/load_back.py`: `load_back(result_blend, collection, expected_hash, suffixes=("", "_Mobile"))`. Targets are `<collection><suffix>` present in the result. A loaded `_High` collection keeps its hidden flags. `scripts/blender/finalize_session.py` passes `suffixes` through.
- `hashing.content_hash`, the validator, and export already read only `<Name>` and `<Name>_Mobile`. Because `<Name>_High` is a top-level sibling, no change is needed there. A regression test proves it.

### Background job (`finalize_core/reduce_job.py`, `scripts/blender/finalize_entry.py`, `src/nmg_game_dev/pipeline/`)

- `finalize_entry.py` accepts the command `reduce`. `reduce_job.run_reduce(request, job)` opens the checkpoint, calls `reduce_asset` with the request's options (`out_dir` = `<job>/reduce/`), saves `<job>/reduce.blend`, and writes the envelope `<job>/reduce.json` (`{"schemaVersion": 1, "step": "reduce", "ok", "outputs": {"result", "blend"}, "error"}`). Progress is printed as `NMG_PROGRESS` lines.
- `pipeline/reduce.py` (new):
  - `ReduceRequest` (pydantic, frozen): `collection`, `asset_class`, `blend`, `budgets_path`, `device`, `cage_extrusion`, `max_ray_distance`, `miss_threshold`, and `parts: dict[str, PartOptions]`. `PartOptions` holds `share`, `tris`, `cage_extrusion`, and `max_ray_distance`.
  - `execute_reduce(request, clients, runner, job_dir, emit)` does these steps:
    1. checkpoint, through the shared helper refactored from `engine._checkpoint`;
    2. `runner.run("reduce", ...)`;
    3. for a session run that reduced, `load_back(suffixes=("", "_High"))`;
    4. a refused load-back raises `reduce.session_changed` with the result `.blend`.
  - A `within_budget` result loads nothing.
- `pipeline/jobs.py`: `job.json` gains `kind` (`"finalize"` by default, or `"reduce"`). `start_reduce(request, ...)` reuses the lock, status, and launcher. `run_job` dispatches on `kind`. `status` and `wait` are unchanged, so `get_finalize_job` serves both kinds.

### Entry points

- **Panel:** `operators/reduce_to_budget.py` adds `NMGGAMEDEV_OT_reduce_to_budget` (`nmggamedev.reduce_to_budget`) with collection, asset class, cage, ray distance, and threshold properties. It is registered, and a button sits in `panels/main_panel.py`. It calls `reduce_asset` and reports `summary` or the error.
- **CLI:** `python -m nmg_game_dev.finalize reduce --collection N --class C [--blend F] [--budgets F] [--device GPU|CPU] [--cage M] [--ray M] [--miss-threshold X] [--parts JSON] [--wait S]`. It prints the job status JSON, and `ERROR [code]` with exit 1.
- **MCP:** `finalize_mcp.reduce_asset(collection, asset_class, blend?, budgets_path?, device?, cage_extrusion?, max_ray_distance?, miss_threshold?, parts?, wait_seconds=0)`, implemented in `src/nmg_game_dev/finalize/mcp_tools.py`. It is declared in `mcp-servers/finalize/tools.json` and registered in `mcp-servers/finalize/src/finalize_mcp/server.py`.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Work on copies and commit at the end | Selected | Failure leaves the scene unchanged without snapshotting every datablock field |
| Decimate the originals in place and snapshot them | Rejected | 1.4M-triangle snapshots are large and error-prone |
| Add reduce as a seventh finalize step | Rejected | Out of scope: reduction is not automatic inside `finalize_asset` |
| Measure misses from a numpy UV rasterization | Rejected | A self-bake island mask uses Blender's own rasterization, so it matches the bake exactly |
| Refuse `environment_piece` | Rejected (user) | Generated buildings need the step; the `nmg_reduced` tag keeps the atlas |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #139 | 2026-11-11 | Initial feature design |
