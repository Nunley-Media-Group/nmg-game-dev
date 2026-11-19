# Tasks: Mesh cleanup recalculates normals differently from the geometry.normals check

**Issue**: #232
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/140-fix-finalize-export-failing-the-contract-on-mobile-lods-the-variants-step-decimated/

## Implementation Tasks

### T001: Share the per-island normal recalculation

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `recalc_island_normals(bm)` recalculates normals once per island from `_islands(bm)`, in island order
- `normal_violations(bm)` is public, and `geometry_findings` calls it; findings are otherwise unchanged
- The existing `tests/blender/test_geometry_normals.py` passes unchanged

### T002: Settle normals in clean_mesh

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/meshes.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `clean_mesh()` no longer calls a whole-mesh `recalc_face_normals`
- `_settle_normals` loops as design.md describes: shared recalc, write, probe with `normal_violations`, then delete flagged faces and loose geometry, until nothing is flagged
- AC1–AC4 hold. The existing `tests/blender/test_variants_clean.py` passes unchanged.

### T003: Add regression coverage

**File(s)**: `tests/blender/test_clean_normals.py`
**Type**: Create
**Depends**: T002
**Acceptance**:
- Fixture `klein(nu=16, nv=8)` builds the figure-8 Klein bottle, r = 2.0, as a quad grid. `u = 2πi/nu` and `v = 2π(j + 0.5)/nv`. Row `nu - 1` closes onto row 0 with the twisted seam `(i, j) → (0, (-j) % nv)`.
- Fixture `fin_klein` adds a triangle on face 0's first edge, with its tip at the edge midpoint plus 0.02 along face 0's normal. It then reverses the faces flagged by the open-island winding check until none remain, so `geometry_findings` reports no geometry finding.
- SCN001 (AC1): `geometry_findings` reports `geometry.normals` on `fin_klein` after the pre-fix steps (drop the fin, whole-mesh `recalc_face_normals`), which proves the fixture reproduces the bug. It reports none after `clean_mesh()`.
- SCN002 (AC2): collection `Klein` holds `SM_Klein` from `fin_klein`. Validate reports no `geometry.*` finding before `cleanup_desktop` and none after.
- SCN003 (AC3): after `optimize_mobile("Klein", "standard_prop")`, validate reports no `geometry.normals` finding on any `SM_Klein_Mobile*` target
- SCN004 (AC4): on two copies of the plain `klein` mesh, `clean_mesh()` leaves no face that is not a source face. It removes every face that `recalc_island_normals` then `normal_violations` flags on a source copy. The two outputs have equal vertex positions, polygon vertex lists, and normals.
- SCN005 (AC5): the single correctly facing quad passes. A `create_cube` with all faces reversed is flagged 6 times; after `clean_mesh()` it keeps 6 faces, all outward, with no finding. A `contract_fixtures.build_crate` crate keeps its triangle count through `clean_mesh()` and has no `geometry.*` finding.
- On the pre-fix `clean_mesh()`, SCN001–SCN004 fail and SCN005 passes
- `scripts/run-blender-tests.sh` (gate-blender-headless), `repository.lint`, `repository.format`, and `repository.types` pass

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #232 | 2026-11-18 | Initial defect tasks |
