# Defect Report: Finalize drops the rig of a character rigged with rig_humanoid

**Issue**: #102
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/32-support-humanoid-rigging-and-animation-import/

## Reproduction

1. Author `SM_<Name>` in collection `<Name>` and run `rig_humanoid(<Name>, "humanoid", landmarks)`, so `SK_<Name>` skins it through an Armature modifier.
2. Run `finalize_asset` with `asset_class: character`.
3. Inspect `Desktop/SM_<Name>.fbx`, `/Game/<Category>/<Name>/Desktop/SM_<Name>`, and the Mobile import result.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | Desktop imports as a Skeletal Mesh with its skeleton and a physics asset. Mobile imports as a Skeletal Mesh with LOD0–LOD2 that reuses the Desktop skeleton and physics asset. Both use their own `MI_<Name>_<Part>`. |
| **Actual** | Variant cleanup applies and removes the Armature modifier, so `Desktop/SM_<Name>.fbx` holds bones but no skin, and UE imports `SM_<Name>` as a Static Mesh. The Mobile LODs are not skinned, and the Mobile import fails with `import_ue.failed: RuntimeError: no static mesh for snapshot part: SM_<Name>_LOD0`. |

## Acceptance Criteria

### AC1: Desktop rigged export and import

**Given** a `character` collection with `SK_<Name>` skinning `SM_<Name>` through an Armature modifier
**When** `finalize_asset` runs
**Then** `Desktop/SM_<Name>.fbx` contains an armature named `Armature` with the 26 deform bones and `SM_<Name>` skinned to it, and `/Game/<Category>/<Name>/Desktop/SM_<Name>` is a Skeletal Mesh with skeleton `SM_<Name>_Skeleton`, physics asset `SM_<Name>_PhysicsAsset`, and `MI_<Name>_<Part>` assigned to every slot

### AC2: Mobile rigged LODs

**Given** the same rigged collection
**When** `finalize_asset` runs
**Then** `Mobile/` holds `SM_<Name>.fbx`, `SM_<Name>_LOD1.fbx`, and `SM_<Name>_LOD2.fbx`, each with the armature and one mesh skinned to it, at LOD1 50% and LOD2 25% of LOD0's triangles. `/Game/<Category>/<Name>/Mobile/SM_<Name>` is a Skeletal Mesh with 3 LODs that uses the Desktop skeleton and physics asset and its own Mobile `MI_<Name>_<Part>`, and the job succeeds

### AC3: Cleanup keeps the skin

**Given** a rigged collection whose mesh also has non-Armature modifiers
**When** the variants cleanup runs
**Then** the non-Armature modifiers are applied, and the Armature modifier targeting `SK_<Name>` and the mesh's vertex groups remain

### AC4: Unrigged assets unchanged

**Given** a collection without `SK_<Name>`
**When** `finalize_asset` runs
**Then** Desktop and Mobile export and import as Static Meshes exactly as before, with the single-FBX Mobile LodGroup layout

### AC5: Re-import check covers rigged variants

**Given** exported rigged Desktop and Mobile variants
**When** the re-import check runs on each variant folder
**Then** it imports every LOD file of the rigged Mobile variant, compares names, triangles, and dimensions with the pre-export report, and reports `reimport.skin_missing` for an expected mesh that comes back without an armature deform and vertex groups

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Cleanup applies every modifier except an Armature modifier targeting `SK_<Name>`, and keeps vertex groups | Must |
| FR2 | When `SK_<Name>` exists, Desktop and Mobile export skinned FBX with the armature named `Armature`, `add_leaf_bones=False`, `use_armature_deform_only=True`, primary bone axis Y, secondary X, and no baked animation | Must |
| FR3 | Rigged Mobile LODs are built from the undeformed rest mesh, skinned to `SK_<Name>`, and written one FBX per LOD | Must |
| FR4 | `import_ue` imports rigged variants as Skeletal Meshes, creates one skeleton and physics asset on Desktop, reuses them for Mobile, imports Mobile LOD1 and LOD2 into the Mobile Skeletal Mesh, binds `MI_<Name>_<Part>` to skeletal material slots, and checks the root's pivot | Must |
| FR5 | The re-import check handles rigged variants (AC5), and `docs/asset-contract.md` §5 and §7 "Rigged characters" describe the rigged Desktop and Mobile layout | Should |

## Out of Scope

- Importing animation clips into Unreal
- Non-humanoid rigs
- A Mobile LOD chain for rigged characters with child parts (they keep the existing LOD0-only rule)

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #102 | 2026-10-31 | Initial defect report |
