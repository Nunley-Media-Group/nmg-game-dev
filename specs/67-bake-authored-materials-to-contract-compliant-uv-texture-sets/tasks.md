# Tasks: Bake authored materials to contract-compliant UV texture sets

**Issue**: #67
**Date**: 2026-10-30
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/30-add-contract-validation-re-import-check-and-review-renders/

## Implementation Tasks

### T001: Budget table with Desktop and Mobile overrides

**File(s)**: `plugins/nmg-game-dev-blender-addon/utils/budgets.py`
**Type**: Create | Modify
**Depends**: none
**Acceptance**:
- `CONTRACT_BUDGETS` matches contract §6 for all five classes, and `resolve_budget(asset_class, budgets_path)` merges `nmg-budgets.json` per design § Data / Storage Changes (top-level → Mobile, `desktop` → Desktop) (FR3, AC3)
- Unknown class or non-power-of-two size raises `BakeError` reason `budget_invalid`

### T002: Bake core — inspection, state, UVs, channels, packing

**File(s)**: `plugins/nmg-game-dev-blender-addon/bake_core/__init__.py`, `plugins/nmg-game-dev-blender-addon/bake_core/errors.py`, `plugins/nmg-game-dev-blender-addon/bake_core/inspect.py`, `plugins/nmg-game-dev-blender-addon/bake_core/state.py`, `plugins/nmg-game-dev-blender-addon/bake_core/uv.py`, `plugins/nmg-game-dev-blender-addon/bake_core/bake.py`, `plugins/nmg-game-dev-blender-addon/bake_core/pack.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- Material inspection rejects every AC6 reason in design § Material inspection with `texture.bake_failed`, naming the material
- UV handling keeps a valid layout and otherwise jointly unwraps per design § UVs, failing with `uv_unwrap_failed` when no UV area results (AC1, AC6)
- Channel bakes and packing produce BC (sRGB), N (OpenGL, Non-Color), and ORM (AO/roughness/metallic, Non-Color) PNGs at Desktop size and downscaled Mobile copies with identical names (FR2, AC1, AC3)
- Render visibility and every created datablock are restored or removed by `state` on success and failure (AC6)

### T003: Tiling, merging, rewire, proof, cache, and orchestration

**File(s)**: `plugins/nmg-game-dev-blender-addon/bake_core/tiling.py`, `plugins/nmg-game-dev-blender-addon/bake_core/rewire.py`, `plugins/nmg-game-dev-blender-addon/bake_core/proof.py`, `plugins/nmg-game-dev-blender-addon/bake_core/cache.py`, `plugins/nmg-game-dev-blender-addon/bake_core/core.py`
**Type**: Create
**Depends**: T002
**Acceptance**:
- `bake_asset` runs the design § Architecture sequence and returns the result schema in design § Data / Storage Changes; `run_for_mcp` returns it or the `error` dict (FR5, AC5)
- Rewire and part naming follow design § Rewire and § Part naming; merging produces one `M_<Name>_Body` set when the material count exceeds the Mobile limit (FR4, AC1, AC4)
- Tiling mode keeps UVs, bakes each material on a UV plane, and enforces the seam and texel-density checks (AC2)
- Proof renders write `<Name>_prebake.png` / `<Name>_baked.png` and fail with `proof_mismatch` beyond tolerance (FR6, AC1, AC6)
- An unchanged, already-baked asset returns `cache_hit: true` without writing files (FR7, AC7)

### T004: Operator and registration

**File(s)**: `plugins/nmg-game-dev-blender-addon/operators/bake_materials.py`, `plugins/nmg-game-dev-blender-addon/operators/__init__.py`, `plugins/nmg-game-dev-blender-addon/__init__.py`, `plugins/nmg-game-dev-blender-addon/property_groups/pipeline_props.py`, `plugins/nmg-game-dev-blender-addon/panels/main_panel.py`, `tests/blender/test_addon_registration.py`
**Type**: Create | Modify
**Depends**: T003
**Acceptance**:
- `nmggamedev.bake_materials` has the design properties, calls `bake_asset`, stores the result JSON in `scene.nmg_game_dev.last_result`, and returns `CANCELLED` with the code, message, and remediation reported on `BakeError` (AC5, AC6)
- The operator is in `REGISTER_CLASSES` and the panel; the registration test's operator count includes it

### T005: Pipeline texture stage

**File(s)**: `src/nmg_game_dev/pipeline/stages/texture.py`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- The placeholder is replaced by the stage in design § Pipeline stage: tier→class mapping, `out_dir`, optional `nmg-budgets.json`, the `run_for_mcp` script, the sidecar fields, and `error` → `PipelineError` mapping with stage `texture` (FR1, AC5, AC6)

### T006: Docs and changelog

**File(s)**: `docs/skills/bake-materials.md`, `docs/asset-contract.md`, `CHANGELOG.md`
**Type**: Create | Modify
**Depends**: T005
**Acceptance**:
- `docs/skills/bake-materials.md` documents the three entry points, inputs, output layout, merging, tiling mode, budget overrides, failure reasons with remediations, and the proof tolerance values (AC1, AC2, AC4, AC6)
- Contract §4 and §8 step 3 name the bake step and its pre-bake/baked renders
- `CHANGELOG.md` `[Unreleased]` gets a bullet ending with `(#67)`

### T007: Pipeline stage tests

**File(s)**: `tests/unit/pipeline/stages/test_texture.py`, `tests/bdd/features/texture_bake.feature`, `tests/bdd/test_texture_bake_bdd.py`
**Type**: Modify | Create
**Depends**: T005
**Acceptance**:
- Unit tests with a scripted Blender fake cover: the script calls `run_for_mcp` with the prompt's collection, mapped class, and `out_dir`; the sidecar carries texture paths, byte totals, proof, and summary (AC5); an `error` result raises `PipelineError` `texture.bake_failed` with stage `texture` (AC6); a `cache_hit` result passes through (AC7); a raised client exception becomes `mcp.blender.unreachable`
- `texture_bake.feature` scenarios for AC5 and AC6 at the stage level run under pytest-bdd
- Passes under the `repository.tests`, `repository.lint`, and `repository.types` validations

### T008: Blender headless bake tests

**File(s)**: `tests/blender/bake_fixtures.py`, `tests/blender/test_bake_unique.py`, `tests/blender/test_bake_tiling.py`, `tests/blender/test_bake_failures.py`, `tests/blender/test_bake_cache.py`
**Type**: Create
**Depends**: T004
**Acceptance**:
- Fixtures build, in code, a procedural-material asset (Noise/Voronoi + Bump), a triplanar asset (Geometry Position / Box projection), an image-texture asset with a valid `UVMap`, a three-material `standard_prop`, a tiling `environment_piece` plane with UVs spanning 0–10, and one fixture per AC6 reason; tests use an `nmg-budgets.json` override of 256 px Desktop / 128 px Mobile and low samples
- `test_bake_unique.py` covers AC1 (UVMap present; an existing valid UVMap is unchanged; PNG names, sizes, and color spaces; rewired node types; proof within tolerance for all three material kinds), AC3 (Desktop/Mobile sizes, byte totals), AC4 (merged `M_<Name>_Body` vs per-material under the limit), and AC5 (operator and direct call produce the same result)
- `test_bake_tiling.py` covers AC2 (UVs preserved, seam check pass, a non-periodic material fails `not_seamless`, low density fails `texel_density`)
- `test_bake_failures.py` covers AC6 (each reason raises `texture.bake_failed` naming the target; original materials and UV layers restored)
- `test_bake_cache.py` covers AC7 (second run `cache_hit: true`, PNG mtimes unchanged; a material edit causes a rebake)
- Passes with `BLENDER_APP` set to Blender 5.2 under `scripts/run-blender-tests.sh`

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #67 | 2026-10-30 | Initial feature tasks |
