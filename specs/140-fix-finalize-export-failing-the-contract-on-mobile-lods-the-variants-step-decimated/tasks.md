# Tasks: Fix finalize export failing the contract on Mobile LODs the variants step decimated

**Issue**: #140
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/33-build-blender-cleanup-remesh-lod-and-variant-operators/

## Implementation Tasks

### T001: Share one clean routine between Desktop cleanup and fitted meshes

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/meshes.py`, `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `meshes.clean_mesh(mesh)` runs, in order: merge doubles (1e-5), `dissolve_degenerate` (1e-6), delete faces with area `< 1e-8`, delete faces beyond the two largest on every edge with more than two faces (ties keep the lower index), delete faces whose vertex set repeats an earlier face's (keep the first), delete loose edges and vertices, then `recalc_face_normals` (FR3, FR4).
- `cleanup_desktop` uses `clean_mesh`, and its `tris_after` counts the cleaned meshes (AC4).
- `cleanup.py` no longer defines `_clean_mesh` or the 1e-10 zero-area constant, and `meshes.py` no longer defines `_drop_duplicate_faces`.

### T002: Clean every mesh fit_meshes returns

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/meshes.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `fit_meshes` runs `clean_mesh` on every candidate, both the under-budget copies and every decimated copy, before it compares the triangle total with the target (FR1, FR5).
- The rigged chain, the LodGroup and the multi-part path all receive cleaned meshes, and the `lod_tris` that `build_mobile` reports equal the cleaned meshes' triangle counts (AC1, AC6).

### T003: Re-seat the Mobile variant after fitting

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/mobile.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- `build_mobile` measures the world-space bounding-box bottom centre of the Mobile meshes whose names do not match `_LOD[1-9]$`. When it is not exactly the origin, it translates the mesh data of every Mobile mesh, LOD1 and LOD2 included, by the opposite offset in each object's local frame (FR2, AC3).
- Objects, origins, parenting, the LodGroup Empty, Armature modifiers and vertex groups are unchanged (AC6).
- An asset whose Mobile bottom centre is already exactly at the origin is not translated (AC7).

### T004: Document the clean and re-seat

**File(s)**: `docs/asset-contract.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- `docs/asset-contract.md` §5 Variants states that the `variants` step cleans every Mobile mesh it produces (degenerate, zero-area, non-manifold-edge, duplicate and loose geometry) and re-seats the variant so its bottom centre is at the world origin (FR7).
- `CHANGELOG.md` `[Unreleased]` has a bullet for this fix that ends with `(#140)`.

### T005: Add Blender regression coverage

**File(s)**: `tests/blender/test_variants_clean.py`
**Type**: Create
**Depends**: T003
**Acceptance**:
- AC1 / SCN001: a rigged asset above the Mobile budget whose decimation leaves a zero-area face → after `build_mobile`, `validate_asset` reports no `geometry.zero_area` or `geometry.loose` on any Mobile LOD.
- AC2 / SCN002: a Desktop mesh with a tiny face on an edge shared by three faces → after `cleanup_desktop` and `build_mobile`, `validate_asset` reports no `geometry.normals` on the Desktop mesh or any Mobile LOD, and a second `validate_asset` call returns the same findings.
- AC3 / SCN003: an asset whose bottom-most extreme vertex is removed by decimation → after `build_mobile` the Mobile root origin and bottom centre are within `1e-3` of the origin, and no `pivot.bottom_center` is reported.
- AC4 / SCN004: a Desktop mesh with a non-manifold-edge face and two faces sharing one vertex set → after `cleanup_desktop` the extra face is gone, one face remains for the set, and `tris_after` equals the input count minus the removed triangles.
- AC5 / SCN005: the AC4 asset through `build_mobile`, `export_variants` and `reimport_check` → no `reimport.tris` finding for Desktop or any Mobile mesh.
- AC6 / SCN006: rigged, unrigged single-mesh and multi-part assets → every LOD is within its target, rigged LODs keep the `Armature` modifier and vertex groups, the layout (rigged chain, LodGroup, LOD0-only parts) matches the existing layout, and the result's `lod_tris` equal the meshes' triangle counts.
- AC7 / SCN007: an already-clean asset (the `build_crate` fixture) → triangle counts and the pivot match the existing expectations in `tests/blender/test_variants.py`, and two runs give identical triangle counts and vertex positions.
- Each test fails against the pre-fix code and passes with T001–T003.
- `gate-blender-headless` (`scripts/run-blender-tests.sh`) passes with the new and existing `tests/blender/` suites, and `repository.lint`, `repository.format` and `repository.types` pass.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #140 | 2026-11-11 | Initial defect report |
