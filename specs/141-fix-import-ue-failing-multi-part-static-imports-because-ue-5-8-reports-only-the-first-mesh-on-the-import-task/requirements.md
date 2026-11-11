# Defect Report: import_ue fails multi-part static imports because UE 5.8 reports only the first mesh on the import task

**Issue**: #141
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/102-preserve-the-rig-when-finalizing-a-character-rigged-with-rig-humanoid/

## Reproduction

1. In a UE 5.8 project onboarded with nmg-game-dev, finalize a static asset with two or more mesh parts (`SM_<Name>_<Part>`), so `import_ue` runs.
2. `import_ue` fails with `import_ue.failed`: `no static mesh for snapshot part: SM_<Name>_<Part>`, although every part's Static Mesh is in the destination folder. On UE 5.8, an FBX imported with `combine_meshes = False` lists only the first mesh in `AssetImportTask.imported_object_paths`. This happens with Interchange FBX import on or off.
3. Finalize a rigged character (its snapshot holds `SK_<Name>`). The Desktop import reports `ok`, and the Mobile import then fails with `asset not found: /Game/<Category>/<Name>/Desktop/SM_<Name>_PhysicsAsset`.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | `import_ue` resolves every expected mesh by name in the destination folder and returns one mesh per snapshot part. A rigged Desktop import returns `ok` only once `SM_<Name>_Skeleton` and `SM_<Name>_PhysicsAsset` exist, creating the physics asset when the import did not. |
| **Actual** | `import_ue` trusts `task.imported_object_paths`, fails every multi-part static import, and reports a rigged Desktop import as `ok` without a physics asset. |

## Acceptance Criteria

### AC1: Multi-part static import returns every part

**Given** a static asset whose snapshot lists two or more `MESH` parts for the variant, and an import that creates each part's Static Mesh in the destination folder
**When** the generated import code runs
**Then** `NMG_RESULT` is `ok` with one `static_meshes` entry per snapshot part
**And** no `no static mesh for snapshot part` failure occurs

### AC2: Expected meshes are resolved from the destination folder

**Given** an FBX import after which `task.imported_object_paths` lists only the first imported mesh
**When** the import code continues
**Then** it resolves each expected mesh by trying each name in its candidate list (`PARAMS["expected_meshes"]`) as `<dest>/<name>` with `EditorAssetLibrary.does_asset_exist` and `load_asset`, accepting only an asset of the expected class (Static Mesh, or Skeletal Mesh for a rigged asset)
**And** it binds materials and reports bounds only for those resolved meshes, ignoring other assets in the folder

### AC3: Rigged Desktop import guarantees the skeleton and physics asset

**Given** a rigged character whose Desktop import created `SM_<Name>` and `SM_<Name>_Skeleton` but no `SM_<Name>_PhysicsAsset`
**When** the Desktop import code runs
**Then** it creates the physics asset with `SkeletalMeshEditorSubsystem.create_physics_asset` for the Skeletal Mesh, makes sure it is at `<dest>/SM_<Name>_PhysicsAsset`, assigns it to the mesh's `physics_asset`, and saves both
**And** `NMG_RESULT` is `ok` only when `SM_<Name>_Skeleton` and `SM_<Name>_PhysicsAsset` both exist in the Desktop folder
**And** a missing skeleton fails the import with `import_ue.failed` naming the skeleton path

### AC4: Rigged Mobile import reuses the Desktop skeleton and physics asset

**Given** a rigged character whose Desktop folder holds `SM_<Name>_Skeleton` and `SM_<Name>_PhysicsAsset`
**When** the Mobile import code runs
**Then** it succeeds with the Desktop skeleton and physics asset set on the import options, and LOD 1 and LOD 2 are imported from `SM_<Name>_LOD1.fbx` and `SM_<Name>_LOD2.fbx`
**And** no `asset not found: .../Desktop/SM_<Name>_PhysicsAsset` error occurs

### AC5: A re-import reports the new geometry

**Given** a destination folder that already holds the variant's meshes from an earlier import
**When** the import replaces them with meshes of different bounds
**Then** the reported bounds are those of the newly imported meshes
**And** `check_pivots` passes against the new snapshot

### AC6: A missing part fails with every missing asset named

**Given** an import after which two expected meshes are absent from the destination folder
**When** the import code evaluates the result
**Then** `NMG_RESULT` reports an error, and `import_variant` raises `import_ue.failed`
**And** the message lists every missing expected mesh, not only the first

### AC7: Regression test with a two-part fixture

**Given** a unit test with a two-part static asset whose fake import task reports only the first mesh in `imported_object_paths`, while both `SM_<Name>_<Part>` assets exist in the destination folder
**When** the generated import code runs against the fake `unreal` module
**Then** the result is `ok` with both parts in `static_meshes`

### AC8: Existing import behavior is preserved

**Given** a single-part static asset
**When** the generated import code runs against the fake `unreal` module
**Then** texture settings, `MI_<Name>_<Part>` creation and binding, the `NMG_RESULT` schema, and the 0.01 cm pivot check behave as before

### AC9: The Interchange cvar is not offered as a workaround

**Given** the code, skills, docs, scripts, and consumer templates in this repository
**When** the fix lands
**Then** no file under `src/`, `skills/`, `docs/`, `scripts/`, or `templates/` contains `Interchange.FeatureFlags.Import.FBX`
**And** the generated import code neither reads nor sets it

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | The import code does not rely on `task.imported_object_paths` or `task.get_objects()` to list every imported mesh; it resolves expected meshes by name from the destination folder | Must |
| FR2 | Only the meshes named by `PARAMS["expected_meshes"]` are resolved, bound, and reported | Must |
| FR3 | A rigged Desktop import returns `ok` only when `SM_<Name>_Skeleton` and `SM_<Name>_PhysicsAsset` exist; a missing physics asset is created with `SkeletalMeshEditorSubsystem.create_physics_asset`, placed at `<dest>/SM_<Name>_PhysicsAsset`, assigned, and saved | Must |
| FR4 | On a re-import, the reported meshes and bounds are those of the new import | Must |
| FR5 | When expected meshes are missing, the step fails with `import_ue.failed` and the message lists all of them | Must |
| FR6 | No repository code, skill, doc, script, or template reads, sets, or recommends `Interchange.FeatureFlags.Import.FBX` | Must |
| FR7 | The `NMG_RESULT` schema, error codes, texture import, material binding, Mobile LOD import, and pivot check are unchanged | Must |
| FR8 | Unit tests execute the generated code against an in-memory fake `unreal` module covering the under-reporting task with a two-part fixture, folder resolution, the physics-asset fallback, the missing-skeleton failure, the missing-asset message, the re-import, and the single-part baseline | Must |

## Out of Scope

- Waiting or polling for an asynchronous import; the import is complete when `import_asset_tasks` returns
- Supporting the legacy FBX importer (`Interchange.FeatureFlags.Import.FBX=0`)
- Having `/onboard-consumer` write any Interchange cvar into a consumer project's engine config
- Texture import (`_import_textures`)
- Animation clip import through finalize (#138)
- The static Mobile LOD group mapping (#146)

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #141 | 2026-11-11 | Initial defect report |
