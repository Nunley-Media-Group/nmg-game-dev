# Root Cause Analysis: Tiling seam check rejects high-frequency textures that tile correctly

**Issue**: #147
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/67-bake-authored-materials-to-contract-compliant-uv-texture-sets/

## Root Cause

`bake_core/tiling.py` `seam_error()` returns the larger of the mean absolute differences between the first and last pixel column and between the first and last pixel row, and `check_seams()` fails any channel above the absolute `SEAM_TOLERANCE = 0.04`. In a wrapped texture the first and last rows are neighbours across the wrap, so their difference equals the texture's ordinary adjacent-row difference. For a busy texture that is above 0.04 everywhere, so the check measures how busy the texture is rather than whether the wrap is discontinuous. The same absolute threshold lets a smooth texture with a visible wrap step under 0.04 pass.

`src/nmg_game_dev/texture/seamless.py` `is_seamless()` already uses a relative measure (wrap ≤ 1.5 × interior adjacent difference), so texture-gen output that passes its own check fails the bake. `is_seamless()` has no floor, so a near-flat 8-bit image whose interior step is a fraction of one quantization level can fail it.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `plugins/nmg-game-dev-blender-addon/bake_core/tiling.py` | `SEAM_TOLERANCE`, `seam_error`, `check_seams` | Absolute threshold on the wrap difference |
| `plugins/nmg-game-dev-blender-addon/bake_core/core.py` | `_pack` | Calls `tiling.check_seams(name, {"BC", "N", "ORM"})` in tiling mode; ignores the return value |
| `plugins/nmg-game-dev-blender-addon/bake_core/errors.py` | `REASONS["not_seamless"]` | Remediation with no usable step |
| `src/nmg_game_dev/texture/seamless.py` | `is_seamless` | Relative measure with no floor; differs from the bake |
| `src/nmg_game_dev/texture/__main__.py` | `_build_parser`, `main` | No command to make an existing texture seamless |
| `docs/skills/bake-materials.md` | Failure reasons table | Describes the 0.04 rule |

## Fix Strategy

Define one seam measure and use it in both places.

For an image normalised to 0–1 floats (integer dtypes divided by `np.iinfo(dtype).max`; float images used as-is) and each axis in (0, 1):

- `wrap` = mean absolute difference between the last and first pixel along the axis;
- `interior` = mean absolute difference between adjacent pixels along the axis (`np.diff`);
- `allowed` = `max(SEAM_RATIO × interior, SEAM_FLOOR)` with `SEAM_RATIO = 1.5` and `SEAM_FLOOR = 2 / 255`;
- the axis passes when `wrap <= allowed`; the image passes when both axes pass.

The floor is the only absolute term: a flat image (`interior = 0`) is judged against 2/255 without division, and quantization noise of one or two 8-bit levels passes. A visible step of e.g. 0.03 on a smooth image exceeds both terms and fails.

### New bpy-free module `bake_core/seam_metric.py`

Numpy-only, with no imports from the add-on package, so pytest under plain CPython can load it by file path (the `tests/unit/test_blender_budgets.py` pattern) without importing `bake_core/__init__.py` (which imports `bpy`).

| Symbol | Behaviour |
|--------|-----------|
| `SEAM_RATIO: Final = 1.5`, `SEAM_FLOOR: Final = 2 / 255` | Shared thresholds |
| `AxisSeam` (frozen dataclass: `axis: int`, `wrap: float`, `interior: float`, `allowed: float`, `passes: bool`) | One axis measurement |
| `normalize(img) -> NDArray[np.float64]` | Integer → divided by dtype max; float → `astype(float64)` |
| `measure(img) -> tuple[AxisSeam, AxisSeam]` | Measurements for axis 0 (rows, V) and axis 1 (columns, U) of an H×W or H×W×C image |
| `passes(img) -> bool` | Both axes pass |
| `failure_detail(kind, seams) -> str` | For the worst failing axis (largest `wrap / allowed`): `"{kind} wrap {wrap:.3f} vs interior {interior:.3f}"` |

### `bake_core/tiling.py`

- Remove `SEAM_TOLERANCE`. Import `seam_metric` relatively (`from . import seam_metric`).
- `seam_error(rgb)` returns `max(seam.wrap for seam in seam_metric.measure(rgb))`.
- `check_seams(name, channels)` measures each channel; when any fail it raises `BakeError("not_seamless", message, target=name)` with message
  `"Tiling material '{name}' is not seamless ({details}); a wrap may differ by at most 1.5x the interior difference (minimum 0.008)."`
  where `details` joins `failure_detail(kind, seams)` for each failing channel in sorted order with `", "`, and the numbers in the trailing clause are formatted from `SEAM_RATIO` and `SEAM_FLOOR`. Otherwise it returns `{kind: max wrap}` — the same `dict[str, float]` shape as before.
- Update the module docstring: the seam check compares the wrap difference with the interior difference.

### `bake_core/errors.py`

`REASONS["not_seamless"]` becomes: `"Make the source texture tile: run python -m nmg_game_dev.texture seamless <image.png>, or make the procedural material periodic across 0 to 1 UV, then rerun the bake."`

### `src/nmg_game_dev/texture/seamless.py`

- Add `SEAM_RATIO: Final = 1.5`, `SEAM_FLOOR: Final = 2 / 255`, and a private `_normalize(img)` identical in behaviour to the add-on's `normalize`.
- `is_seamless(img, ratio: float = SEAM_RATIO) -> bool`: true when for both axes `seam_mad(n, axis) <= max(ratio * interior_mad(n, axis), SEAM_FLOOR)` with `n = _normalize(img)`.
- `seam_mad`, `interior_mad`, and `make_seamless` keep their signatures and behaviour.
- Module docstring states that the bake seam check (`bake_core/seam_metric.py`) uses the same definition.

### `src/nmg_game_dev/texture/__main__.py`

| Interface | Input | Output / Error | Behaviour |
|-----------|-------|----------------|-----------|
| `python -m nmg_game_dev.texture seamless <path> [--out <path>]` | A PNG path; optional output path | stdout JSON `{"path": "<written path>", "seamless": <bool>}`, exit 0 | Loads the PNG with Pillow as a numpy array, applies `make_seamless`, saves to `--out` (parent created) or over the input, and reports `is_seamless` of the written array |
| same, input missing or unreadable | — | stderr `ERROR [texture.input_missing]: ...` and `Remediation: Pass the path of an existing PNG texture.`; exit 1 | Raised as `TextureGenError` and printed by the existing handler in `main` |

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `plugins/nmg-game-dev-blender-addon/bake_core/seam_metric.py` | New bpy-free shared metric | FR1, FR2 |
| `plugins/nmg-game-dev-blender-addon/bake_core/tiling.py` | Use the metric; new message; keep return shape | AC1–AC4, FR6, FR9 |
| `plugins/nmg-game-dev-blender-addon/bake_core/errors.py` | New `not_seamless` remediation | AC7, FR6 |
| `src/nmg_game_dev/texture/seamless.py` | Same definition with normalisation and floor | AC6, FR3 |
| `src/nmg_game_dev/texture/__main__.py` | `seamless` subcommand | AC7, FR7 |
| `docs/skills/bake-materials.md`, `docs/asset-contract.md`, `docs/onboarding/texture-models.md` | Describe the measure and the subcommand | AC7, FR8 |
| Tests (see tasks) | Regression, parity, CLI, BDD, Blender bake | FR4, FR5 |

## Blast Radius

- `bake_core/core.py` `_pack` is the only caller of `check_seams`; it ignores the return value and relies on the `not_seamless` reason, both preserved.
- `is_seamless` callers (`tests/unit/texture/test_seamless.py`, `tests/unit/texture/test_maps.py`, `tests/bdd/test_texture_bdd.py`) pass `make_seamless` output and derived maps; adding the floor only widens the pass set by up to 2/255, and the existing assertions that compare `seam_mad` with `1.5 * interior_mad` directly are unaffected.
- `tests/blender/test_bake_tiling.py` asserts the old absolute 0.04 rule on baked textures; it moves to the new metric.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Duplicate the metric in a bpy-free add-on module plus `seamless.py`, held by a parity test | Selected | The add-on runs in Blender's bundled Python without `nmg_game_dev` on its path; a numpy-only module is loadable by both Blender and plain pytest |
| Import `nmg_game_dev.texture.seamless` from the add-on | Rejected | The add-on is installed into consumers' Blender separately from the Python package |
| Raise the absolute tolerance | Rejected | Still fails finer textures and still passes visible steps on smooth ones |
| Document calling `make_seamless` from Python instead of a CLI subcommand | Rejected | Authors need a one-line step they can run on a PNG |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #147 | 2026-11-11 | Initial defect design |
