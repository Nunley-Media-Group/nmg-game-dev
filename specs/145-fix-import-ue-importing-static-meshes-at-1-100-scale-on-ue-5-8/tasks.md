# Tasks: import_ue imports static meshes at 1/100 scale on UE 5.8

**Issue**: #145
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt/

## Implementation Tasks

### T001: Record the mesh datablock name in the contract snapshot

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/validate.py`, `tests/blender/test_finalize_core.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `object_snapshot` returns `"mesh"` set to the object's mesh datablock name for `MESH` objects and `None` for other types; all other snapshot fields are unchanged.
- A headless Blender test asserts that a part object `SM_Crate_Lid` with datablock `SM_Crate_Lid.001` is snapshotted with `"mesh": "SM_Crate_Lid.001"` and that an Empty has `"mesh": None`; `gate-blender-headless` passes.

### T002: Correct static import size, bounds, and naming in the generated UE Python

**File(s)**: `src/nmg_game_dev/unreal/import_asset.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `build_import_code` passes `multi_part` (more than one base part in the variant, ghost1's `_multi_part` rule). `_static_options` sets `transform_vertex_to_absolute = not multi_part` and keeps `combine_meshes` and `bake_pivot_in_vertex` off (AC1, AC2, FR1, FR2).
- For a multi-part asset, after the static FBX import every LOD of every imported static mesh has `build_scale3d` written as `(100, 100, 100)` through `StaticMeshEditorSubsystem.set_lod_build_settings` on every run (not only while it is 1.0), and the asset is saved, so reported bounds are the new geometry in centimetres (AC1, AC4, FR1, FR4).
- For a multi-part asset, `build_import_code` passes `mesh_names` (datablock name → part export name for this variant, excluding rigged LOD extras and datablocks shared by several parts); each imported static mesh whose UE-sanitized name matches a mapped datablock name and differs from its export name is renamed to the export name, consolidating any existing asset at that name into the new one first (AC3, FR3).
- The skeletal path runs neither step (AC6, FR6). Texture settings, material-instance creation and binding, `NMG_RESULT` keys, error codes, and `PIVOT_TOLERANCE_CM` are unchanged (AC8, FR7). The code never reads or sets `Interchange.FeatureFlags.Import.FBX` (FR5).
- The module docstring describes the single-part/multi-part split, the build-scale and rename steps, and names the ghost1 `sitecustomize.py` workaround they replace. `repository.lint`, `repository.format`, and `repository.types` pass.

### T003: Run the generated import code against an in-memory `unreal` fake

**File(s)**: `tests/unit/fake_unreal.py`, `tests/unit/test_unreal_import.py`
**Type**: Create | Modify
**Depends**: T002
**Acceptance**:
- `tests/unit/fake_unreal.py` provides an `unreal` module stand-in that the tests install in `sys.modules` before `exec` of `build_import_code(...)`. Its static meshes model UE 5.8 Interchange: with `transform_vertex_to_absolute` off they report source bounds (metres read as centimetres) times the LOD0 build scale and are named after the mesh datablock; with it on they report bounds converted to centimetres plus the node translation and are named after the node. Bounds stay stale until a build-settings write rebuilds the mesh. It supports `rename_asset`, `consolidate_assets`, `does_asset_exist`, `get_num_lods`, and LOD build settings. It never contacts a running editor.
- Tests assert, from the printed `NMG_RESULT` and `check_pivots`: a single-part 8 m asset and a multi-part asset with an 8 m part each report `-800`/`800` cm bounds and pass the pivot check (AC1); two parts with origins away from the asset origin report bounds relative to their own origins (AC2); a part whose datablock is `SM_Crate_Lid.001` is reported as `SM_Crate_Lid`, and on Mobile the `_Mobile` suffix is removed (AC3); a destination pre-seeded with a 1/100-scale `SM_Crate_Lid` and a datablock-named duplicate reports the new bounds and keeps one asset per part (AC4); a rigged report sets no build scale and renames nothing (AC6); texture settings, `MI_` bindings, result keys, and error codes match the existing expectations (AC8).
- The option-string test replaces `transform_vertex_to_absolute = False` with the `not PARAMS["multi_part"]` expression, keeps `bake_pivot_in_vertex = False`, and asserts the build-scale and rename steps and the absence of `Interchange.FeatureFlags` (FR5, FR9).
- At least the AC1 and AC4 tests fail against the pre-fix template. `uv run pytest tests/unit/test_unreal_import.py -q` passes.

### T004: Add BDD scenarios for the corrected static import

**File(s)**: `tests/bdd/features/import_ue_static_scale.feature`, `tests/bdd/steps/test_import_ue_static_scale.py`
**Type**: Create
**Depends**: T003
**Acceptance**:
- One scenario each for AC1, AC2, AC3, AC4, AC5 (both variants on the fake), AC6, and AC8, each driving `import_variant` with the `tests/unit/fake_unreal.py` stand-in behind an `UnrealPythonClient` that executes the generated code.
- `uv run pytest tests/bdd -q` passes as part of `repository.tests`.

### T005: Add an opt-in multi-part end-to-end finalize test with a generated fixture

**File(s)**: `tests/e2e/fixtures/build_multipart_fixture.py`, `tests/e2e/test_finalize_e2e.py`, `tests/blender/test_e2e_fixture_builder.py`
**Type**: Create | Modify
**Depends**: T002
**Acceptance**:
- `build_multipart_fixture.py` exposes `build_gantry()` and, when run as `blender --background --python tests/e2e/fixtures/build_multipart_fixture.py -- <out.blend>`, saves a non-rigged `Gantry` collection: a root `SM_Gantry` larger than one metre and at least two child parts with origins away from the asset origin, one of whose mesh datablock is named `SM_Gantry_<Part>.001`, each with a material slot `M_Gantry_<Part>`.
- `tests/blender/test_e2e_fixture_builder.py` calls `build_gantry()` in headless Blender and asserts the part count, the one-metre size, the off-origin part origins, and the differing datablock name; `gate-blender-headless` passes. It does not contact the live Blender session.
- A new `slow` test in `tests/e2e/test_finalize_e2e.py` builds that fixture into `tmp_path` with the binary from `nmg_game_dev.pipeline.blender_proc.resolve_blender()`, runs `finalize` with `blend=` the result, and asserts both variants import, one static mesh per part named after its object in each variant's result, and that `import_ue` passed its pivot check (AC7).
- The existing crate test is unchanged. `uv run pytest tests/e2e/test_finalize_e2e.py -q` (no `--runslow`) collects the new test and reports it skipped. The `--runslow` run is opt-in for a developer and is not run during implement or verify, which must not launch, restart, or connect to the live Blender or Unreal editors.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #145 | 2026-11-11 | Initial defect tasks |
