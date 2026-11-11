# Root Cause Analysis: import_ue fails the Mobile variant of static assets that export as an LOD group

**Issue**: #146
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt/

## Root Cause

`_build_lod_group` in `plugins/nmg-game-dev-blender-addon/variants_core/mobile.py` gives a non-rigged asset with no child parts a Mobile variant that is an Empty `SM_<Name>_Mobile` (`fbx_type = "LodGroup"`) with mesh children `SM_<Name>_Mobile_LOD0`..`_LOD2`. The export strips `_Mobile`, so the FBX holds `SM_<Name>` with children `SM_<Name>_LOD0`..`_LOD2`. The contract snapshot holds one `MESH` entry per LOD object.

UE 5.8 Interchange imports that LOD group as one Static Mesh named after the Empty, `SM_<Name>`, and the children become its LODs. `src/nmg_game_dev/unreal/import_asset.py` instead assumes one Static Mesh per snapshot `MESH` entry:

- `_expected_mesh_candidates` drops `_LOD1`/`_LOD2` entries only when the asset is rigged. Its candidates for `SM_<Name>_Mobile_LOD0` are that key and `SM_<Name>_LOD0`, and neither is `SM_<Name>`. So `_check_expected` in the UE code raises `no static mesh for snapshot part`.
- `check_pivots` has the same rigged-only skip, and `_matching_mesh` matches only the key or the key without `_Mobile`.
- The static branch of `_bind_materials` records no LOD count. `LOD_COUNT` is filled only for skeletal meshes, so a Static Mesh that lost LODs goes unreported.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `src/nmg_game_dev/unreal/import_asset.py` | `_expected_mesh_candidates`, `_matching_mesh`, `check_pivots` | Map snapshot entries to UE mesh names; fail on `_LOD0`; would look up `_LOD1`/`_LOD2` |
| `src/nmg_game_dev/unreal/import_asset.py` | `_IMPORT_TEMPLATE` `_bind_materials` (static branch) | Reports no `lod_count` for static meshes |
| `src/nmg_game_dev/unreal/import_asset.py` | `import_variant` | Runs no LOD count check |
| `src/nmg_game_dev/unreal/__init__.py` | exports | Public surface of the import module |

## Fix Strategy

Keep the export and the FBX import options unchanged. Teach the host side what a static LOD group looks like in Unreal, and report and check its LOD count.

1. Add a helper `_lod_groups(report, variant, rigged) -> dict[str, list[str]]`. For a non-rigged report, it returns each base `B` that has a `MESH` entry `B_LOD0` of the variant, mapped to the sorted keys `B_LOD<n>` of that variant. For a rigged report it returns `{}`. A static Mobile crate gives `{"SM_Crate_Mobile": ["SM_Crate_Mobile_LOD0", "SM_Crate_Mobile_LOD1", "SM_Crate_Mobile_LOD2"]}`.
2. Add `_mesh_names(key) -> list[str]`, the sorted, de-duplicated names a snapshot key may carry in UE: the key, the key without `_Mobile`, and, when the key ends in `_LOD0`, both of those without `_LOD0`. `SM_Crate_Mobile_LOD0` gives `["SM_Crate", "SM_Crate_LOD0", "SM_Crate_Mobile", "SM_Crate_Mobile_LOD0"]`. `_expected_mesh_candidates` uses it for each entry. `_matching_mesh` tries the same names in order: key, export name, then the names without `_LOD0`.
3. Skip rule, shared by `_expected_mesh_candidates` and `check_pivots`: skip a `_LOD[1-9]` key when the asset is rigged (unchanged), or when its base is a key of `_lod_groups`. Static multi-part and Desktop snapshots have no `_LOD0` entry, so their candidates and checks stay the same.
4. In `_IMPORT_TEMPLATE`, the static branch of `_bind_materials` adds `"lod_count": mesh.get_num_lods()` to each `static_meshes` entry. Nothing else in the UE code changes.
5. Add a public `check_lod_counts(report, result) -> None`. For each LOD group from `_lod_groups`, it finds the UE mesh with `_matching_mesh(<base>_LOD0, result["static_meshes"])`. When there is no such mesh, or its `lod_count` is missing, not an int, or differs from `len(keys)`, it raises `PipelineError(code="import_ue.failed", stage="import_ue")` with the message `"{mesh} has {actual} LODs in Unreal; the snapshot has {expected} LOD objects ({first}..{last})"` (`actual` is `missing` when absent) and the existing import remediation.
6. `import_variant` calls `check_lod_counts(report, result)` after the `ok` check and before `check_pivots`.
7. Docs: the module docstring describes the static LOD group (one Static Mesh `SM_<Name>`, LODs from the group, LOD count check, `_LOD0` pivot), the NMG_RESULT schema shows `lod_count` on `static_meshes`, and `docs/asset-contract.md` §5 says how a static Mobile LOD group lands in Unreal.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `src/nmg_game_dev/unreal/import_asset.py` | `_lod_groups`, `_mesh_names`, skip rule, `_matching_mesh`, static `lod_count`, `check_lod_counts`, `import_variant` call, docstring | AC1–AC7, FR1–FR8, FR11 |
| `src/nmg_game_dev/unreal/__init__.py` | Export `check_lod_counts` | AC2, AC9 |
| `docs/asset-contract.md` | §5: a static Mobile LOD group is one Static Mesh `SM_<Name>` with LOD 0–2 in Unreal | FR11 |
| `tests/unit/test_unreal_import.py` | Static Mobile LOD group cases | AC9, AC7 |
| `tests/e2e/test_finalize_e2e.py` | Build the fixture in headless Blender; assert the Mobile LOD mesh and a reimport | AC8, AC1, AC5, AC6 |

## Blast Radius

- `import_variant` is called from `src/nmg_game_dev/pipeline/engine.py` (the `import_ue` step) for both variants. Only snapshots with a `_LOD0` `MESH` entry in a non-rigged variant, which means static Mobile LOD groups, get new behavior.
- `NMG_RESULT` gains `lod_count` on `static_meshes` entries. That is additive. `check_pivots` reads only `bounds`.
- The rigged path, the Blender export, the FBX import options, and the error codes are untouched.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Accept the Interchange LOD-group mesh and assert `get_num_lods()` | Selected | Matches observed UE 5.8 Interchange behavior (ghost1 workaround); host-only change; the count check catches a lost LOD |
| Export separate `_LOD1`/`_LOD2` FBX and place them with `StaticMeshEditorSubsystem.import_lod` | Rejected | Changes the export and contract layout for behavior Interchange already provides |
| `import_lod` from the LOD-group FBX | Rejected | Relies on unverified LOD-node selection on Interchange |
| Run the LOD count check inside the UE code | Rejected | The host-side check is unit-testable with the fake client, and the UE side only reports `get_num_lods()` |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #146 | 2026-11-11 | Initial defect design |
