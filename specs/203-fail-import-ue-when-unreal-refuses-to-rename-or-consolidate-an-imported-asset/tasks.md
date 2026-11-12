# Tasks: import_ue reports success when Unreal refuses to rename or consolidate an imported asset

**Issue**: #203
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/145-fix-import-ue-importing-static-meshes-at-1-100-scale-on-ue-5-8/

## Implementation Tasks

### T001: Check every rename and consolidate result in the generated import code

**File(s)**: `src/nmg_game_dev/unreal/import_asset.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- In `_IMPORT_TEMPLATE` `_rename_to_parts`, a `False` from `unreal.EditorAssetLibrary.consolidate_assets(mesh, [_load(target)])` raises `RuntimeError("consolidate_assets refused to merge " + target + " into " + object_path)`. A `False` from `unreal.EditorAssetLibrary.rename_asset(object_path, target)` raises `RuntimeError("rename_asset refused to rename " + object_path + " to " + target)` (AC1, AC2, FR1).
- In `_ensure_rig_assets`, a `False` from `unreal.EditorAssetLibrary.rename_asset(created_path, physics)` raises `RuntimeError("rename_asset refused to rename " + created_path + " to " + physics)` before the existing `does_asset_exist(physics)` check (AC3, FR1).
- The generated code still contains the call text `consolidate_assets(mesh, [_load(target)])` and `rename_asset(object_path, target)`. No other template step, the `NMG_RESULT` schema, the error codes, or the remediation text changes (AC4).

### T002: Add rename and consolidate failure injection to the fake unreal module

**File(s)**: `tests/unit/fake_unreal.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `FakeWorld` gains `refused_renames: set[str]` and `refused_consolidations: set[str]`, both empty by default, and the class and module docstrings describe them (FR2).
- `EditorAssetLibrary.rename_asset(source, destination)` returns `False` and leaves `assets` and `saved` unchanged when `source` is in `refused_renames`. Otherwise its behavior is unchanged (FR2).
- `EditorAssetLibrary.consolidate_assets(to, assets)` returns `False` and leaves `assets`, `saved`, and `redirects` unchanged when any asset's path is in `refused_consolidations`. Otherwise its behavior is unchanged (FR2).
- The fake still contacts no running editor.

### T003: Unit tests for refused and successful renames and consolidations

**File(s)**: `tests/unit/test_unreal_import.py`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- AC1: stage a Desktop multi-part import with `SM_Crate` and `SM_Crate_Lid` (`duplicate=True`, so UE names it `SM_Crate_Lid_001`), and refuse the rename of `<dest>/SM_Crate_Lid_001`. `run_import_code` returns `ok: false` with error `RuntimeError: rename_asset refused to rename <dest>/SM_Crate_Lid_001 to <dest>/SM_Crate_Lid`. `run_import` raises `PipelineError` with code `import_ue.failed` whose message contains both paths.
- AC2: in the same scenario, seed existing assets at `<dest>/SM_Crate_Lid` and `<dest>/SM_Crate_Lid_001`, as in the existing re-import test, and refuse consolidation of `<dest>/SM_Crate_Lid`. The error is `RuntimeError: consolidate_assets refused to merge <dest>/SM_Crate_Lid into <dest>/SM_Crate_Lid_001`, `world.redirects` stays empty, and `run_import` raises `import_ue.failed` whose message contains both paths.
- AC3: stage a rigged Desktop import with `world.physics_folder = <dest>/Physics`, and refuse the rename of `<dest>/Physics/SM_Crate_PhysicsAsset`. The error is `RuntimeError: rename_asset refused to rename <dest>/Physics/SM_Crate_PhysicsAsset to <dest>/SM_Crate_PhysicsAsset`.
- AC4: with no refusals, a multi-part re-import that consolidates and renames returns `ok: true` with the same `static_meshes` keys and bounds, the same `redirects`, and the same saved paths as the existing #145 re-import test asserts. Every existing test in the file passes unchanged.
- No test starts a real Unreal Editor or Blender process. All tests run against `tests/unit/fake_unreal.py`.

### T004: BDD scenarios for AC1–AC4

**File(s)**: `tests/bdd/features/import_ue_refused_rename.feature`, `tests/bdd/steps/test_import_ue_refused_rename.py`
**Type**: Create
**Depends**: T001, T002
**Acceptance**:
- The feature file holds SCN001–SCN004 from this spec's `feature.gherkin`. Each is bound with `pytest_bdd.scenario` in the steps module, following `tests/bdd/steps/test_import_ue_static_scale.py`: a `state` fixture, `stage`/`part`/`run_import`/`run_import_code` from `tests.unit.fake_unreal`, and the failure-injection knobs from T002.
- SCN001–SCN003 assert the `import_ue.failed` code and the exact error text from T003. SCN004 asserts `ok: true`, the `static_meshes` keys, and the consolidation redirect.
- Passes under `repository.tests` (`uv run pytest tests/unit tests/bdd -q`), and the changed files pass `repository.lint`, `repository.format`, and `repository.types`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #203 | 2026-11-11 | Initial defect tasks |
