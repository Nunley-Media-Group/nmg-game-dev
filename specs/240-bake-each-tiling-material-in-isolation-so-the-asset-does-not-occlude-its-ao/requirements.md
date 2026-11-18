# Defect Report: Tiling bake lets the asset occlude the tile's ambient occlusion

**Issue**: #240
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Reproduction

1. In an `environment_piece` collection (tiling mode), put a 1 m plane whose tiling material tiles (a periodic checker, UVs spanning 0 to 10). Add a box mesh in the same collection, using the same material, that stands on the plane over its +X edge (x from 0.3 to 0.5 m, height 0.5 m).
2. Bake the collection with `bake_asset(..., "environment_piece", ...)` at the scene's default world AO distance.
3. The bake fails with `not_seamless` on the ORM channel. The temporary bake tile at the origin lies under the box, so the baked AO is dark along the tile's +X edge and bright along its −X edge.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | Each tiling material is baked on a tile that no other object can occlude. The baked AO, and so ORM, depends only on the material. A material that tiles bakes a seamless ORM whatever geometry sits at the origin. |
| **Actual** | The asset's meshes stay render-visible above the tile during the tiling bake. The baked AO carries the asset's contact shadow, and the seam check rejects ORM for a material that tiles. |

## Acceptance Criteria

### AC1: Asset geometry does not occlude the tiling bake

**Given** the tiling collection from Reproduction step 1, whose box stands over the bake tile's position
**When** the tiling bake runs at the scene's default world AO distance
**Then** for every channel bake, the bake tile is the only object in the scene that is render-visible, the bake succeeds, and every baked Desktop and Mobile texture passes the seam check

### AC2: Tiling AO depends only on the material

**Given** the same tiling material baked once with the box present (the Reproduction collection) and once as the plane alone
**When** both tiling bakes complete
**Then** the red (AO) channels of the two baked Desktop `_ORM` textures differ by a mean absolute difference of at most 0.02

### AC3: Scene state is restored after the bake

**Given** a scene that holds the tiling collection, an extra object outside it with `hide_render = False`, a second extra object with `hide_render = True`, and a world whose `light_settings.distance` is 0.37
**When** the tiling bake succeeds, and separately when it fails with `not_seamless` (a non-periodic material)
**Then** every object's `hide_render` matches its pre-bake value, the world AO distance is still 0.37, the active scene and view layer are unchanged, and no object or mesh named `__nmg_bake_tile` remains in the file

### AC4: Related behaviour is preserved

**Given** the existing unique-mode bake tests, the tiling bake tests, the bake failure and cache tests under `tests/blender/`, and the tiling seam check scenarios (`tests/bdd/features/tiling_seam_check.feature`)
**When** the fix is in place
**Then** those tests pass without modification, and the seam rule and its thresholds are unchanged

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | While a tiling material's channels bake, every scene object other than the bake tile, including the asset's own meshes, has `hide_render = True`. This holds without relying on the world AO distance. | Must |
| FR2 | The tiling bake restores each object's `hide_render` to its value from just before the tiling bake, on success and on failure, so the proof render and rewire see the asset as before. The temporary tile is removed in both cases. | Must |
| FR3 | `bake_core/cache.py` `BAKE_VERSION` changes, so tiling bakes cached under the old behaviour are rebaked. | Must |
| FR4 | Blender headless tests bake the Reproduction collection and assert AC1–AC3. | Must |
| FR5 | The tiling bullet of `docs/skills/bake-materials.md` says that each tile bakes alone, with every other object including the asset hidden, so baked AO depends only on the material. | Should |

## Out of Scope

- Changing the seam rule (`SEAM_RATIO`, `SEAM_FLOOR`, `bake_core/seam_metric.py`) or the tiling seam check.
- Making generated source maps pass the seam rule (#238).
- Changing how unique mode bakes AO.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #240 | 2026-11-18 | Initial defect report |
