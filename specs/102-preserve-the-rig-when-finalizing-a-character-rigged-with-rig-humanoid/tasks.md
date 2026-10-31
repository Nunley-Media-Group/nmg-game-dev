# Tasks: Finalize drops the rig of a character rigged with rig_humanoid

**Issue**: #102
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/32-support-humanoid-rigging-and-animation-import/

## Implementation Tasks

### T001: Keep the skin through cleanup and build skinned Mobile LODs

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/assets.py`, `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py`, `plugins/nmg-game-dev-blender-addon/variants_core/mobile.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `asset_armature(name)` returns `SK_<Name>` when it is an `ARMATURE` in collection `<Name>`, else `None`.
- Cleanup applies every modifier except Armature modifiers targeting `SK_<Name>`, which remain together with the vertex groups (AC3, FR1).
- For a rigged `SM_<Name>` without child parts, `<Name>_Mobile` holds `SM_<Name>_Mobile`, `SM_<Name>_Mobile_LOD1`, and `SM_<Name>_Mobile_LOD2`, built from the rest mesh. LOD0 is within the Mobile budget, and LOD1 and LOD2 are at most 50% and 25% of LOD0's triangles. Each is parented to `SK_<Name>`, has an Armature modifier on `SK_<Name>`, and keeps the 26 deform vertex groups (AC2, FR3).
- Unrigged collections produce the same Mobile objects as before (AC4).

### T002: Export skinned Desktop and per-LOD Mobile FBX

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/export.py`, `plugins/nmg-game-dev-blender-addon/variants_core/__init__.py`, `plugins/nmg-game-dev-blender-addon/variants_core/sidecars.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- Rigged Desktop `SM_<Name>.fbx` and each rigged Mobile file are exported with the armature renamed `Armature`, `add_leaf_bones=False`, `use_armature_deform_only=True`, primary bone axis Y, secondary X, and `bake_anim=False`. `SK_<Name>` gets its name back afterwards, even on failure (AC1, FR2).
- Rigged Mobile writes `SM_<Name>.fbx` (LOD0), `SM_<Name>_LOD1.fbx`, and `SM_<Name>_LOD2.fbx`, each holding the armature and one skinned mesh (AC2).
- An existing object named `Armature` other than `SK_<Name>` raises `variants.armature_name_taken` before any file is written.
- `nmg-variants.json` records `rigged`, and when rigged, `mobile.lod_files` lists the three files. Unrigged output is otherwise unchanged (AC4).

### T003: Re-import check for rigged variants

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/reimport.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- The check imports `SM_<Name>_LOD1.fbx` and `SM_<Name>_LOD2.fbx` after `SM_<Name>.fbx` when they exist, and the rigged Mobile variant passes name, triangle, and dimension checks (AC5).
- When the pre-report has `SK_<Name>`, an expected mesh with no armature deform or no vertex groups yields `reimport.skin_missing` (AC5, FR5).
- Unrigged re-import findings are unchanged (AC4).

### T004: Import rigged variants into UE as Skeletal Meshes

**File(s)**: `src/nmg_game_dev/unreal/import_asset.py`, `src/nmg_game_dev/pipeline/engine.py`, `src/nmg_game_dev/pipeline/steps.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- `build_import_code` sets `rigged` from the report snapshot and `skeleton_dest` from `import_variant(..., skeleton_dest=...)`. The engine passes the Desktop destination for both variants and imports Desktop first.
- Rigged Desktop code imports skeletal with `create_physics_asset = True` and `import_animations = False`. Rigged Mobile code sets `skeleton` and `physics_asset` to the Desktop `SM_<Name>_Skeleton` and `SM_<Name>_PhysicsAsset`, and imports LOD1 and LOD2 with `SkeletalMeshEditorSubsystem.import_lod` (AC1, AC2, FR4).
- Skeletal material slots named `M_<Name>_<Part>` get `MI_<Name>_<Part>` with `BaseColor`, `Normal`, and `ORM` set. `RESULT["skeletal_meshes"]` carries path, bounds, lod_count, skeleton, and physics_asset. `check_pivots` matches rigged roots against `skeletal_meshes` and skips rigged `_LOD[1-9]` entries (AC1, AC2).
- Unrigged code keeps `import_as_skeletal = False` and today's static path (AC4).
- `_STEP_VERSION` is `"3"`.

### T005: Document the rigged variant layout

**File(s)**: `docs/asset-contract.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T002, T004
**Acceptance**:
- §5 Variants states the rigged Mobile layout (three skinned LOD meshes, one FBX per LOD, no LodGroup), and §7 "Rigged characters" describes the rigged Desktop and Mobile FBX files and the Skeletal Mesh, skeleton, and physics asset UE creates. The sentence deferring the Mobile rig to #33 is gone (FR5).
- `CHANGELOG.md` `[Unreleased]` has a Fixed bullet for rigged finalize that ends with `(#102)`.

### T006: Regression coverage

**File(s)**: `tests/blender/test_variants_rigged.py`, `tests/blender/test_contract_reimport.py`, `tests/unit/test_unreal_import.py`, `tests/bdd/features/rigged_finalize.feature`, `tests/bdd/test_rigged_finalize_bdd.py`
**Type**: Create
**Depends**: T001, T002, T003, T004
**Acceptance**:
- `tests/blender/test_variants_rigged.py` uses `tests/blender/rig_fixtures.py` to rig a hero. It asserts AC3 (a non-Armature modifier applied, the Armature modifier and vertex groups kept). It asserts AC1 and AC2 by re-importing each exported FBX into a fresh scene: an `Armature` with 26 bones, meshes with an Armature modifier and vertex groups, three Mobile files, and LOD ratios within budget. The pass and failure paths of `scripts/run-blender-tests.sh` cover it.
- `tests/blender/test_contract_reimport.py` covers AC5: a rigged Mobile folder passes, and a mesh exported without skin yields `reimport.skin_missing`.
- `tests/unit/test_unreal_import.py` covers FR4 and AC1/AC2 on the generated code and a fake client. It checks the rigged Desktop and Mobile options, `import_lod` for LOD1/LOD2, the skeleton and physics asset paths, skeletal material binding, `check_pivots` against `skeletal_meshes`, and `import_variant` with `skeleton_dest`. Unrigged reports still produce `import_as_skeletal = False` (AC4).
- `tests/bdd/features/rigged_finalize.feature` (SCN001–SCN005) is bound in `tests/bdd/test_rigged_finalize_bdd.py`. `pytest tests/unit tests/bdd` passes.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #102 | 2026-10-31 | Initial defect tasks |
