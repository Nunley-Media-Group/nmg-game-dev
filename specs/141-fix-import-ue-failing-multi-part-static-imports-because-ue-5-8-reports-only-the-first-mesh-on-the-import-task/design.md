# Root Cause Analysis: import_ue fails multi-part static imports because UE 5.8 reports only the first mesh on the import task

**Issue**: #141
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/102-preserve-the-rig-when-finalizing-a-character-rigged-with-rig-humanoid/

## Root Cause

`_imported_assets` in the `_IMPORT_TEMPLATE` of `src/nmg_game_dev/unreal/import_asset.py` builds the mesh list from `AssetImportTask.imported_object_paths`. On UE 5.8, an FBX imported with `combine_meshes = False` lists only the first mesh there, though every part is created in the destination folder. `_check_expected` then raises `no static mesh for snapshot part` for the first part that is not listed. `_import_skeletal` uses the same list and requires exactly one Skeletal Mesh from it.

For a rigged Desktop import, `_skeletal_options(desktop=True)` asks for a physics asset, and `_bind_materials` reports `physics_asset` as `_physics_path()` without checking that it exists. The Mobile import then calls `_load(_physics_path())` and raises `asset not found`. `SM_<Name>_Skeleton` is assumed the same way.

The existing unit tests only compile the generated code and check its text, so nothing exercised an import task that under-reports.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `src/nmg_game_dev/unreal/import_asset.py` | `_IMPORT_TEMPLATE`: `_imported_assets`, `_import_meshes`, `_import_skeletal`, `_check_expected` | Trusts the task's object list |
| `src/nmg_game_dev/unreal/import_asset.py` | `_IMPORT_TEMPLATE`: `_bind_materials` (skeletal branch) | Reports an unchecked physics asset |
| `tests/unit/test_unreal_import.py` | — | No executed-code coverage |

## Fix Strategy

All changes are inside `_IMPORT_TEMPLATE`. The host-side Python API, `NMG_RESULT` keys, and error codes are unchanged.

1. **Resolve from the folder.** Replace `_imported_assets` and `_check_expected` with `_resolve_expected(asset_class)`:
   - For each candidate list in `PARAMS["expected_meshes"]`, try each name in order. For `path = dest + "/" + name`, when `EditorAssetLibrary.does_asset_exist(path)`, it loads the asset. When the asset `isinstance(asset_class)`, it takes `(path, asset)` and stops.
   - A list with no match adds `candidates[0]` to `missing`.
   - When `missing` is non-empty, it raises `RuntimeError("no static mesh for snapshot part: " + ", ".join(missing))`, or `"no skeletal mesh for snapshot part: "` for a rigged asset.
   - It returns the resolved list, de-duplicated by path in candidate order.
   - `task.imported_object_paths` is no longer read.
2. **Static path.** `_import_meshes` runs the import task, then `_resolve_expected(unreal.StaticMesh)`. The former "imported no static meshes" check is covered by `missing`.
3. **Skeletal path.** `_import_skeletal` runs the import task, then `_resolve_expected(unreal.SkeletalMesh)`, which must yield exactly one mesh, the root. LOD import on Mobile is unchanged.
4. **Skeleton and physics guarantee (Desktop only).** After the Desktop skeletal import, `_ensure_rig_assets(mesh)` runs:
   - When `_skeleton_path()` does not exist, it raises `RuntimeError("skeleton missing after import: " + path)`.
   - When `_physics_path()` does not exist, it calls `unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem).create_physics_asset(mesh)`, the call ghost1 used. If the created asset's path is not `_physics_path()`, it is moved there with `EditorAssetLibrary.rename_asset`. The asset is assigned with `mesh.set_editor_property("physics_asset", physics)`, and both are saved with `save_loaded_asset`.
   - When `_physics_path()` still does not exist afterwards, it raises `RuntimeError("physics asset missing after import: " + path)`.
5. **Re-import.** Because meshes are loaded from the folder after `import_asset_tasks` returns with `replace_existing = True`, the bounds come from the replaced assets.
6. Nothing in the template references `Interchange.FeatureFlags`.

### Composition with #145 and #146

`import_asset.py` also carries #145's multi_part, build-scale, and rename steps (merged before this fix) and #146's static LOD-group mapping (`_expected_mesh_candidates`, `check_lod_counts`, static `lod_count`). This fix composes with them and does not replace them:

- **Change only where meshes are found.** Folder resolution replaces only the step that gets the imported mesh list from the task (`_imported_assets` and `_check_expected`, or whatever #145 named them). Every step #145 runs on the imported meshes before material binding (multi_part handling, build scale, renames) runs unchanged on the resolved list.
- **Resolve after renames.** If a #145 rename step changes asset names in the destination folder, resolution runs after it, so it finds the final names.
- **Take candidate names from #146.** Resolution reads `PARAMS["expected_meshes"]` exactly as `_expected_mesh_candidates` builds it, including #146's `_LOD0`→`SM_<Name>` candidates. It never rebuilds candidate names itself.
- **Leave the host-side checks alone.** `check_lod_counts`, static `lod_count`, `check_pivots`, and `import_variant` ordering are not altered.

### Fake `unreal` module (tests)

`tests/unit/fake_unreal.py` is the shared in-memory `unreal` stand-in that #145 introduces for executing `build_import_code`. This fix reuses and extends it; it creates the file only when it is not on the default branch at implementation time. It must provide a module object, installed as `sys.modules["unreal"]` in a pytest fixture, with:

- `AssetImportTask`, `FbxImportUI` (with `static_mesh_import_data`), `FBXImportType`, and `TextureCompressionSettings`;
- `AssetToolsHelpers.get_asset_tools()`, returning tools with `import_asset_tasks`, which runs a per-test **scenario** callback that creates assets in an in-memory `EditorAssetLibrary` and sets `imported_object_paths`, and `create_asset`;
- `EditorAssetLibrary` (`does_asset_exist`, `load_asset`, `save_loaded_asset`, `rename_asset`);
- `StaticMesh` (`get_bounding_box`, `static_materials`, `set_material`) and `SkeletalMesh` (`get_bounds`, editor properties `materials` and `physics_asset`);
- `MaterialInstanceConstant`, `MaterialInstanceConstantFactoryNew`, and `MaterialEditingLibrary`;
- `get_editor_subsystem`, returning a `SkeletalMeshEditorSubsystem` with `import_lod` and `create_physics_asset`.

A helper `run_import_code(code)` `exec`s the generated code and returns the parsed `NMG_RESULT`, using `parse_nmg_result` on the captured stdout. The fake scenarios cover:

- under-reporting: only the first path is listed;
- missing parts;
- no physics asset created;
- no skeleton;
- re-import with changed bounds.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `src/nmg_game_dev/unreal/import_asset.py` | `_resolve_expected`, `_ensure_rig_assets`; static and skeletal paths use them; module docstring updated | AC1–AC6, AC8, FR1–FR5, FR7 |
| `tests/unit/fake_unreal.py` | Extend #145's shared fake (create only if absent) with the scenarios below | FR8 |
| `tests/unit/test_unreal_import.py` | Executed-code tests | AC1–AC9 |

## Blast Radius

- The fix composes with #145's multi_part, build-scale, and rename steps and #146's LOD-group mapping, as described under Composition with #145 and #146. #145's and #146's tests keep passing.
- Only the UE-side template changes. `build_import_code`, `parse_nmg_result`, `check_pivots`, and `import_variant` keep their signatures. `src/nmg_game_dev/pipeline/engine.py` is untouched.
- Other assets in the destination folder are never bound or reported, because only expected names are resolved.
- The #146 change to `_expected_mesh_candidates` feeds the same `PARAMS["expected_meshes"]` and needs no extra code here.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Resolve every expected mesh from the folder (ghost1's `does_asset_exist` lookup, applied to all parts) | Selected | Proven in ghost1; independent of what the task reports; picks up re-imported assets |
| Append folder lookups to the task list (ghost1 patch as written) | Rejected | Keeps a dependency on a list known to be wrong |
| `Interchange.FeatureFlags.Import.FBX=0` | Rejected | Does not fix static imports; legacy importer brings skeletal meshes in at 1/100 |
| Poll for an asynchronous import | Rejected | The parts already exist when `import_asset_tasks` returns |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #141 | 2026-11-11 | Initial defect design |
