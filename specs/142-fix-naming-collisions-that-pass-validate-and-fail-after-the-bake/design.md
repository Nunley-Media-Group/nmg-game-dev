# Root Cause Analysis: Naming collisions pass validate and fail after the bake

**Issue**: #142
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/67-bake-authored-materials-to-contract-compliant-uv-texture-sets/

## Root Cause

**Image collision.** `bake_core/rewire.py` `_image_node` loads each baked PNG with `bpy.data.images.load(path, check_existing=False)` and then sets `image.name = name`. When an image with that name is already in the file, Blender renames the new image to `name.001`. `retire()` keeps the authored materials alive with a fake user, so the authored images keep holding the contract names. `variants_core/textures.py` names each Mobile image `f"{source.name}_Mobile"`, which carries the suffix over. `contract_core/validate.py` `_image_findings` matches `T_<Name>_<Part>_(BC|N|ORM)` exactly, so the export gate reports `naming.texture`. The finalize validate step runs with `authored=True`, which drops texture rules, so nothing catches this before the bake.

**Mesh datablock mismatch.** `variants_core/export.py` renames objects, materials, and images for export, but not mesh datablocks. The FBX geometry therefore carries `obj.data.name`, which Unreal uses as the static mesh name. The contract snapshot and `import_asset._expected_mesh_candidates` are keyed by object name, so the names disagree. No validate rule looks at `obj.data`, so a datablock shared by two parts, which cannot take both names, is never reported.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `plugins/nmg-game-dev-blender-addon/bake_core/rewire.py` | `_image_node` | Names output images; collides with authored images |
| `plugins/nmg-game-dev-blender-addon/variants_core/export.py` | `export_variants`, `_rename` | Renames objects, materials, and images, but not meshes |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | `_structure_findings` / `validate_asset` | No shared-mesh-data rule |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | `RULES` | Remediation catalogue |

## Fix Strategy

1. **Free the output name before loading** (`rewire.py`):
   - Add `_free_contract_name(name)`. When `bpy.data.images.get(name)` exists, it renames that image to the first of `f"{name}_Src"`, `f"{name}_Src2"`, … that no image holds.
   - `_image_node` calls it before `bpy.data.images.load(...)`, then sets `image.name = name`. The new image now takes the exact name.
   - The renamed image keeps its pixels, its packed or file data, and its users, including the retired `_Authoring` material.
   - The bake has already rendered from the sources and written the PNGs before `build_material` runs (`bake_core/core.py`), so the source pixels are read before any rename.
   - On a re-bake, the previous outputs are renamed to `_Src…` the same way, so no `.001` contract image is ever created.
2. **Name meshes after objects at export** (`export.py`):
   - Add `_name_meshes(objects, target)`. For each exported `MESH` object it computes the desired mesh name: `target(obj.name)`, where the object already holds its export name at that point. If another mesh holds that name, the holder is moved to `_to_temp(holder.name)`. Then `obj.data.name` is set to the desired name.
   - It returns `(datablock, original_name)` pairs, which are appended to the existing `restores` list.
   - It is called after the Desktop objects are selected (identity naming) and again after the Mobile objects are renamed by `_unsuffixed`. Desktop meshes are renamed to temp alongside the Desktop objects first, so Mobile meshes can take the shared names. This includes the rigged Mobile LOD jobs and the static LOD group.
   - The existing `finally` restores every name in reverse order, so the session's names are unchanged after export.
3. **Validate shared mesh data** (`validate.py`, `report.py`):
   - Add `_shared_mesh_findings(variant, objects)`. It groups the variant's `MESH` objects by `obj.data.as_pointer()`, and for each group of two or more it emits `finding("naming.mesh_data", mesh.name, "<mesh> is shared by <obj1>, <obj2>; each part needs its own mesh data.")`.
   - It is called per variant in `validate_asset`. `naming.mesh_data` is not in `_EXPORT_ONLY_RULES`, so the `authored=True` run reports it.
   - `RULES["naming.mesh_data"]` reads: "Give each part its own mesh data: select the parts and run Object > Relations > Make Single User > Object & Data (contract section 1)."
4. **Docs**: `docs/asset-contract.md` section 1 says that parts must not share mesh data and that export names each mesh after its object.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `plugins/nmg-game-dev-blender-addon/bake_core/rewire.py` | `_free_contract_name`; call in `_image_node` | AC1–AC3, FR1–FR3 |
| `plugins/nmg-game-dev-blender-addon/variants_core/export.py` | `_name_meshes`; restore through `restores` | AC4, FR4 |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | `_shared_mesh_findings` | AC5, FR5 |
| `plugins/nmg-game-dev-blender-addon/contract_core/report.py` | `RULES["naming.mesh_data"]` | AC5, FR5 |
| `docs/asset-contract.md` | Section 1 note | FR7 |
| `tests/blender/test_bake_unique.py`, `tests/blender/test_variants.py`, `tests/blender/test_contract_validate.py` | Regression tests | FR6 |

## Blast Radius

- `_image_node` is used only by `build_material`, which runs only in the bake. Assets with no colliding images take the same path as before (AC6).
- Export changes only temporary names during the FBX write. Session names are restored. FBX files whose mesh datablocks already matched their objects are unchanged.
- The new validate rule fires only on shared datablocks. The variants step builds each Mobile LOD from its own mesh, so existing fixtures produce no new findings.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Rename colliding source images to `_Src` (ghost1's approach, done inside the bake) | Selected | Keeps authored pixels and users; gives exact output names; proven in ghost1 |
| Replace the source image's pixels in place | Rejected | Would destroy the `_Authoring` material's source |
| Rename meshes at export and restore after (ghost1's `o.data.name = o.name`, holder moved aside) | Selected | Fixes the FBX name without mutating the session |
| Permanently rename meshes during validate | Rejected | Validate must not mutate the scene |
| Fuzzy-match `_001` in `import_ue` | Rejected | Out of scope; hides the mismatch |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #142 | 2026-11-11 | Initial defect design |
