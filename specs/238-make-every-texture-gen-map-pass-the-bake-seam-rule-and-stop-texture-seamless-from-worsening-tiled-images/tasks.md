# Tasks: Generated texture maps fail the bake seam rule and `texture seamless` worsens tiled images

**Issue**: #238
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Add the edge-band seam repair and severity-based fix

**File(s)**: `src/nmg_game_dev/texture/seamless.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- FR3: `edge_band`, `repair_seam`, `seam_wraps`, `seam_ratios`, `EDGE_BAND_WIDTH = 8`, and `GROSS_SEAM_RATIO = 3.0` exist as described in design.md. `repair_seam` output passes `is_seamless` and keeps shape and dtype for uint8 and float64, RGB and single-channel inputs.
- FR4: `fix_seam` returns a passing input unchanged (array-equal), applies the band only when `max(seam_ratios) ≤ 3.0`, and otherwise applies `make_seamless` then `repair_seam(reference=input)`. On every axis the result's wrap is ≤ the input's.
- `is_seamless`, `make_seamless`, `SEAM_RATIO` and `SEAM_FLOOR` are unchanged.

### T002: Guarantee generated albedos and derived maps pass the seam rule

**File(s)**: `src/nmg_game_dev/texture/generate.py`, `src/nmg_game_dev/texture/maps.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- FR1, AC1: `_make_seamless_png` saves `repair_seam(result)` when `make_seamless`'s result fails `is_seamless`.
- FR2, AC2: `derive` checks N and AO with `is_seamless` and repairs a failing map before writing. N is band-repaired on the float normal vectors, renormalized to unit length, then encoded. R and M are unchanged.
- The module docstrings describe the check.

### T003: Make `texture seamless` leave passing images alone and never worsen a wrap

**File(s)**: `src/nmg_game_dev/texture/__main__.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- FR4, AC3, AC4: `_make_seamless_file` writes `fix_seam(image)` and prints `{"path", "seamless"}` with `seamless` from `is_seamless` of the written array. The `--out` and `texture.input_missing` behaviour is unchanged.
- The module docstring and the `seamless` subparser help describe the repair.

### T004: Document the repair and the reload/repack step

**File(s)**: `docs/onboarding/texture-models.md`, `docs/skills/bake-materials.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- FR6, AC6: the "Make a source texture seamless" section describes the severity-based repair and says images packed into a `.blend` file keep their old pixels until they are reloaded or repacked from the fixed files. The `not_seamless` remediation in `docs/skills/bake-materials.md` says the same. "Derived maps" says every map is checked against the seam rule.
- `CHANGELOG.md` `[Unreleased]` has a `### Fixed` bullet for this change ending with `(#238)`.

### T005: Add regression fixtures and unit tests

**File(s)**: `tests/texture_fakes.py`, `tests/unit/texture/test_seamless.py`, `tests/unit/texture/test_maps.py`, `tests/unit/texture/test_generate.py`, `tests/unit/texture/test_cli.py`
**Type**: Modify
**Depends**: T002, T003
**Acceptance**:
- `tests/texture_fakes.py` gains the following. Existing fixtures and the fake worker's default output are unchanged.
  - `low_contrast_crop(size=256, seed=5) -> np.ndarray`: uint8 RGB `rint(clip(0.5 + (periodic_crop(size, seed, 0.25) − 0.5) × 0.1, 0, 1) × 255)`.
  - `narrow_seam_albedo() -> np.ndarray`: `make_seamless(synthetic_image(256))` with its last row raised by 8 levels, clipped.
  - `stepped_normal_map() -> np.ndarray`: (128, 128, 255) plus seeded ±1 noise, with the last row's R and G raised by 3.
  - A `FAKE_WORKER_SOURCE_PNG` option, set through `fake_spawn(..., source_png=Path | None)`, that makes the fake worker copy that PNG to each item path.
- FR5, AC1: a `test_generate.py` test runs `generate` with the fake worker writing `low_contrast_crop()`, the `stone` preset and `ao=True`, and asserts that the albedo and its N, R, M and AO PNGs all pass `is_seamless`.
- FR5, AC2: `test_maps.py` asserts that every derived map passes `is_seamless` for `make_seamless(low_contrast_crop())` (AO fails there without the fix) and for the existing `synthetic_image` albedo. It also asserts that a band-repaired N is still a unit-vector encoding (atol 0.02, z > 0).
- AC3: `test_cli.py` asserts that `seamless` on `make_seamless(synthetic_image(256))`, in place and with `--out`, writes pixels equal to the input and prints `"seamless": true`.
- AC4: `test_cli.py` is parametrized over `synthetic_image(256)`, `narrow_seam_albedo()` and `stepped_normal_map()`. Each input fails `is_seamless` before the command runs. After it runs, the output passes, keeps shape and dtype, and on both axes `seam_wraps(output) ≤ seam_wraps(input)`.
- FR3/FR4: `test_seamless.py` covers `edge_band` and `repair_seam` on uint8 and float, RGB and gray inputs, a single failing axis whose repair pushes the other axis over, and `fix_seam`'s three branches.
- AC5: no existing test function in these files is modified or removed.
- Evidence: `uv run pytest tests/unit/texture -q` passes, and so do the `repository.tests`, `repository.lint`, `repository.format` and `repository.types` validations.

### T006: Add BDD scenarios for the seam repair

**File(s)**: `tests/bdd/features/texture_seam_repair.feature`, `tests/bdd/test_texture_seam_repair_bdd.py`
**Type**: Create
**Depends**: T004, T005
**Acceptance**:
- One pytest-bdd scenario per AC (SCN001–SCN006), matching `feature.gherkin`, with steps that use the T005 fixtures.
- SCN005 runs the existing texture unit and BDD modules (`tests/unit/texture`, `tests/bdd/test_texture_bdd.py`, `tests/bdd/test_tiling_seam_check_bdd.py`) through `pytest.main` in a subprocess and asserts exit 0.
- SCN006 reads the two docs and asserts that each mentions reloading or repacking images packed into a `.blend` file.
- Evidence: the `repository.tests` validation (`uv run pytest tests/unit tests/bdd -q`) passes.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #238 | 2026-11-18 | Initial defect tasks |
