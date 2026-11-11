# Tasks: Tiling seam check rejects high-frequency textures that tile correctly

**Issue**: #147
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/67-bake-authored-materials-to-contract-compliant-uv-texture-sets/

## Implementation Tasks

### T001: Add the shared bpy-free seam metric

**File(s)**: `plugins/nmg-game-dev-blender-addon/bake_core/seam_metric.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- The module imports only the standard library and numpy and defines `SEAM_RATIO = 1.5`, `SEAM_FLOOR = 2 / 255`, `AxisSeam`, `normalize`, `measure`, `passes`, and `failure_detail` as in design.md.
- An axis passes when `wrap <= max(SEAM_RATIO * interior, SEAM_FLOOR)` on the normalised image (FR1, FR2).

### T002: Correct the bake seam check and its remediation

**File(s)**: `plugins/nmg-game-dev-blender-addon/bake_core/tiling.py`, `plugins/nmg-game-dev-blender-addon/bake_core/errors.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `SEAM_TOLERANCE` is removed; `check_seams` judges every channel with `seam_metric` and raises `BakeError` with reason `not_seamless` and the message from design.md, reporting wrap and interior values for each failing channel (AC1–AC4, FR6).
- `check_seams` still returns `dict[str, float]` with one value per channel (FR9).
- `REASONS["not_seamless"]` names `python -m nmg_game_dev.texture seamless` (AC7, FR6).

### T003: Align texture-gen's seamless check with the bake

**File(s)**: `src/nmg_game_dev/texture/seamless.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `SEAM_RATIO` and `SEAM_FLOOR` are defined with the same values as `bake_core/seam_metric.py`, and `is_seamless` applies the same normalisation, ratio, and floor (AC6, FR3).
- `make_seamless`, `seam_mad`, and `interior_mad` keep their signatures and behaviour.

### T004: Add the `seamless` CLI subcommand

**File(s)**: `src/nmg_game_dev/texture/__main__.py`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- `python -m nmg_game_dev.texture seamless <png> [--out <png>]` writes the `make_seamless` result in place or to `--out` and prints JSON `{"path", "seamless"}` with exit 0 (FR7).
- A missing input prints `ERROR [texture.input_missing]` and `Remediation:` to stderr and exits 1.

### T005: Document the measure and the make-seamless step

**File(s)**: `docs/skills/bake-materials.md`, `docs/asset-contract.md`, `docs/onboarding/texture-models.md`
**Type**: Modify
**Depends**: T002, T004
**Acceptance**:
- The `not_seamless` row in `docs/skills/bake-materials.md` states that a channel fails when a wrap differs from its opposite edge by more than 1.5× the interior adjacent-pixel difference (minimum 2/255) and names `python -m nmg_game_dev.texture seamless <image.png>` as the remediation (AC7, FR8).
- `docs/asset-contract.md` section 4 defines a seamless tiling texture with the same measure and points to the subcommand; `docs/onboarding/texture-models.md` documents the subcommand next to `generate` and `status` (FR8).

### T006: Add unit regression and parity coverage

**File(s)**: `tests/texture_fakes.py`, `tests/unit/texture/test_seam_metric.py`, `tests/unit/texture/test_cli.py`
**Type**: Create | Modify
**Depends**: T002, T003, T004
**Acceptance**:
- `tests/texture_fakes.py` gains seeded generators for exactly periodic band-limited noise (FFT-filtered, values 0–1, with a cutoff parameter) and for a non-periodic crop of a larger periodic field.
- `tests/unit/texture/test_seam_metric.py` loads `bake_core/seam_metric.py` and `bake_core/errors.py` by file path and covers: AC1 (periodic fine noise with asserted interior difference > 0.04 passes `seam_metric.passes` and `is_seamless`); AC2 (non-periodic noise with asserted wrap ≥ 3× interior fails and `failure_detail` names the channel); AC3 (smooth 0→0.03 gradient with asserted wrap < 0.04 and ≥ 10× interior fails); AC4 (constant float image and near-flat uint8 image with ±1 level noise pass); AC5 (`make_seamless` of `synthetic_image` and of uint8 white noise passes `seam_metric.passes`); AC6 (identical `SEAM_RATIO`/`SEAM_FLOOR` and identical pass/fail between `seam_metric.passes` and `is_seamless` on a corpus covering every image above in uint8 and float, RGB and single-channel); AC7 (`REASONS["not_seamless"]` contains `python -m nmg_game_dev.texture seamless`).
- `tests/unit/texture/test_cli.py` covers `seamless` in place, with `--out`, and with a missing input (FR7).
- Evidence: `repository.tests`, `repository.lint`, `repository.format`, `repository.types`.

### T007: Add BDD acceptance coverage

**File(s)**: `tests/bdd/features/tiling_seam_check.feature`, `tests/bdd/test_tiling_seam_check_bdd.py`
**Type**: Create
**Depends**: T006
**Acceptance**:
- The feature mirrors scenarios SCN001–SCN004, SCN006, and SCN007 from `feature.gherkin`; step definitions judge images with the add-on `seam_metric` loaded by file path and `is_seamless`, and check the `not_seamless` remediation and the `seamless` CLI output.
- Evidence: `repository.tests`.

### T008: Add Blender bake regression coverage

**File(s)**: `tests/blender/bake_fixtures.py`, `tests/blender/test_bake_tiling.py`
**Type**: Modify
**Depends**: T002, T003
**Acceptance**:
- `bake_fixtures.py` gains `noise_image(name, size=256, periodic=True, seed=0)` building exactly periodic fine noise (interior adjacent difference > 0.04) or, from a `uint8` array argument, an image whose pixels are that array divided by 255.
- `test_bake_tiling.py` replaces the absolute `0.04` assertions with the add-on's `seam_metric.passes` on each baked Desktop texture; adds AC1 (a periodic fine-noise tiling material bakes with no error and every baked texture passes) and AC5 (uint8 white noise passed through `make_seamless`, loaded from `src/nmg_game_dev/texture/seamless.py` by file path, bakes with no error and every baked texture passes); the existing non-periodic ramp test still raises `not_seamless` (AC2).
- Evidence: `gate-blender-headless` (`scripts/run-blender-tests.sh`).

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #147 | 2026-11-11 | Initial defect tasks |
