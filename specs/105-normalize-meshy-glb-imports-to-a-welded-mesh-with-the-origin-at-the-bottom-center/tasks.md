# Tasks: Normalize Meshy GLB imports to a welded mesh with the origin at the bottom center

**Issue**: #105
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/98-add-optional-meshy-model-generation-and-retexturing-through-the-meshy-api/

## Implementation Tasks

### T001: Normalize the imported mesh

**File(s)**: `scripts/blender/meshy_session.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `_normalize` bakes transforms, welds within `1e-5` m, recenters to the bottom center, clears custom normals, smooths by 30°, and recalculates normals outward, as in the design (AC1–AC3, FR1–FR3).
- `import_glb` returns `merged_vertices` and `origin_offset` with the existing keys. Failures inside normalization return the `meshy.session_failed` error shape (AC4).
- The module docstring lists the new result keys. Other ops are unchanged.

### T002: Surface the normalization in the Meshy job result and docs

**File(s)**: `src/nmg_game_dev/meshy/jobs.py`, `tests/meshy_fakes.py`, `docs/mcp/meshy.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- A generate job that loaded into the session copies `merged_vertices` and `origin_offset` from the import result into its `result`. A job whose import was unreachable is unchanged (AC4, FR4).
- The fake session returns both keys from `import_glb`.
- `docs/mcp/meshy.md` says imported meshes are welded, recentered to the bottom center, and smooth-shaded, and lists the two result keys.
- `CHANGELOG.md` `[Unreleased]` has an Added bullet that ends with `(#105)`.

### T003: Tests

**File(s)**: `tests/blender/test_meshy_session.py`, `tests/unit/meshy/test_jobs.py`, `tests/bdd/features/meshy.feature`, `tests/bdd/test_meshy_bdd.py`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- `tests/blender/test_meshy_session.py` builds a GLB from a UV-seamed cube (UV-unwrapped with seams, so the exporter splits vertices), placed at location `(2, 3, 4)` with custom split normals set. After `import_glb`, it asserts: one connected island and `merged_vertices > 0`, with face count, sorted per-corner UVs, and material slots equal to the source (AC1); identity transforms and bounding-box X/Y center and min Z within `1e-3` of 0 (AC2); `has_custom_normals` false, all faces smooth, cube edges marked sharp, and every face normal dotted with (face center − mesh centroid) greater than 0 (AC3); and the result's `merged_vertices` and three-element `origin_offset` (AC4). The existing exact-dict assertion is updated for the two new keys. The suite runs under `scripts/run-blender-tests.sh`.
- A Meshy jobs unit test asserts the job result carries both keys from the fake session (AC4).
- `tests/bdd/features/meshy.feature` gains SCN001–SCN004 scenarios for this issue, bound in `tests/bdd/test_meshy_bdd.py` through the fake session and the job result. `pytest tests/unit tests/bdd` passes.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #105 | 2026-10-31 | Initial feature tasks |
