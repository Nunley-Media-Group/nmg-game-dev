# Defect Report: Tiling seam check rejects high-frequency textures that tile correctly

**Issue**: #147
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/67-bake-authored-materials-to-contract-compliant-uv-texture-sets/

## Reproduction

1. Build an exactly periodic fine-noise image (or generate a high-frequency albedo such as grass or gravel with texture-gen, which applies `make_seamless`).
2. In Blender, author an `environment_piece` collection whose tiling material samples that image through `UVMap`.
3. Run the bake (or finalize) on the collection.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | A texture whose wrap is no more discontinuous than its own interior passes the seam check; a texture with a real discontinuity at the wrap fails it. |
| **Actual** | The bake fails with `not_seamless` ("Tiling material '<name>' is not seamless (BC 0.049; tolerance 0.04).") because the check compares the absolute first/last row and column difference with 0.04, which a busy texture exceeds everywhere. A smooth texture with a visible wrap step below 0.04 passes. |

## Acceptance Criteria

### AC1: An exactly tileable busy texture passes

**Given** an exactly periodic high-frequency noise texture whose interior adjacent-row difference is above 0.04
**When** the tiling seam check runs on it
**Then** no `not_seamless` error is raised

### AC2: A real wrap discontinuity on a busy texture still fails

**Given** a high-frequency noise texture that is not periodic, so its wrap difference is at least 3 times its interior adjacent-row difference
**When** the tiling seam check runs on it
**Then** `not_seamless` is raised and the message names the failing channel

### AC3: A visible seam on a smooth texture fails

**Given** a smooth texture with a step at the wrap that is under 0.04 in absolute terms but at least 10 times its interior adjacent-row difference
**When** the tiling seam check runs on it
**Then** `not_seamless` is raised

### AC4: Flat and near-flat textures pass

**Given** a constant-colour texture, or a near-flat 8-bit texture whose pixels vary by one quantization level
**When** the tiling seam check runs on it
**Then** no `not_seamless` error is raised and no division by zero occurs

### AC5: Texture-gen output bakes without edits

**Given** a non-tiling albedo passed through texture-gen's `make_seamless` post-process and used unmodified in a tiling material
**When** the bake runs on an `environment_piece` that uses it
**Then** the seam check passes for every baked channel

### AC6: Bake and texture-gen agree on what seamless means

**Given** any image in the test corpus (periodic, non-periodic, smooth-with-step, flat, near-flat, and `make_seamless` output; 8-bit and float; RGB and single-channel)
**When** it is judged by the bake seam check and by `nmg_game_dev.texture.seamless.is_seamless`
**Then** both give the same pass or fail result

### AC7: The error and docs describe the new measure and a fix

**Given** a `not_seamless` failure
**When** the author reads the error message, its remediation, and `docs/skills/bake-materials.md`
**Then** they state the measure used (wrap difference relative to the interior difference, with the floor), the message reports the wrap and interior values for each failing channel, and the remediation and docs name `python -m nmg_game_dev.texture seamless` as the make-seamless step for a source texture that does not tile

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | The bake seam check passes an axis when its wrap difference (mean absolute difference between the last and first pixel along the axis) is at most `max(1.5 × interior difference, 2/255)`, where the interior difference is the mean absolute difference between adjacent pixels along that axis; a channel fails when either axis fails. | Must |
| FR2 | The metric normalises integer images by their dtype maximum, so the 2/255 floor gives flat and near-flat textures a defined passing result without dividing by the interior difference. | Must |
| FR3 | `nmg_game_dev.texture.seamless.is_seamless` uses the same definition, ratio, and floor as the bake seam check, and a unit test holds the two implementations in step. | Must |
| FR4 | Regression tests cover AC1 to AC4 with generated tileable and non-tileable noise and smooth images, and a Blender-side test bakes a tileable noise material through the tiling path. | Must |
| FR5 | `make_seamless` output passes the bake seam metric, covered by a unit test and by a Blender bake of a `make_seamless` albedo. | Must |
| FR6 | The `not_seamless` message reports the wrap and interior values per failing channel; the `not_seamless` remediation in `bake_core/errors.py` names `python -m nmg_game_dev.texture seamless`. | Must |
| FR7 | `python -m nmg_game_dev.texture seamless <png> [--out <png>]` applies `make_seamless` to a PNG, writes it in place or to `--out`, and prints JSON with the output path and the `is_seamless` result; a missing input exits 1 with `ERROR [...]` and `Remediation:` lines. | Must |
| FR8 | `docs/skills/bake-materials.md`, `docs/asset-contract.md` (where it defines a seamless tiling texture), and `docs/onboarding/texture-models.md` describe the relative measure and the `seamless` subcommand. | Must |
| FR9 | The `not_seamless` reason code and the `check_seams` return shape (`dict[str, float]`, one value per channel) keep working for existing callers. | Must |

## Out of Scope

- Detecting visible repetition or low-frequency tiling artefacts away from the wrap.
- Changing the `make_seamless` algorithm.
- Changing the texel density check in `bake_core/tiling.py`.
- Automatically repairing a non-tiling material during the bake.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #147 | 2026-11-11 | Initial defect report |
