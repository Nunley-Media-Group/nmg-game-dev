# Defect Report: import_ue fails the Mobile variant of static assets that export as an LOD group

**Issue**: #146
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt/

## Reproduction

1. In Blender, author a non-rigged collection `<Name>` with a single mesh `SM_<Name>` and no child parts.
2. Run finalize so `import_ue` runs for both variants on UE 5.8 with Interchange FBX import at its default.
3. The Mobile export is an LOD group: an Empty `SM_<Name>` with children `SM_<Name>_LOD0`, `_LOD1`, and `_LOD2`. The Mobile snapshot holds the `MESH` entries `SM_<Name>_Mobile_LOD0`, `_LOD1`, and `_LOD2`.
4. Interchange imports the Mobile FBX as one Static Mesh `SM_<Name>` whose LODs are the three children.
5. `import_ue` fails the Mobile variant with `import_ue.failed`: `no static mesh for snapshot part: SM_<Name>_LOD0`.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | The Mobile variant is one Static Mesh `/Game/<Category>/<Name>/Mobile/SM_<Name>` with three LODs. `import_ue` maps the snapshot's `_LOD0` entry to that mesh. It checks that the mesh has as many LODs as the snapshot has LOD objects, checks LOD0's bounds against the `_LOD0` entry, and passes. |
| **Actual** | `import_ue` expects one static mesh asset per LOD object and fails on `SM_<Name>_LOD0`. It never checks the LOD count of the imported Static Mesh, so a mesh that lost LOD1 and LOD2 would not be reported. |

## Acceptance Criteria

### AC1: A static Mobile LOD group imports as one Static Mesh with three LODs

**Given** a non-rigged asset with no child parts whose Mobile snapshot holds `SM_<Name>_Mobile_LOD0`, `_LOD1`, and `_LOD2`
**When** `import_ue` builds the Mobile import code and the UE result reports one Static Mesh `SM_<Name>` with `lod_count` 3
**Then** the import code expects exactly one static mesh, matched by `SM_<Name>`, and no separate `SM_<Name>_LOD0`, `_LOD1`, or `_LOD2` mesh
**And** `import_variant` returns that result without failing with `no static mesh for snapshot part`

### AC2: The LOD count is verified against the snapshot

**Given** a static Mobile variant whose snapshot holds three LOD objects
**When** the imported Static Mesh reports a different number of LODs
**Then** `import_ue` fails with `import_ue.failed`
**And** the message names the mesh, the expected LOD count, and the actual LOD count

### AC3: The LOD0 pivot is verified against the snapshot

**Given** a static Mobile variant with an LOD group
**When** `check_pivots` runs on the import result
**Then** it compares the bounds of the Static Mesh `SM_<Name>` with the snapshot entry `SM_<Name>_Mobile_LOD0`, within 0.01 cm
**And** a mismatch raises `import_ue.pivot_mismatch`
**And** the `_LOD1` and `_LOD2` snapshot entries are not looked up as separate meshes

### AC4: The result reports the LOD count of a static mesh

**Given** a successful static import
**When** the UE code prints `NMG_RESULT`
**Then** each `static_meshes` entry carries `lod_count`, the Static Mesh's `get_num_lods()`: 3 for a Mobile LOD group, 1 for any other static mesh

### AC5: Each LOD carries its own geometry and the asset's materials

**Given** a static Mobile LOD group
**When** `import_ue` builds the Mobile import code
**Then** the code imports the LOD-group FBX `SM_<Name>.fbx` once, with no separate LOD import and no engine LOD reduction, so LOD 0, 1, and 2 come from the exported `_LOD0`, `_LOD1`, and `_LOD2` meshes
**And** the static mesh's material slots `M_<Name>_<Part>` are bound to `MI_<Name>_<Part>` by the same code path as a static mesh without LODs

### AC6: A reimport gives the same result

**Given** a Mobile variant that was already imported, and Mobile import code that imports with `replace_existing`
**When** `import_variant` runs again for the Mobile variant and the UE result again reports `SM_<Name>` with `lod_count` 3 and matching bounds
**Then** the LOD count and pivot checks pass again

### AC7: Other imports are unchanged

**Given** a static Desktop variant, a multi-part static Mobile variant (root and parts, LOD0 only), and a rigged character's Desktop and Mobile variants
**When** `import_ue` builds the import code and checks the result for each
**Then** the expected meshes, the pivot checks, and the error codes are the same as before this fix
**And** a multi-part static asset still expects one static mesh per part
**And** no LOD count check is applied to them

### AC8: An end-to-end test covers a static Mobile import

**Given** `tests/e2e/test_finalize_e2e.py`
**When** `uv run pytest tests/e2e/test_finalize_e2e.py --runslow --collect-only -q` runs
**Then** it collects a `slow`-marked test for the static Mobile import. The test builds a single-mesh non-rigged fixture in headless Blender with no manual step, and it asserts that both variants import, that the Mobile folder holds one Static Mesh `SM_<Name>` with three LODs and no `SM_<Name>_LOD0`..`_LOD2` assets, that each LOD's triangle count matches the variants step, and that a second Mobile import passes the LOD count and pivot checks
**And** without `--runslow` the test is skipped

### AC9: Unit tests cover the static Mobile LOD group

**Given** the fake `unreal` client in `tests/unit/test_unreal_import.py`
**When** `uv run pytest tests/unit/test_unreal_import.py` runs
**Then** it covers a static Mobile snapshot with three LOD objects that imports as one mesh with three LODs, a LOD count mismatch, the LOD0 pivot comparison and mismatch, and a repeated Mobile import

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | A static Mobile LOD group is accepted as one Static Mesh `SM_<Name>`, imported from the unchanged LOD-group FBX, whose LODs are the exported `_LOD0`, `_LOD1`, and `_LOD2` meshes | Must |
| FR2 | The import does not read or set `Interchange.FeatureFlags.Import.FBX`, does not import LODs separately, and relies on Interchange's LOD-group import; a mesh with the wrong LOD count fails under FR4 | Must |
| FR3 | For a static LOD group, the expected-mesh check and `check_pivots` treat the snapshot's `_LOD0` entry as the Static Mesh `SM_<Name>` and do not expect a separate asset for any `_LOD1`+ entry | Must |
| FR4 | The import fails with `import_ue.failed` when the Static Mesh's reported `lod_count` differs from the number of LOD objects in the snapshot, or is missing; the message names the mesh and gives both counts | Must |
| FR5 | `check_pivots` compares the LOD-group mesh's bounds with the snapshot's `_LOD0` `local_bounds` at the existing 0.01 cm tolerance | Must |
| FR6 | Each `static_meshes` entry of `NMG_RESULT` carries `lod_count`; the other fields and the error codes do not change | Must |
| FR7 | Material instances are created and bound for a static mesh with LODs as for one without | Must |
| FR8 | Static Desktop, multi-part static Mobile, and rigged imports keep their current expected meshes, pivot checks, and error codes, and get no LOD count check | Must |
| FR9 | An opt-in (`--runslow`) e2e test builds a single-mesh static fixture without a manual step and verifies the Mobile Static Mesh name, its three LODs and their triangle counts, the absence of per-LOD assets, the pivot check, and a reimport | Must |
| FR10 | Unit tests cover the static Mobile LOD group: success, LOD count mismatch, and the LOD0 pivot comparison | Must |
| FR11 | `docs/asset-contract.md` and the `import_asset.py` module docstring state that a static Mobile LOD group is one Static Mesh `SM_<Name>` with three LODs in Unreal, and that `static_meshes` entries carry `lod_count` | Should |

## Out of Scope

- Changing the static Mobile export (it stays one LOD-group FBX)
- Static meshes importing at 1/100 scale and being named after mesh datablocks (#145)
- Resolving imported meshes when the import task lists only the first one (#141)
- Decimated Mobile LODs failing the contract at export (#140)
- Naming collisions that pass validate and fail after the bake (#142)
- LODs for multi-part static assets, which keep LOD0 only
- Changing the rigged Mobile LOD layout (one FBX per LOD level) or adding a LOD count check to it
- LOD screen sizes and other LOD settings in Unreal

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #146 | 2026-11-11 | Initial defect report |
