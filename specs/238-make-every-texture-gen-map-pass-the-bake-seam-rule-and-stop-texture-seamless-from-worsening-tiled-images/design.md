# Root Cause Analysis: Generated texture maps fail the bake seam rule and `texture seamless` worsens tiled images

**Issue**: #238
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Root Cause

`is_seamless` (and the bake's `seam_metric.passes`) compares one line, the mean absolute difference between the first and last pixel along an axis, with the mean adjacent-pixel difference over the whole interior. The allowance is `max(1.5 × interior, 2/255)`.

`make_seamless` blends each axis with a half-rolled copy under a `sin²` window. Across most of the image the output is an average of two uncorrelated copies, so its adjacent-pixel steps are smaller than the original's. At the wrap, the weight is near 0 and the output joins `orig[n/2 − 1]` to `orig[n/2]`, a full, un-averaged original step. The wrap/interior ratio therefore lands close to 1.5, and the single-line wrap sample varies enough to cross it. The derived maps make this worse. N and AO are high-pass functions of luminance with a much smaller interior, so the same residual crosses their allowance more often. With `make_seamless(u8(0.5 + (periodic_crop(256, 5, 0.25) − 0.5) × 0.1))`, the albedo passes (axis ratios 0.60 / 0.67), but the derived AO fails on axis 1 (wrap 0.0112 vs allowance 0.0105).

`maps.derive` already wraps: N uses `np.roll` central differences and AO uses `_wrap_box_blur`. No clamping path remains. What's missing is a check: neither `generate._generate` nor `maps.derive` verifies a written map with `is_seamless`.

`__main__._make_seamless_file` always applies `make_seamless`. On an image that already tiles, that moves the earlier blend region and adds a new one, and nothing compares the result with the input.

The existing tests miss all of this. `test_maps.py` checks derived seams only for `synthetic_image`, whose 0–20 per-pixel noise makes the interior, and so the allowance, large.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `src/nmg_game_dev/texture/seamless.py` | `make_seamless`, `is_seamless` | Post-process and seam rule. No repair that guarantees a pass |
| `src/nmg_game_dev/texture/generate.py` | `_make_seamless_png` | Writes the albedo after `make_seamless` without checking it |
| `src/nmg_game_dev/texture/maps.py` | `derive` | Writes N and AO without checking them |
| `src/nmg_game_dev/texture/__main__.py` | `_make_seamless_file`, the `seamless` subparser help | Always re-blends, never compares with the input |
| `tests/texture_fakes.py` | `synthetic_image`, fake worker | Only noisy fixtures, which hide the failure |

## Fix Strategy

Add a deterministic edge-band repair whose result always passes, and call it wherever a written map fails the seam check. The CLI uses a severity rule, so a passing image is never touched and a failing one never ends up with a worse wrap.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `src/nmg_game_dev/texture/seamless.py` | Add `EDGE_BAND_WIDTH: Final = 8` and `GROSS_SEAM_RATIO: Final = 3.0`. Add `seam_wraps(img) -> tuple[float, float]`: the normalized wrap per axis (0 then 1). Add `seam_ratios(img) -> tuple[float, float]`: wrap ÷ `max(SEAM_RATIO × interior, SEAM_FLOOR)` per axis. Add `edge_band(img, axis, width=EDGE_BAND_WIDTH) -> Image`, which works in float64 from an unmodified copy. With `w = max(1, min(width, n // 2))`, for `k < w` and `t = 0.5 × (1 − k / w)`, it sets `line[k] = (1 − t)·src[k] + t·src[n−1−k]` and `line[n−1−k] = (1 − t)·src[n−1−k] + t·src[k]`. Add `repair_seam(img, reference=None) -> Image`, which runs at most two passes. Each pass applies `edge_band` along every axis that fails `is_seamless` or, when `reference` is given, whose wrap exceeds `seam_wraps(reference)` on that axis. It rounds and clips integer results to the dtype once at the end. Add `fix_seam(img) -> Image`: return `img` when it passes. Return `repair_seam(img, reference=img)` when `max(seam_ratios(img)) ≤ GROSS_SEAM_RATIO`. Otherwise return `repair_seam(make_seamless(img), reference=img)`. `is_seamless` and `make_seamless` stay unchanged. | FR3, FR4 |
| `src/nmg_game_dev/texture/generate.py` | `_make_seamless_png`: after `make_seamless`, replace the result with `repair_seam(result)` when `is_seamless(result)` is false, then save. | FR1, AC1 |
| `src/nmg_game_dev/texture/maps.py` | In `derive`: when the encoded N fails `is_seamless`, apply `edge_band` to the float `normal` field along each failing axis, renormalize each pixel to unit length, re-encode, and recheck (at most two passes). Then save. When the AO u8 array fails `is_seamless`, replace it with `repair_seam(ao)` before saving. R and M are constant and unchanged. Update the module docstring: each map is checked against the seam rule. | FR2, AC1, AC2 |
| `src/nmg_game_dev/texture/__main__.py` | `_make_seamless_file` writes `fix_seam(image)` (in place or to `--out`) and prints `{"path", "seamless": is_seamless(result)}`. Update the module docstring and the `seamless` subparser help to describe repair rather than "apply make_seamless". | FR4, AC3, AC4 |
| `docs/onboarding/texture-models.md` | In "Make a source texture seamless": a passing image is left unchanged, a narrowly failing one gets an 8 px edge blend, and a non-tiling one is cross-faded and then edge-blended. The output always passes and its wrap never gets worse. Add that images packed into a `.blend` keep their old pixels until reloaded or repacked from the fixed files. In "Derived maps", state that each map is checked against the same seam rule. | FR6, AC6 |
| `docs/skills/bake-materials.md` | In the `not_seamless` remediation, add that images packed into the `.blend` must be reloaded or repacked from the fixed files before rerunning. | FR6, AC6 |
| `CHANGELOG.md` | Under `## [Unreleased]` → `### Fixed`, add one bullet ending `(#238)`. | Release notes |

## Blast Radius

`generate.run` / `run_batch` (CLI, texture-gen MCP and job queue) call `_make_seamless_png` and `derive`. Their outputs change only when a map would have failed the seam rule, and then only within 8 px of the edges. `texture seamless` changes output only for failing inputs. The `is_seamless` / `seam_metric` parity, the JSON shapes, and the file names and folders are unchanged. The bake and `bake_core` are untouched.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Edge band (weight 0.5 at the wrap) as the guaranteed repair | Selected | Makes the two wrap lines identical, so the wrap is 0 and always passes. It changes only 8 px per side. |
| Re-run `make_seamless` until it passes | Rejected | Not convergent. A second half-roll on an already-blended image can widen the wrap. |
| Edge band only in the CLI, for all failing inputs | Rejected | A grossly non-tiling photo would show an 8 px smear. The half-roll hides a large mismatch better (interview decision). |
| Loosen the seam rule | Rejected | Out of scope. The bake's rule is canonical (#147). |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #238 | 2026-11-18 | Initial defect design |
