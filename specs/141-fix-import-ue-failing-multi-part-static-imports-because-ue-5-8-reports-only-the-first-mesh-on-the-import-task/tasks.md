# Tasks: import_ue fails multi-part static imports because UE 5.8 reports only the first mesh on the import task

**Issue**: #141
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/102-preserve-the-rig-when-finalizing-a-character-rigged-with-rig-humanoid/

## Implementation Tasks

### T001: Resolve expected meshes from the destination folder and guarantee rig assets

**File(s)**: `src/nmg_game_dev/unreal/import_asset.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- The generated code resolves meshes only through `_resolve_expected`, which tries each `PARAMS["expected_meshes"]` candidate as `<dest>/<name>` with `does_asset_exist` and `load_asset` and checks the asset class. It does not read `imported_object_paths` or call `get_objects()` (AC1, AC2, FR1, FR2).
- Missing expected meshes raise one error that lists all of them, which `import_variant` reports as `import_ue.failed` (AC6, FR5).
- The rigged Desktop path calls `_ensure_rig_assets`:
  - it fails when `SM_<Name>_Skeleton` is missing;
  - when `SM_<Name>_PhysicsAsset` is missing, it creates the physics asset with `SkeletalMeshEditorSubsystem.create_physics_asset`, moves it to `<dest>/SM_<Name>_PhysicsAsset` if needed, assigns it as `physics_asset`, and saves both;
  - it fails when the physics asset is still missing (AC3, FR3).
- The rigged Mobile path is unchanged apart from folder resolution of the root mesh (AC4).
- Folder resolution replaces only the task-list lookup. #145's multi_part, build-scale, and rename steps still run on the resolved meshes, and #146's candidate lists from `_expected_mesh_candidates` are used as given (FR2, FR7).
- Texture import, material binding, LOD import, `NMG_RESULT` keys, and error codes are unchanged. The template contains no `Interchange.FeatureFlags` (AC8, AC9, FR6, FR7).
- The module docstring describes folder resolution and the physics-asset fallback.

### T002: Extend the shared in-memory fake `unreal` module

**File(s)**: `tests/unit/fake_unreal.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- Reuses the shared fake from #145. It creates the file only if it is not on the default branch when this task runs, and keeps every existing helper and behavior #145's tests rely on.
- Provides the fake classes and functions listed in design.md and a `run_import_code(code, scenario)` helper. The helper installs the fake as `sys.modules["unreal"]`, `exec`s the generated code, and returns the `NMG_RESULT` dict parsed with `parse_nmg_result`.
- Scenarios can create assets with chosen bounds and material slots, set `imported_object_paths` to a chosen subset, omit the skeleton or physics asset, and replace existing assets.
- Imports no real `unreal`, opens no socket, and starts no process (FR8).

### T003: Executed-code regression tests

**File(s)**: `tests/unit/test_unreal_import.py`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- Two-part static import whose task lists only `SM_Crate`, while `SM_Crate_Body` and `SM_Crate_Lid` exist: the result is `ok` with both parts in `static_meshes` and their bounds (AC1, AC7).
- A folder holding an extra unrelated Static Mesh: it is not reported or bound (AC2).
- Rigged Desktop import with no physics asset created: the result is `ok`, the fake records one `create_physics_asset` call, `<dest>/SM_Crate_PhysicsAsset` exists and is assigned, and both assets are saved. The same scenario without a skeleton fails, naming the skeleton path (AC3).
- Rigged Mobile import after that Desktop scenario: the result is `ok`, the import options carry the Desktop skeleton and physics asset, and `import_lod` is called for levels 1 and 2 (AC4).
- Re-import whose scenario replaces `SM_Crate` with new bounds: the result reports the new bounds, and `check_pivots` passes against a matching snapshot (AC5).
- Two expected parts missing: `import_variant` with a fake client that runs the code raises `import_ue.failed`, and the message names both (AC6).
- Single-part baseline: texture settings, `MI_Crate_Body` creation and binding, the result keys, and the pivot check match the existing expectations (AC8).
- A test scans `src/`, `skills/`, `docs/`, `scripts/`, and `templates/` and finds no `Interchange.FeatureFlags.Import.FBX`, and the generated code contains no `Interchange.FeatureFlags` (AC9).
- Existing tests in the file, including those added by #145 (and #146 when implemented), keep passing.
- Evidence: `uv run pytest tests/unit/test_unreal_import.py -q`; `repository.tests`, `repository.lint`, `repository.format`, `repository.types`. No live editor is used.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #141 | 2026-11-11 | Initial defect tasks |
