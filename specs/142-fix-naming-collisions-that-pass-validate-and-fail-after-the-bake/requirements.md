# Defect Report: Naming collisions pass validate and fail after the bake

**Issue**: #142
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/67-bake-authored-materials-to-contract-compliant-uv-texture-sets/

## Reproduction

**Image collision**

1. In Blender, author a collection `<Name>` with a part whose material samples images named `T_<Name>_<Part>_BC`, `T_<Name>_<Part>_N`, and `T_<Name>_<Part>_ORM`.
2. Run finalize. Validate passes and the bake runs to completion.
3. The export pre-check fails `naming.texture` on `T_<Name>_<Part>_BC.001` (and `_N.001`, `_ORM.001`) and on their `_Mobile` copies.

**Mesh datablock mismatch**

1. In Blender, author a collection `<Name>` with a part object `SM_<Name>_Seat` whose mesh datablock is named `SM_<Name>_Seat.001`.
2. Run finalize. Validate, bake, and export pass.
3. The FBX carries the mesh as `SM_<Name>_Seat.001`, and `import_ue` fails with `no static mesh for snapshot part: SM_<Name>_Seat`.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | The bake writes its outputs under the exact contract names, even when the source material already uses images with those names. The exported FBX names every mesh after its object's export name. A mesh datablock shared by two parts of one variant is reported by validate before the bake. |
| **Actual** | Validate passes and the bake runs. The run then fails at the export pre-check (`naming.texture` on `.001` images) or at `import_ue` (`no static mesh for snapshot part`). |

## Acceptance Criteria

### AC1: Bake outputs take the contract names when source images already hold them

**Given** a collection whose authored material samples images named `T_<Name>_<Part>_BC`, `_N`, and `_ORM`
**When** the finalize bake step runs
**Then** the baked material's images are named exactly `T_<Name>_<Part>_BC`, `_N`, and `_ORM`, with no `.001` suffix
**And** the export pre-check reports no `naming.texture` finding for those images or their `_Mobile` copies

### AC2: Authored materials keep their source images

**Given** the same collection
**When** the bake has replaced the materials
**Then** each retired `<name>_Authoring` material still samples the same image datablocks, with the same pixels, it was authored with
**And** each of those images is named `<contract name>_Src` (or `_Src2`, `_Src3`, … when that name is taken), which does not match a contract output name

### AC3: Re-running the bake does not accumulate suffixed images

**Given** an asset that was already baked, so images with the contract names exist in the file
**When** the bake step runs again
**Then** the outputs carry the exact contract names
**And** no image whose name is a contract name followed by `.NNN` is left in the file

### AC4: Export names mesh datablocks after their objects

**Given** a part object `SM_<Name>_Seat` whose mesh datablock is named `SM_<Name>_Seat.001`
**When** the finalize export step writes the Desktop and Mobile FBX files
**Then** each mesh in each FBX is named after its object's export name (the Mobile suffix removed, as for objects), including the Mobile LOD meshes
**And** re-importing each FBX shows every mesh datablock named the same as its object
**And** after export, the session's objects and mesh datablocks have the names they had before

### AC5: A mesh datablock shared between parts is a validate finding

**Given** two mesh objects of the same variant that share one mesh datablock
**When** the finalize validate step runs before the bake (`authored=True`) or the full contract runs
**Then** it reports a `naming.mesh_data` finding that targets the datablock and names both objects
**And** the remediation text tells the author to make the mesh data single-user (Object > Relations > Make Single User > Object & Data) so each part has its own datablock

### AC6: Existing behavior is preserved

**Given** an asset with neither collision
**When** validate, bake, and export run
**Then** they produce the same findings, image names, material names, and FBX file names as before this fix

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | The bake step produces images named exactly `T_<Name>_<Part>_BC`, `_N`, and `_ORM` when images with those names already exist | Must |
| FR2 | Before creating an output image, the bake renames any existing image holding the output name to the first free name of `<name>_Src`, `<name>_Src2`, …; the source pixels were already baked to PNG, and the renamed image keeps its data and users | Must |
| FR3 | A repeated bake leaves no `<contract name>.NNN` image in the file | Must |
| FR4 | The export step writes each exported mesh datablock under its object's export name for both variants, including Mobile LOD meshes and rigged Mobile LOD files; any other mesh holding that name is moved to a temporary name first; all names are restored after export, including on failure | Must |
| FR5 | The validate step, including the `authored=True` run, reports `naming.mesh_data` for a mesh datablock used by two or more mesh objects of one variant, with remediation text in `contract_core/report.py` `RULES` | Must |
| FR6 | Blender headless tests cover the same-named source image bake, the repeated bake, the mismatched datablock export, and the shared-datablock finding | Must |
| FR7 | `docs/asset-contract.md` states that mesh datablocks are exported under their object names and that parts must not share mesh data | Should |

## Out of Scope

- Validate findings for same-named source images or for a mismatched single-user mesh datablock; both are corrected automatically
- Automatically making a shared mesh datablock single-user
- Changing the texture naming contract or the `naming.texture` rule
- Renaming or name checks for other datablock types (armatures, actions, materials beyond what the bake already does)
- Fuzzy matching of Unreal asset names in `import_ue`
- Deleting stale `_001` assets already imported into an Unreal project
- `import_ue` reading Interchange import results too early (#141)

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #142 | 2026-11-11 | Initial defect report |
