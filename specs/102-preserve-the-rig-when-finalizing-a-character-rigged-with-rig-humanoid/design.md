# Root Cause Analysis: Finalize drops the rig of a character rigged with rig_humanoid

**Issue**: #102
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/32-support-humanoid-rigging-and-animation-import/

## Root Cause

The variants pipeline and the UE import were written for static props only:

1. `variants_core/cleanup.py` `_apply_modifiers()` evaluates the mesh with every modifier, clears `obj.modifiers`, and swaps in the evaluated mesh. That applies and removes the Armature modifier that `rig_core/rig.py` added, so the skin is lost before export.
2. `variants_core/mobile.py` `_copy_objects()` builds Mobile copies from `evaluated_mesh(src)`, which also bakes the current pose. The copies and their LODs are never given an Armature modifier or parent, so they keep vertex groups but have no skin.
3. `variants_core/export.py` `_FBX_OPTIONS` lacks the rig options that `rig_core/export.py` uses: `add_leaf_bones=False`, `use_armature_deform_only=True`, the bone axes, and the armature renamed to `Armature`. Mobile is always one FBX whose LodGroup Empty parents the LODs, which a skinned mesh parented to its armature cannot use.
4. `src/nmg_game_dev/unreal/import_asset.py` always sets `import_as_skeletal = False`, keeps only `unreal.StaticMesh` results, binds materials through `static_materials`, and expects every snapshot mesh, including `SM_<Name>_LOD0`, to come back as a static mesh.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py` | `_apply_modifiers` | Applies the Armature modifier |
| `plugins/nmg-game-dev-blender-addon/variants_core/mobile.py` | `build_mobile`, `_copy_objects`, `_build_lod_group` | Unskinned, posed Mobile copies; LodGroup only |
| `plugins/nmg-game-dev-blender-addon/variants_core/export.py` | `_FBX_OPTIONS`, `export_variants` | No rig options; single Mobile FBX |
| `plugins/nmg-game-dev-blender-addon/variants_core/assets.py` | asset lookup | No rig lookup |
| `plugins/nmg-game-dev-blender-addon/contract_core/reimport.py` | `reimport_check`, findings | Imports one FBX; no skin check |
| `src/nmg_game_dev/unreal/import_asset.py` | `_IMPORT_TEMPLATE`, `build_import_code`, `check_pivots`, `import_variant` | Static-only import |
| `src/nmg_game_dev/pipeline/engine.py` | `_run_import` | Imports variants with no shared skeleton |
| `src/nmg_game_dev/pipeline/steps.py` | `_STEP_VERSION` | Cache key for changed step outputs |
| `docs/asset-contract.md` | §5 Variants, §7 Rigged characters | Says the Mobile rig belongs to #33 |

## Fix Strategy

A collection is **rigged** when `bpy.data.objects["SK_<Name>"]` exists, has type `ARMATURE`, and is in collection `<Name>`. Add `variants_core/assets.py` `asset_armature(collection_name) -> bpy.types.Object | None` and use it everywhere below. Unrigged collections take today's code paths unchanged.

**Cleanup (FR1).** In `_apply_modifiers`, collect Armature modifiers whose `object` is `SK_<Name>`, set their `show_viewport` to False, evaluate, remove every other modifier, swap the mesh with `replace_mesh`, and restore `show_viewport`. The evaluated mesh keeps vertex groups, and `_clean_mesh` keeps the bmesh deform layer.

**Mobile (FR3).** When rigged, `_copy_objects` copies `src.data.copy()`, the rest mesh that cleanup already freed of non-Armature modifiers, instead of `evaluated_mesh(src)`. If `SM_<Name>` has no child parts, build the rigged chain instead of `_build_lod_group`: LOD0 = `fit_meshes` to the budget, named `SM_<Name>_Mobile`; LOD1 and LOD2 = `fit_meshes` of LOD0 to `lod0_tris // 2` and `// 4`, named `SM_<Name>_Mobile_LOD1` and `SM_<Name>_Mobile_LOD2`. All three live in `<Name>_Mobile` with no Empty. Each Mobile mesh is parented to `SK_<Name>` with an identity parent inverse and gets an Armature modifier named `Armature` with `object = SK_<Name>`. The report's `lod_levels` is 3 and `lod_tris` is the three counts. With child parts, Mobile stays LOD0-only as today, skinned the same way. The naming keeps the contract root `SM_<Name>_Mobile`. `_LOD_EXTRA` already leaves LOD1/LOD2 out of budget and pivot checks, and `export_name` maps them to `SM_<Name>`, `SM_<Name>_LOD1`, and `SM_<Name>_LOD2`.

**Export (FR2).** Add `_RIG_FBX_OPTIONS = {**_FBX_OPTIONS, "add_leaf_bones": False, "use_armature_deform_only": True, "primary_bone_axis": "Y", "secondary_bone_axis": "X", "bake_anim": False}`. When rigged, rename `SK_<Name>` to `Armature` for the export and restore it in `finally`. If another object already holds that name, raise `VariantError("variants.armature_name_taken", …)` before any file is written. Desktop exports `SM_<Name>.fbx` with the armature plus the Desktop meshes and `object_types={"ARMATURE", "MESH"}`. Mobile exports one file per LOD with the existing Mobile-suffix rename: `SM_<Name>.fbx` holds the armature and LOD0 plus any child parts, and `SM_<Name>_LOD1.fbx` and `SM_<Name>_LOD2.fbx` each hold the armature and that LOD. PNG export is unchanged. `nmg-variants.json` gains `"rigged": true|false`, and when rigged, `mobile.lod_files` lists the three FBX names.

**Re-import (FR5).** In `reimport_check`, when the folder holds `SM_<Name>_LOD1.fbx` or `SM_<Name>_LOD2.fbx`, import them after `SM_<Name>.fbx`. When the pre-report snapshot has an `ARMATURE` entry `SK_<Name>`, every expected mesh must come back with an Armature modifier, or a parent of type `ARMATURE`, and at least one vertex group. Otherwise add finding `reimport.skin_missing` naming the mesh. Name, triangle, dimension, and texture findings work as today. Imported armatures are ignored in name findings.

**UE import (FR4).** `build_import_code` gains `rigged` (the report snapshot has an `ARMATURE` entry `SK_<Name>`) and `skeleton_dest` (the Desktop destination) in `PARAMS`. When rigged:
- Desktop: `options.import_as_skeletal = True`, `options.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH`, `options.import_animations = False`, `options.create_physics_asset = True`, materials and textures off. Keep the imported `unreal.SkeletalMesh` `SM_<Name>`.
- Mobile: the same, but with `options.skeleton` = `<skeleton_dest>/SM_<Name>_Skeleton`, `options.physics_asset` = `<skeleton_dest>/SM_<Name>_PhysicsAsset`, and `create_physics_asset = False`. Then, for each `SM_<Name>_LOD{1,2}.fbx` in order, call `unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem).import_lod(mesh, level, path)`. Raise when the returned index is not `level`.
- Materials bind through the skeletal mesh's `materials` array (`SkeletalMaterial.material_slot_name`, `material_interface`) with the same `M_<Name>_<Part>` → `MI_<Name>_<Part>` rule, then `set_editor_property("materials", …)` and save.
- `RESULT["skeletal_meshes"][name]` = `{"path", "bounds" (from get_bounds() origin ± box_extent), "lod_count", "skeleton", "physics_asset"}`.
- Expected-mesh candidates and `check_pivots` drop snapshot entries matching `_LOD[1-9]$` when rigged. They match the rest against `static_meshes` ∪ `skeletal_meshes`.

`import_variant` takes `skeleton_dest: str | None = None`. `engine._run_import` passes `ue_destination(request, "Desktop")`, and Desktop is imported first, as `VARIANTS` already orders it. Bump `_STEP_VERSION` to `"3"` so cached unrigged-era results are not reused.

**Docs.** In `docs/asset-contract.md`, §5 states the rigged Mobile layout (no LodGroup, three skinned LOD meshes), and §7 "Rigged characters" describes the Desktop and Mobile FBX files and the UE result. The "#33" sentence is replaced.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `variants_core/assets.py` | `asset_armature()` | AC1–AC4 |
| `variants_core/cleanup.py` | Keep the Armature modifier | AC3, FR1 |
| `variants_core/mobile.py` | Rest-mesh copies, rigged LOD chain, skinning | AC2, FR3 |
| `variants_core/export.py`, `variants_core/__init__.py`, `variants_core/sidecars.py` | Rig FBX options, per-LOD Mobile files, `rigged`/`lod_files` | AC1, AC2, FR2 |
| `contract_core/reimport.py` | LOD files, `reimport.skin_missing` | AC5, FR5 |
| `src/nmg_game_dev/unreal/import_asset.py` | Skeletal import path | AC1, AC2, FR4 |
| `src/nmg_game_dev/pipeline/engine.py`, `steps.py` | `skeleton_dest`, step version | AC2, FR4 |
| `docs/asset-contract.md` | §5, §7 | FR5 |

## Blast Radius

Every unrigged collection goes through the same branches as before, so static props, environment pieces, and child-part assets keep their output byte for byte. The only exception is the new `"rigged": false` key in `nmg-variants.json`. The `_STEP_VERSION` bump invalidates every cached finalize step once. `rig_core/export.py` is untouched.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| One FBX per Mobile LOD plus `import_lod` | Selected | Explicit, testable files; skinned meshes stay parented to the armature |
| One Mobile FBX with a LodGroup of skinned meshes | Rejected | A skinned mesh cannot sit under both the LodGroup Empty and its armature |
| Regenerate Mobile LODs inside UE | Rejected | Bypasses Blender decimation, the Mobile budget, and the re-import check |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #102 | 2026-10-31 | Initial defect report |
