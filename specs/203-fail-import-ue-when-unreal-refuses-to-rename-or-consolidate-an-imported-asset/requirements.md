# Defect Report: import_ue reports success when Unreal refuses to rename or consolidate an imported asset

**Issue**: #203
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/145-fix-import-ue-importing-static-meshes-at-1-100-scale-on-ue-5-8/

## Reproduction

1. Finalize a multi-part static asset whose part `SM_Crate_Lid` has the mesh datablock `SM_Crate_Lid.001`, so UE imports it as `SM_Crate_Lid_001` and the generated code renames it to `SM_Crate_Lid`.
2. Have Unreal refuse the rename (`EditorAssetLibrary.rename_asset` returns `False`, for example because the asset is referenced or checked out), or, on a re-import where `SM_Crate_Lid` already exists, refuse the consolidation (`consolidate_assets` returns `False`).
3. Run `import_ue` for the variant.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | The import fails with `import_ue.failed`, naming the asset Unreal refused to rename or consolidate and its intended target. |
| **Actual** | The generated code ignores the `False` result. `NMG_RESULT` reports `ok: true`, `static_meshes` can name a path that does not exist, and the pivot and material-binding steps run against a stale asset. The physics-asset move in a rigged Desktop import ignores its rename result too, and then fails with an error that does not name the created asset. |

## Acceptance Criteria

### AC1: A failed rename fails the import

**Given** a static multi-part import where `rename_asset` returns `False` for a part
**When** the import code runs
**Then** `NMG_RESULT` reports an error naming the source path and the intended target, and `import_variant` raises `import_ue.failed`

### AC2: A failed consolidate fails the import

**Given** a re-import where the target asset exists and `consolidate_assets` returns `False`
**When** the import code runs
**Then** `NMG_RESULT` reports an error naming the mesh and the target, and `import_variant` raises `import_ue.failed`

### AC3: The physics-asset rename is checked

**Given** a rigged Desktop import where `rename_asset` for the created physics asset returns `False`
**When** the import code runs
**Then** the error names the created path and the expected `SM_<Name>_PhysicsAsset` path

### AC4: Successful imports are unchanged

**Given** imports where every rename and consolidate succeeds
**When** the import code runs
**Then** the result, schema and error codes are as before

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Every `rename_asset` and `consolidate_assets` call in the generated import code checks its return value and raises with the source and target paths when it is `False` | Must |
| FR2 | Unit tests drive the generated code against the in-memory fake `unreal` module (`tests/unit/fake_unreal.py`), with failure injection for rename and consolidate, covering AC1–AC4 | Must |

## Out of Scope

- Retrying a refused rename or consolidation, or freeing the asset that blocks it.
- Other `EditorAssetLibrary` calls whose results the code ignores, such as `save_loaded_asset`.
- Running the import against a live Unreal Editor in tests.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #203 | 2026-11-11 | Initial defect report |
