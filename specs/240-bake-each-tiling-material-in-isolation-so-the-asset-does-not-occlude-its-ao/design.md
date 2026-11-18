# Root Cause Analysis: Tiling bake lets the asset occlude the tile's ambient occlusion

**Issue**: #240
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Root Cause

`core._bake` calls `BakeState.make_render_enabled()` (`bake_core/state.py`) before any bake. It sets `hide_render = False` on every member of the asset collection and `True` on everything else, because unique mode and the proof render need the asset visible. In tiling mode, `_bake_tiling()` then builds a temporary 1 m plane with `tiling.make_tile()`. The plane lies in the XY plane at the world origin and is linked to the scene collection, and every channel in `bake.CHANNELS`, including Cycles `AO`, is baked onto it with `bake.bake_channel`. Under the contract pivot, the asset stands on the origin, directly over the tile. Its meshes are still render-visible, so the tile's AO rays hit them. The baked AO (ORM red channel) carries their contact shadow, and the opposite tile edges differ, so `tiling.check_seams` raises `not_seamless`. Shortening the world AO distance hides the symptom only because the rays stop before they reach the asset.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `plugins/nmg-game-dev-blender-addon/bake_core/core.py` | `_bake_tiling` | Bakes each tile while the asset is render-visible |
| `plugins/nmg-game-dev-blender-addon/bake_core/state.py` | `BakeState.make_render_enabled` | Leaves asset meshes render-visible for the whole bake |
| `plugins/nmg-game-dev-blender-addon/bake_core/tiling.py` | `make_tile`, `TILE_NAME` | Creates the tile at the origin in the scene collection |
| `plugins/nmg-game-dev-blender-addon/bake_core/cache.py` | `BAKE_VERSION` | Cache key; old tiling results would otherwise be reused |

## Fix Strategy

Isolate the tile inside `_bake_tiling` only. For each material, after `make_tile()` creates the tile:

1. Snapshot `{obj.name: obj.hide_render}` for every object in `bpy.context.scene.objects`.
2. Set `hide_render = True` on every object except the tile, and `False` on the tile.
3. Bake the channels.
4. In the existing `finally`, restore each snapshotted object's `hide_render` (skip names no longer in `bpy.data.objects`), then remove the tile object and mesh as today.

Add a context manager `tiling.isolated(tile)` that does steps 1, 2 and 4, so that the restore runs on success and on any raised error. `BakeState.release` still restores the original pre-bake flags at the end of the run, unchanged. The world, its AO distance, the active scene and the view layer are never touched. Bump `cache.BAKE_VERSION` to `"2"`.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `plugins/nmg-game-dev-blender-addon/bake_core/tiling.py` | Add `@contextmanager isolated(tile: bpy.types.Object) -> Iterator[None]`. It snapshots `hide_render` for `bpy.context.scene.objects`, hides all but `tile`, shows `tile`, yields, and restores the snapshot in `finally`. | FR1, FR2 |
| `plugins/nmg-game-dev-blender-addon/bake_core/core.py` | `_bake_tiling`: wrap the channel-image creation and the `bake.bake_channel` loop in `with tiling.isolated(tile):`. The existing `finally` that removes the tile stays outside it, so visibility is restored before the tile is removed. Update the docstring to "on its own 1 m tile, with every other object hidden from the bake". | FR1, FR2, AC1–AC3 |
| `plugins/nmg-game-dev-blender-addon/bake_core/cache.py` | `BAKE_VERSION = "2"`. | FR3 |
| `docs/skills/bake-materials.md` | In the **Tiling** bullet: each tiling material bakes alone on the tile, and every other object, the asset included, is hidden from the bake, so baked AO depends only on the material and not on the world AO distance. | FR5 |
| `CHANGELOG.md` | Under `## [Unreleased]` → `### Fixed`, add one bullet ending `(#240)`. | Release notes |

## Blast Radius

Only the tiling path changes. `_bake_unique`, `BakeState`, the proof render, rewire, and the seam and density checks are unchanged. `hide_render` is restored inside `_bake_tiling`, so the later proof render sees the same visibility as before. The cache bump rebakes every asset once, the unique-mode ones included, with the same unique output.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Toggle `hide_render` on all non-tile objects around the tiling bake | Selected | Uses the same render-visibility mechanism `BakeState` already relies on to keep other objects out of the bake. It is local, and restored in a `finally`. |
| Bake the tile in a temporary scene or view layer | Rejected | Changes the active scene or view layer that `bake_channel` and `select_only` operate in. Needs more restore state. |
| Move the tile far from the origin | Rejected | Depends on scene extent and the AO distance, so it isn't guaranteed. |
| Set the world AO distance during the bake | Rejected | Affects the material's own AO detail and still depends on scene geometry. |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #240 | 2026-11-18 | Initial defect design |
