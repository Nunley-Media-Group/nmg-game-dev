# Tasks: A millimetre-scale pivot offset on a rigged mesh blocks finalize

**Issue**: #244
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/140-fix-finalize-export-failing-the-contract-on-mobile-lods-the-variants-step-decimated/

## Implementation Tasks

### T001: Rigged authored pivot allowance

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/validate.py`, `plugins/nmg-game-dev-blender-addon/contract_core/report.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `bottom_center(meshes)` is public, and `_pivot_findings` uses it
- Authored validation of a rigged desktop variant holds the bottom center to 5 mm and the origin to 1 mm. Everything else keeps 1 mm.
- A failing rigged authored check names the 5 mm re-seat limit, and the `pivot.bottom_center` remediation states the rigged allowance

### T002: Re-seat the rigged Desktop mesh in the variants step

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py`, `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `reseat_desktop` moves only mesh data, by one world offset measured with `bottom_center`. It skips static assets and offsets of exactly zero.
- `cleanup_desktop` reports `pivot: {"reseated", "offset"}`, and the variants step outputs include it
- The existing `tests/blender/test_variants_clean.py`, `tests/blender/test_variants_rigged.py`, and `tests/blender/test_contract_validate.py` pass

### T003: Document the rigged allowance

**File(s)**: `docs/asset-contract.md`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- Section 2 states that a rigged asset may sit up to 5 mm off at authoring time, that finalize's variants step moves its mesh data onto the origin, and that static assets stay at 1 mm

### T004: Add regression coverage

**File(s)**: `tests/blender/test_pivot_reseat.py`
**Type**: Create
**Depends**: T002
**Acceptance**:
- The fixture builds the rigged hero with `rig_fixtures.reset_scene`, `build_hero`, `rig_humanoid`, and `add_baked_hero_material`, then translates the `SM_Hero` data so that `bottom_center` equals a target offset
- SCN001 (AC1): at `(0.0006, 0.0013, -0.0007)`, authored `validate_asset("Hero", "character", authored=True)` has no `pivot.bottom_center` finding. After `cleanup_desktop("Hero")`, `bottom_center` is within 1 mm of the origin, and `pivot.reseated` is true.
- SCN002 (AC2): a second skinned part parented to `SM_Hero` moves by the same world offset. Object `matrix_world` values, modifier lists, vertex-group names and weights, and the rig's bone heads and tails are equal before and after.
- SCN003 (AC3): on a hero exactly on the origin, the vertex positions are unchanged, and `pivot` is `{"reseated": False, "offset": [0.0, 0.0, 0.0]}`
- SCN004 (AC4): at `(0.0, 0.0, 0.02)`, authored validate fails `pivot.bottom_center`, and the message contains `5 mm`
- SCN005 (AC5): `contract_fixtures.build_crate` translated to 1.3 mm fails and translated to 0.8 mm passes authored validate. After `cleanup_desktop("Crate")`, `pivot.reseated` is false.
- SCN006 (AC6): after `cleanup_desktop` and `optimize_mobile` on the SCN001 asset, `validate_asset("Hero", "character")` has no `pivot.bottom_center` finding. After `export_variants`, `run_isolated` on each variant directory reports no finding whose rule starts with `reimport.pivot`.
- On the pre-fix code, SCN001 and SCN003 fail and SCN005 passes
- `scripts/run-blender-tests.sh` (gate-blender-headless), `repository.lint`, `repository.format`, and `repository.types` pass

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #244 | 2026-11-18 | Initial defect tasks |
