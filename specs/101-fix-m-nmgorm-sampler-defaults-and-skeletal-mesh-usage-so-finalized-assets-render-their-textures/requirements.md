# Defect Report: M_NmgORM sampler defaults and skeletal-mesh usage

**Issue**: #101
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt/

## Reproduction

1. Build `M_NmgORM` with `scripts/unreal/build_master_material.py` in a UE 5.8 editor on macOS.
2. Finalize any asset so `import_ue` creates `MI_<Name>_<Part>` parented to `/nmg-game-dev/Materials/M_NmgORM`.
3. Place the imported mesh in a level and read the editor Output Log.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | `M_NmgORM` and its instances compile with no sampler errors, the mesh shows its baked `T_<Name>_<Part>_{BC,N,ORM}` textures, and instances also render on skeletal meshes. |
| **Actual** | The `Normal` and `ORM` samplers default to `/Engine/EngineResources/DefaultTexture`, a Color texture. The editor reports `Sampler type is Normal, should be Color` and `Sampler type is Masks, should be Color`, then `Failed to compile Material ... for platform SF_METAL_SM5, Default Material will be used in game`, so the asset renders flat gray. The material also lacks skeletal-mesh usage. |

## Acceptance Criteria

### AC1: Master material compiles

**Given** `M_NmgORM` built by `scripts/unreal/build_master_material.py`
**When** the material is compiled in the UE 5.8 editor
**Then** it compiles with no sampler-type errors, the `Normal` parameter defaults to `/Engine/EngineMaterials/DefaultNormal`, and the `ORM` parameter defaults to `/Engine/EngineMaterials/DefaultDiffuse_TC_Masks`

### AC2: Instances render baked textures on static and skeletal meshes

**Given** an `MI_<Name>_<Part>` parented to `M_NmgORM` with the `BaseColor`, `Normal`, and `ORM` parameters set
**When** it is assigned to a static mesh and to a skeletal mesh
**Then** neither reports a compile failure or falls back to the Default Material, and `M_NmgORM` has `used_with_skeletal_mesh` enabled

### AC3: Rebuild keeps instances and parameter names

**Given** an existing `M_NmgORM` with instances
**When** `build_master_material.py` runs again
**Then** it rebuilds the existing asset in place, so instances keep their parent, and the `BaseColor`, `Normal`, and `ORM` parameter names and channel wiring (BaseColor RGB → Base Color, Normal RGB → Normal, ORM R → Ambient Occlusion, G → Roughness, B → Metallic) are unchanged

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | The builder sets an explicit default texture on every sampler parameter whose type matches the sampler: `BaseColor` → `/Engine/EngineResources/DefaultTexture` (Color), `Normal` → `/Engine/EngineMaterials/DefaultNormal` (Normal), `ORM` → `/Engine/EngineMaterials/DefaultDiffuse_TC_Masks` (Masks). It fails with an error naming the path when a default texture does not load | Must |
| FR2 | The builder enables `used_with_skeletal_mesh` on `M_NmgORM` before it recompiles and saves | Must |
| FR3 | The shipped `plugins/nmg-game-dev-ue-plugin/Content/Materials/M_NmgORM.uasset` is rebuilt with these settings | Must |

## Out of Scope

- Changing the ORM channel layout or adding material parameters
- Material usage flags other than skeletal mesh
- Changes to `src/nmg_game_dev/unreal/import_asset.py` material-instance creation

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #101 | 2026-10-31 | Initial defect report |
