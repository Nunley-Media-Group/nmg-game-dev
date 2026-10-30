# Tasks: Blender cleanup, decimate, LOD, and variant operators

**Issue**: #33
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Contract budget table and override resolution

**File(s)**: `plugins/nmg-game-dev-blender-addon/utils/budgets.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- `CONTRACT_BUDGETS` has all five classes with the Desktop and Mobile values from contract §6; `resolve_budget` merges `nmg-budgets.json` mobile overrides and rejects unknown classes or metrics with `variants.budget_override_invalid` (FR6, AC6)
- The module imports no `bpy`

### T002: Core cleanup and Mobile build

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/__init__.py`, `plugins/nmg-game-dev-blender-addon/variants_core/errors.py`, `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py`, `plugins/nmg-game-dev-blender-addon/variants_core/mobile.py`, `plugins/nmg-game-dev-blender-addon/variants_core/textures.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- Cleanup implements FR2 without decimation (AC2)
- The Mobile build implements the design's copy, deterministic decimation loop, LOD1/LOD2, LodGroup Empty, child-part fallback, and texture downscale (FR3, FR4, AC3, AC5)
- Validation raises `variants.asset_not_found`, `variants.unbaked_material`, `variants.mobile_material_limit`, or `variants.budget_unreachable` before any write (AC7)

### T003: Export and sidecars

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/export.py`, `plugins/nmg-game-dev-blender-addon/variants_core/sidecars.py`
**Type**: Create
**Depends**: T002
**Acceptance**:
- Both FBX exports use the contract §7 settings with identical unsuffixed names, and Desktop names are restored afterward (FR5, AC1)
- `nmg-variants.json`, `Mobile/nmg-asset.json`, and the result dict match the design (FR7, AC4, AC5)

### T004: Real operators

**File(s)**: `plugins/nmg-game-dev-blender-addon/operators/cleanup_desktop.py`, `plugins/nmg-game-dev-blender-addon/operators/optimize_mobile.py`, `plugins/nmg-game-dev-blender-addon/operators/generate_variants.py`, `plugins/nmg-game-dev-blender-addon/property_groups/pipeline_props.py`, `plugins/nmg-game-dev-blender-addon/panels/main_panel.py`, `plugins/nmg-game-dev-blender-addon/__init__.py`, `plugins/nmg-game-dev-blender-addon/utils/logging.py`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- The operators expose the design properties, call `variants_core`, store `last_result`, and report errors as `CANCELLED` with code, message, and remediation (FR1, AC4, AC7)
- `last_result` is added to the property group, and the panel shows the operator properties
- The `bl_info` description no longer says "stub"; the stub log helper is removed or replaced by a per-operator info log

### T005: Contract update and changelog

**File(s)**: `docs/asset-contract.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T004
**Acceptance**:
- Contract §5 states that the Mobile export is an LOD group `SM_<Name>` with `SM_<Name>_LOD0..2` children (LOD0 only for assets with child parts) (FR9)
- `CHANGELOG.md` `[Unreleased]` gets a bullet for the variant operators ending with `(#33)`

### T006: Budget table unit test

**File(s)**: `tests/unit/test_blender_budgets.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- Loads `utils/budgets.py` by file path, parses the §6 table in `docs/asset-contract.md`, and asserts every class's Desktop and Mobile triangle, texture, and material values match; covers override merging and invalid overrides (FR6, FR8, AC6)
- Passes under the `repository.tests`, `repository.lint`, and `repository.types` validations

### T007: Blender headless variant tests

**File(s)**: `tests/blender/conftest.py`, `tests/blender/test_variants.py`, `tests/blender/test_operator_stubs.py`
**Type**: Create | Modify | Delete
**Depends**: T004
**Acceptance**:
- `conftest.py` adds a fixture that builds collection `Crate` in a fresh scene: a subdivided `SM_Crate` of about 12,000 triangles, a baked-style `M_Crate_Body` with generated 2048 px `T_Crate_Body_BC/_N/_ORM` images saved to a temp dir, plus injected duplicate verts, a loose vertex, a zero-area face, and flipped normals. It also adds variants for an unbaked (Noise Texture) material and a two-material Mobile case
- `test_variants.py` covers AC1 (both FBX files re-imported with identical names), AC2, AC3 (LOD counts and ratios, 1024 px textures), AC4 (both sidecars and result keys), AC5 (two runs equal), AC6 (5,000-triangle override), AC7 (each failure code, with no files written), and AC8 (with `socket.socket` patched to raise)
- `test_operator_stubs.py` stub-behavior tests are removed; registration tests stay
- Passes with `BLENDER_APP` pointing at Blender 5.2 under `scripts/run-blender-tests.sh`

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #33 | 2026-10-29 | Initial feature tasks |
