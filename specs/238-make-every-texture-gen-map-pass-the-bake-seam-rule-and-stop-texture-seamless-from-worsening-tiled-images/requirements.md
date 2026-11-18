# Defect Report: Generated texture maps fail the bake seam rule and `texture seamless` worsens tiled images

**Issue**: #238
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Reproduction

1. Build a low-contrast, band-limited albedo: the uint8 image `0.5 + (periodic_crop(256, seed=5, cutoff=0.25) − 0.5) × 0.1` scaled to 0–255, and pass it through `make_seamless`, as `generate` does.
2. Run `maps.derive(albedo, 0.85, 0.0, ao=True)`.
3. Run `is_seamless` on each written map. The AO map fails (axis 1 wrap 0.0112 vs allowance 0.0105) although the albedo passes.
4. Run `python -m nmg_game_dev.texture seamless <png>` on an albedo that already passes. The command re-blends it instead of leaving it as it is.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | Every PNG texture-gen writes (albedo, N, R, M, AO) passes `nmg_game_dev.texture.seamless.is_seamless`. `texture seamless` leaves a passing image unchanged and repairs a failing one so it passes. It never makes a wrap measure worse. |
| **Actual** | Generated albedos and derived N/AO maps can fail `is_seamless`, and the bake rejects them with `not_seamless`. `texture seamless` always applies the half-roll cross-fade, so it can widen the wrap step of an image that already tiles. It also does not bring failing N/AO maps into compliance. |

## Acceptance Criteria

### AC1: Generated maps pass the seam rule

**Given** a texture-gen run with a fake worker that writes the low-contrast band-limited image from Reproduction step 1 (before `make_seamless`), the `stone` preset, and `ao: true`
**When** generation writes the albedo and its derived N, R, M and AO maps
**Then** every written PNG passes `nmg_game_dev.texture.seamless.is_seamless`

### AC2: Derived maps pass for any passing albedo

**Given** an albedo that passes `is_seamless`: either `make_seamless(synthetic_image(128))` or the low-contrast band-limited albedo from Reproduction step 1
**When** `maps.derive` writes N, R, M and AO
**Then** each derived map passes `is_seamless`

### AC3: `texture seamless` leaves a passing image unchanged

**Given** a PNG that already passes `is_seamless` (`make_seamless(synthetic_image(256))`)
**When** `python -m nmg_game_dev.texture seamless <png>` runs, in place or with `--out`
**Then** the written pixels equal the input pixels and the printed JSON reports `"seamless": true`

### AC4: `texture seamless` repairs failing maps without making them worse

**Given** a PNG that fails `is_seamless`. It is one of: a non-tiling albedo (`synthetic_image(256)`); a narrowly failing albedo (`make_seamless(synthetic_image(256))` with its last row raised by 8 levels); or a normal-map-like image (flat (128, 128, 255) with ±1 noise and its last row's R and G raised by 3 levels)
**When** `python -m nmg_game_dev.texture seamless <png>` runs
**Then** the written image passes `is_seamless`, keeps the input's shape and dtype, and on neither axis is its wrap measure larger than the input's

### AC5: Existing behaviour is preserved

**Given** the existing texture-gen, maps, seamless and `seamless` CLI tests. They cover output shape, dtype and mode, `--out`, the `{"path", "seamless"}` JSON, R/M constant values, normal unit-vector encoding, and the `is_seamless` / `seam_metric` parity
**When** the fix is in place
**Then** those tests pass without modification

### AC6: Docs tell consumers to reload or repack after fixing files on disk

**Given** the "Make a source texture seamless" section of `docs/onboarding/texture-models.md` and the `not_seamless` row of `docs/skills/bake-materials.md`
**When** a consumer reads them
**Then** both state that images packed into a `.blend` file keep their old pixels until they are reloaded or repacked from the fixed files

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | texture-gen checks each albedo with `is_seamless` after `make_seamless`. When it fails, it applies the edge-band repair before the albedo is written and its maps are derived. | Must |
| FR2 | `maps.derive` checks the N and AO maps it produces with `is_seamless`. When one fails, it applies the edge-band repair before writing. For N, the repair works on the float normal vectors and renormalizes each to unit length before encoding. | Must |
| FR3 | `nmg_game_dev.texture.seamless` provides an edge-band repair. Along an axis it cross-fades each line within `min(8, n // 2)` pixels of the edge (default 8) with its mirror line across the wrap. The weight is 0.5 at the wrap and falls linearly toward 0. The repair is applied to each failing axis, then rechecked, so any axis the first pass pushed over is repaired too. It keeps shape, dtype and mode. | Must |
| FR4 | `texture seamless` returns an image that already passes unchanged. If an image fails with both axes at wrap ≤ 3× allowance, it applies the edge-band repair. Otherwise it applies `make_seamless`, then the edge-band repair on any axis that still fails or whose wrap exceeds the input's. The written output always passes, and on neither axis is its wrap larger than the input's. The printed JSON keeps the `{"path", "seamless"}` shape. | Must |
| FR5 | Tests assert that every map texture-gen writes passes `is_seamless`, using the low-contrast band-limited fixture as well as `synthetic_image`. | Must |
| FR6 | `docs/onboarding/texture-models.md` and the `not_seamless` remediation in `docs/skills/bake-materials.md` say that textures packed into `.blend` files must be reloaded or repacked after the files on disk are fixed. | Should |

## Out of Scope

- Changing the seam rule (`SEAM_RATIO`, `SEAM_FLOOR`, `bake_core/seam_metric.py`) or the bake's tiling check.
- Reprocessing a consumer's existing generated textures automatically.
- Repacking images inside `.blend` files automatically.
- Changes to the texture generation models, prompts, or backends.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #238 | 2026-11-18 | Initial defect report |
