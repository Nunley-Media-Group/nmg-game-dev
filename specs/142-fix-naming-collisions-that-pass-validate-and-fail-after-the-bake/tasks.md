# Tasks: Naming collisions pass validate and fail after the bake

**Issue**: #142
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/67-bake-authored-materials-to-contract-compliant-uv-texture-sets/

## Implementation Tasks

### T001: Free contract image names before the bake creates its outputs

**File(s)**: `plugins/nmg-game-dev-blender-addon/bake_core/rewire.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `_image_node` first renames any existing image that holds the output name to the first free `<name>_Src`, `<name>_Src2`, …. The loaded image then takes the exact name, `T_<Name>_<Part>_BC`, `_N`, or `_ORM` (AC1, FR1, FR2).
- The renamed image keeps its users and pixels (AC2).
- A repeated bake leaves no `<contract name>.NNN` image (AC3, FR3).
- With no colliding image, output names and materials are unchanged (AC6).

### T002: Export mesh datablocks under their objects' export names

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/export.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- Before each FBX write, every exported mesh object's datablock is named after the object's export name. Any other mesh holding that name is moved to a temporary name first. This covers the Desktop FBX, the static Mobile LOD group, and the rigged Mobile per-LOD files (AC4, FR4).
- All object, material, image, and mesh names are restored in the existing `finally`, including when an export raises (AC4).
- Assets whose mesh names already match produce the same FBX file names as before (AC6).

### T003: Report mesh data shared between parts

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/validate.py`, `plugins/nmg-game-dev-blender-addon/contract_core/report.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `validate_asset` emits `naming.mesh_data`, targeting the datablock and naming every object that shares it, for each variant. It does so with `authored=True` and with the full contract (AC5, FR5).
- `RULES["naming.mesh_data"]` holds the make-single-user remediation (AC5).
- Fixtures without shared data get no new finding (AC6).

### T004: Document the mesh-data rule

**File(s)**: `docs/asset-contract.md`
**Type**: Modify
**Depends**: T002, T003
**Acceptance**:
- Section 1 says each part must have its own mesh data and that export names each mesh after its object (FR7).

### T005: Blender headless regression tests

**File(s)**: `tests/blender/test_bake_unique.py`, `tests/blender/test_variants.py`, `tests/blender/test_contract_validate.py`, `tests/blender/bake_fixtures.py`
**Type**: Modify
**Depends**: T001, T002, T003
**Acceptance**:
- Bake: an asset whose authored material samples images named `T_<Name>_Body_BC`/`_N`/`_ORM` (built with `bake_fixtures.image_material`) bakes to images with exactly those names. The `_Authoring` material still references the original image datablocks, now named `…_Src`, with their pixels unchanged. `contract_core.validate.validate_asset(..., authored=False)` on the baked asset (after variants) reports no `naming.texture` finding (AC1, AC2).
- Bake run twice: the second run leaves exactly one image per contract name and none matching `^T_.*_(BC|N|ORM)\.\d+$` (AC3).
- Export: a crate part object `SM_Crate_Seat` with mesh data `SM_Crate_Seat.001`. Re-importing the Desktop and Mobile FBX into a cleared scene shows `obj.data.name == obj.name` for every mesh. After export, the session's object and mesh names equal their pre-export names (AC4).
- Validate: two parts sharing one mesh produce one `naming.mesh_data` finding whose message names both objects, with `authored=True` and `False` (AC5).
- The existing bake, variants, and validate tests pass unchanged (AC6).
- Evidence: `gate-blender-headless` (`scripts/run-blender-tests.sh`, headless background Blender only, no live session).

### T006: Unit check that the snapshot part maps to the exported mesh name

**File(s)**: `tests/unit/test_unreal_import.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- For a Desktop snapshot holding `SM_Crate` and `SM_Crate_Seat`, `build_import_code` expects `[["SM_Crate"], ["SM_Crate_Seat"]]`. That is the mesh name T002 now writes into the FBX, so `import_ue` needs no `_001` lookup. No Unreal editor is contacted (AC4).
- Evidence: `uv run pytest tests/unit/test_unreal_import.py -q`; `repository.tests`, `repository.lint`, `repository.format`, `repository.types`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #142 | 2026-11-11 | Initial defect tasks |
