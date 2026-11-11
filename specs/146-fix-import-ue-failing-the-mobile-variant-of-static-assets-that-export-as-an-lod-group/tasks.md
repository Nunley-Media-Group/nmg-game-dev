# Tasks: import_ue fails the Mobile variant of static assets that export as an LOD group

**Issue**: #146
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt/

## Implementation Tasks

### T001: Map a static LOD group to one Static Mesh and check its LOD count

**File(s)**: `src/nmg_game_dev/unreal/import_asset.py`, `src/nmg_game_dev/unreal/__init__.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `_expected_mesh_candidates` for a non-rigged Mobile snapshot with `SM_Crate_Mobile_LOD0`..`_LOD2` returns exactly `[["SM_Crate", "SM_Crate_LOD0", "SM_Crate_Mobile", "SM_Crate_Mobile_LOD0"]]` (AC1, FR3).
- `check_pivots` matches `SM_Crate_Mobile_LOD0` to the UE mesh `SM_Crate` and compares its bounds at 0.01 cm. A mismatch raises `import_ue.pivot_mismatch`. `_LOD1`/`_LOD2` entries of a static LOD group are skipped (AC3, FR5).
- The static branch of the UE `_bind_materials` writes `"lod_count": mesh.get_num_lods()` into each `static_meshes` entry. The other fields, the FBX options, and the UE error strings are unchanged (AC4, FR2, FR6, FR7).
- New public `check_lod_counts(report, result)` raises `import_ue.failed` naming the mesh, the expected count, and the actual count (or `missing`) when a static LOD group's mesh `lod_count` differs from its number of LOD objects. `import_variant` calls it before `check_pivots`. It is exported from `nmg_game_dev.unreal` and listed in `__all__` (AC2, FR4).
- Static Desktop, multi-part static Mobile, and rigged snapshots produce the same `expected_meshes` and pivot behavior as before, and `check_lod_counts` does nothing for them (AC7, FR8).
- The module docstring and NMG_RESULT schema describe the static LOD group and the static `lod_count` (FR11).

### T002: Document the static Mobile LOD group in Unreal

**File(s)**: `docs/asset-contract.md`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- §5 states that in Unreal a static Mobile LOD group is one Static Mesh `/Game/<Category>/<Name>/Mobile/SM_<Name>` whose LOD 0, 1, and 2 are `SM_<Name>_LOD0`, `_LOD1`, and `_LOD2`, and that `import_ue` checks its LOD count against the snapshot (FR11).

### T003: Unit regression coverage for the static Mobile LOD group

**File(s)**: `tests/unit/test_unreal_import.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- A static Mobile snapshot with `SM_Crate_Mobile` (`EMPTY`) and `SM_Crate_Mobile_LOD0`..`_LOD2` (`MESH`, with `local_bounds`) yields the single expected-mesh list from T001 in the embedded PARAMS. The generated code compiles and contains `get_num_lods()` and `"lod_count"` (AC1, AC4, AC9).
- `import_variant` with the fake client returns a result whose `static_meshes` holds only `SM_Crate` with `lod_count` 3 and matching bounds (AC1, AC9).
- `lod_count` 1 (and a missing `lod_count`) raises `import_ue.failed` whose message contains `SM_Crate`, `3`, and `1` (or `missing`) (AC2, AC9).
- `check_pivots` passes when `SM_Crate` bounds match `SM_Crate_Mobile_LOD0`, and raises `import_ue.pivot_mismatch` when they are off by more than 0.01 cm, without a lookup failure for `_LOD1`/`_LOD2` (AC3, AC9).
- The static LOD-group Mobile code contains exactly one `_import_fbx` call path for `SM_Crate.fbx`, no `StaticMeshEditorSubsystem`, no `import_lod`, and no `Interchange.FeatureFlags`. Its static branch binds materials through `mesh.set_material`. With the fake returning `materials` `{"M_Crate_Body": ".../MI_Crate_Body"}`, the result carries that binding (AC5, FR2, FR7).
- Calling `import_variant` twice for the static Mobile LOD group with the same fake result passes both times, and the code sets `replace_existing = True` (AC6).
- The existing Desktop, multi-part Mobile (`SM_Crate_Mobile` plus a part, no LODs), and rigged tests keep passing unchanged. A new multi-part Mobile case asserts one candidate list per part and that `check_lod_counts` passes with no `lod_count` (AC7).
- Evidence: `uv run pytest tests/unit/test_unreal_import.py -q` and `repository.tests`, `repository.lint`, `repository.format`, `repository.types` pass.

### T004: End-to-end static Mobile import with a generated fixture

**File(s)**: `tests/e2e/test_finalize_e2e.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- When neither `tests/e2e/fixtures/crate.blend` nor `NMG_FINALIZE_E2E_BLEND` exists, the test builds the fixture with no manual step. It runs `resolve_blender()` (`src/nmg_game_dev/pipeline/blender_proc.py`) in `--background` with a script that imports `tests/blender/contract_fixtures.py`, builds a compliant single-mesh, non-rigged `Crate` (dense enough that the variants step records strictly decreasing Mobile `lod_tris`), and saves it to `tmp_path` (AC8, FR9).
- After `finalize`, it asserts both content paths, uses `UnrealMcpClient` to assert that `/Game/Props/Crate/Mobile/SM_Crate` is a `StaticMesh` with `get_num_lods() == 3` and that no `SM_Crate_LOD0`..`_LOD2` asset exists in that folder (AC1).
- It asserts that each Mobile LOD's triangle count in UE equals the variants step's recorded `lod_tris` for that level, and that the import result's `materials` binds `M_Crate_Body` to `/Game/Props/Crate/Mobile/MI_Crate_Body` (AC5).
- It calls `import_variant` a second time for the Mobile variant with the same export folder and pre-export report, and asserts `static_meshes["SM_Crate"]["lod_count"] == 3` with no exception (AC6).
- The module stays `slow`-marked and skips without `--runslow`. It is opt-in, not a registered gate, and implement/verify do not run it against live editors.
- Evidence: `uv run pytest tests/e2e/test_finalize_e2e.py --runslow --collect-only -q` collects the test without launching or connecting to Blender or Unreal. `uv run pytest tests/e2e/test_finalize_e2e.py -q` reports it skipped. `repository.types`, `repository.lint`, and `repository.format` cover the file (AC8).

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #146 | 2026-11-11 | Initial defect tasks |
