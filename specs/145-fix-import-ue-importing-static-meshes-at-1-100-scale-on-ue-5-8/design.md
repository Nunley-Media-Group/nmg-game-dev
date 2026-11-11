# Root Cause Analysis: import_ue imports static meshes at 1/100 scale on UE 5.8

**Issue**: #145
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt/

## Root Cause

`variants_core/export.py` writes every FBX with `apply_scale_options = "FBX_SCALE_UNITS"`: the file carries `UnitScaleFactor` 100 and vertices in metres. On UE 5.8, Interchange places that unit conversion on the scene node transform, not on the vertices. `_static_options` in `src/nmg_game_dev/unreal/import_asset.py` imports with `transform_vertex_to_absolute = False` and `bake_pivot_in_vertex = False`, so the node transform is never applied to the vertices, and each static mesh keeps its metre values as centimetres. `check_pivots` converts the Blender part's `local_bounds` to centimetres and compares within 0.01 cm, so every part is out by a factor of 100.

In the same mode UE names each static mesh after the FBX geometry (the Blender mesh datablock), not the node (the Blender object). `_check_expected` and `check_pivots` key on object names, so a part whose datablock is named `SM_<Name>_<Part>.001` is reported as missing.

Turning on `transform_vertex_to_absolute` fixes size and naming but bakes each part's translation into its vertices, losing part pivots on a multi-part asset. A build scale set through import options fixed size and pivots but left stale bounds after a reimport over an existing asset. Neither is acceptable alone for every asset.

The ghost1 consumer project already works around this in process (`/Volumes/Fast Brick/source/repos/ghost1/Tools/nmgpatch/sitecustomize.py`, patching `_IMPORT_TEMPLATE`): a single-part asset imports with `transform_vertex_to_absolute = True`, and a multi-part asset keeps it `False` and receives `build_scale3d = (100, 100, 100)` on every LOD through `StaticMeshEditorSubsystem.get_lod_build_settings` / `set_lod_build_settings`, then is saved. That workaround only writes the scale while it is still 1.0, so a mesh that already carries scale 100 is not rebuilt.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `src/nmg_game_dev/unreal/import_asset.py` | `_IMPORT_TEMPLATE`: `_static_options`, `_import_meshes`, `_check_expected`, `_bind_materials` | Static FBX import, expected-part check, and bounds report |
| `src/nmg_game_dev/unreal/import_asset.py` | `build_import_code`, `_expected_mesh_candidates` | Builds the UE-side `PARAMS` from the contract report snapshot |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | `object_snapshot` | Records each object in the snapshot; has no mesh datablock name today |
| `tests/unit/test_unreal_import.py` | static option assertions | Asserts option strings only; never runs the generated code |
| `tests/e2e/test_finalize_e2e.py` | single-part `crate.blend` fixture | Skips because no fixture exists |

## Fix Strategy

Adopt the ghost1 workaround as the framework fix, with one correction for reimports, inside the generated UE Python:

0. **Part count.** `build_import_code` computes `multi_part` for the variant: true when the snapshot's `MESH` parts of that variant, reduced to export names with any `_LOD<n>` suffix removed, name more than one base part (ghost1's `_multi_part`). It is passed in `PARAMS`.
1. **Single-part asset.** `_static_options` sets `transform_vertex_to_absolute = not PARAMS["multi_part"]`. A single-part asset's one object sits at the asset origin, so baking the node transform applies the unit conversion without moving a pivot, and UE names the mesh after the node (the object). `combine_meshes` and `bake_pivot_in_vertex` stay off.
2. **Multi-part asset: forced build scale.** After the static FBX import, for every imported `StaticMesh` and every LOD (`get_num_lods()`), read the build settings with `StaticMeshEditorSubsystem.get_lod_build_settings`, set `build_scale3d` to `unreal.Vector(100.0, 100.0, 100.0)` (`_CM_PER_METER`), and write them back with `set_lod_build_settings`; then save the asset with `EditorAssetLibrary.save_loaded_asset`. Unlike ghost1, the scale is written every time, not only while it is 1.0: the value is absolute so it never compounds, and the write always rebuilds the mesh, which recomputes bounds from the newly imported geometry, so a reimport over an earlier asset reports and saves the new bounds (AC4). Build scale scales about the mesh origin, so part pivots are unchanged (AC2).
3. **Multi-part asset: part naming from the snapshot.** `object_snapshot` records `"mesh": obj.data.name` for `MESH` objects (`None` otherwise). `build_import_code` passes a per-variant map `mesh_names` from the datablock name to the part's export name (snapshot key with `_Mobile` removed), excluding rigged LOD extras and any datablock shared by two or more parts of the variant. After the import, each imported static mesh whose asset name equals a mapped datablock name — compared after replacing every character outside `[A-Za-z0-9_]` with `_`, as UE does for asset names — and differs from the export name is renamed to `<dest>/<export name>` with `EditorAssetLibrary.rename_asset`. When an asset already exists at the export name (an earlier import), the new mesh replaces it first through `EditorAssetLibrary.consolidate_assets(new_mesh, [existing])`, so references to the old asset now point to the new one, and then takes the name. The renamed path is what the result, `_check_expected`, and `_bind_materials` use.
4. The skeletal path (`_import_skeletal`, `_skeletal_options`) runs none of these steps. The exporter is not changed, so the rigged FBX and its import stay as they are.

ghost1's other patches (looking up parts missing from `imported_object_paths`, and the Mobile LOD-group mapping) belong to #141 and are not part of this fix.

The order inside `_run` becomes: import textures → import meshes (options from step 1) → (static multi-part only) build scale and rename → `_check_expected` → `_bind_materials` → `ok`. Any failure still lands in `RESULT["error"]` and maps to `import_ue.failed`; `check_pivots`, `PIVOT_TOLERANCE_CM`, and the `NMG_RESULT` keys are unchanged.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | `object_snapshot` adds `"mesh"` (the mesh datablock name, or `None`) | AC3, FR3 |
| `src/nmg_game_dev/unreal/import_asset.py` | `build_import_code` adds `multi_part` and `mesh_names` to `PARAMS`; `_static_options` bakes the node transform only for a single-part asset; template adds `_apply_unit_scale` (forced per-LOD build scale ×100, rebuild, save) and `_rename_to_parts` (rename/consolidate) for a multi-part asset; module docstring describes these steps and cites the ghost1 workaround they replace | AC1–AC5, AC8, FR1–FR5, FR7 |
| `tests/unit/fake_unreal.py` | New in-memory `unreal` stand-in that models source bounds, per-LOD build scale, stale bounds until rebuild, datablock-named imports, rename, and consolidate | AC1–AC4, AC6, AC8, FR9 |
| `tests/unit/test_unreal_import.py` | Runs the generated code against the fake and asserts size, pivots, naming, reimport, untouched skeletal path, and preserved behavior | AC1–AC6, AC8, FR9 |
| `tests/bdd/features/import_ue_static_scale.feature`, `tests/bdd/steps/test_import_ue_static_scale.py` | pytest-bdd scenarios for AC1–AC6 and AC8 on the fake | AC1–AC6, AC8 |
| `tests/blender/test_finalize_core.py` | Asserts the snapshot `mesh` field | AC3 |
| `tests/e2e/fixtures/build_multipart_fixture.py`, `tests/e2e/test_finalize_e2e.py`, `tests/blender/test_e2e_fixture_builder.py` | Fixture builder (checked by a headless Blender test) and an opt-in `--runslow` multi-part e2e test | AC7, FR8 |

## Blast Radius

- Every non-rigged `import_ue` run: meshes are rebuilt once more after import and may be renamed. Existing assets at the export name are consolidated into the new import, so level references survive.
- The contract snapshot gains one key. `reimport.py` reads snapshot fields by name, so the extra key is ignored there. The `import_ue` cache key is computed from request settings, not the snapshot, so it is unaffected.
- Rigged imports and the exporter are untouched.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| ghost1 split: node transform baked for a single part; forced per-LOD build scale ×100 plus snapshot-driven rename for multi-part | Selected | Proven in the ghost1 consumer on UE 5.8; keeps pivots, fixes size; always writing the scale refreshes bounds on reimport |
| ghost1 workaround unchanged (scale written only while 1.0) | Rejected | A mesh already at scale 100 is not rebuilt, so a reimport can keep stale bounds (AC4) |
| `transform_vertex_to_absolute = True` for every asset | Rejected | Bakes part translation into vertices; multi-part pivots are lost |
| Build scale through import options only | Rejected | Bounds were stale after a reimport |
| `convert_scene_unit` / `import_uniform_scale` on `FbxImportUI` | Rejected | No effect under Interchange |
| Change the exporter's `apply_scale_options` | Rejected | Moves scale onto object transforms that Interchange still leaves on the node, and risks the rigged path (FR6) |
| Rename mesh datablocks at export | Rejected | Owned by #142 |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #145 | 2026-11-11 | Initial defect design |
