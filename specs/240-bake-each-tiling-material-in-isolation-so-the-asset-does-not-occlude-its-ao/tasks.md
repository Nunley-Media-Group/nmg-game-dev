# Tasks: Tiling bake lets the asset occlude the tile's ambient occlusion

**Issue**: #240
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Bake each tiling material on an isolated tile

**File(s)**: `plugins/nmg-game-dev-blender-addon/bake_core/tiling.py`, `plugins/nmg-game-dev-blender-addon/bake_core/core.py`, `plugins/nmg-game-dev-blender-addon/bake_core/cache.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- FR1: `tiling.isolated(tile)` exists as described in design.md. Inside it, the tile is the only object in `bpy.context.scene.objects` with `hide_render = False`.
- FR1, FR2: `_bake_tiling` runs every `bake.bake_channel` call inside `tiling.isolated(tile)`. It restores every object's `hide_render` to its value before isolation, on success and on a raised error, and removes the tile and its mesh afterwards.
- FR3: `cache.BAKE_VERSION == "2"`.
- The world, its `light_settings.distance`, the active scene and the view layer are not modified.

### T002: Document tile isolation

**File(s)**: `docs/skills/bake-materials.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- FR5: the **Tiling** bullet says each tiling material bakes alone on the tile, with every other object (the asset included) hidden, so baked AO depends only on the material.
- `CHANGELOG.md` `[Unreleased]` has a `### Fixed` bullet for this change ending with `(#240)`.

### T003: Add Blender headless regression tests

**File(s)**: `tests/blender/bake_fixtures.py`, `tests/blender/test_bake_tiling.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `bake_fixtures.py` gains `add_tiling_occluder(collection, material, uv_density=10.0)`. It adds a box mesh `SM_<collection>_Occluder` with x from 0.3 to 0.5, y from −0.5 to 0.5 and z from 0 to 0.5, using `material`, with a `UVMap` that projects each face's world coordinates × `uv_density`. It links the box into `collection`. Existing fixtures are unchanged.
- SCN001 (AC1): `test_scn001_occluder_does_not_shade_the_tiling_bake` builds `build_tiling_plane("Road", periodic checker material)` plus `add_tiling_occluder`. It wraps the core module's `bake.bake_channel` so each call records the names of render-visible scene objects, then calls the original. It asserts every record is exactly `[tiling.TILE_NAME]`, that `bake_asset(..., "environment_piece", ..., "CPU", 4)` returns `mode == "tiling"`, and that every Desktop and Mobile texture passes `seam_metric.passes`. Without the T001 fix this test fails with `not_seamless`.
- SCN002 (AC2): `test_scn002_tiling_ao_matches_an_isolated_bake` bakes the plane alone, then (after `clear_scene`) the plane plus occluder, each into its own output folder. It loads both Desktop textures whose names end with `_ORM.png` and asserts that the mean absolute difference of their red channels is ≤ 0.02.
- SCN003 (AC3): `test_scn003_tiling_bake_restores_scene_state` adds a world with `light_settings.distance = 0.37` and two objects outside the collection (one `hide_render=False`, one `True`), then records every object's `hide_render`, `bpy.context.scene` and `bpy.context.view_layer`. It is parametrized over a successful bake (periodic material) and a failing one (`checker_image(..., periodic=False)` raising `BakeError` with reason `not_seamless`). After each bake it asserts the flags, the AO distance, the scene and the view layer are unchanged, and that `__nmg_bake_tile` is in neither `bpy.data.objects` nor `bpy.data.meshes`.
- SCN004 (AC4): no existing test function under `tests/blender/` or `tests/bdd/` is modified or removed.
- Evidence: the `gate-blender-headless` validation (`scripts/run-blender-tests.sh`), `repository.tests`, `repository.lint`, `repository.format` and `repository.types` pass.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #240 | 2026-11-18 | Initial defect tasks |
