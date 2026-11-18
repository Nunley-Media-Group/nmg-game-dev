# Tasks: geometry.normals never settles on a mesh with a twist seam

**Issue**: #243
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/232-make-mesh-cleanup-recalculate-normals-the-way-the-geometry-normals-check-judges-them/

## Implementation Tasks

### T001: Detect and report twist seams in the contract check

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py`, `plugins/nmg-game-dev-blender-addon/contract_core/report.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `twist_seam_edges(faces)` returns, in index order, the edges with two linked faces in `faces` whose loops walk the edge in the same direction
- `normal_violations(bm)` returns `(faces, seam_edges)`. A closed island with seam edges contributes seam edges and no faces.
- `geometry_findings` emits `geometry.twist_seam` with the seam edge count and edge-midpoint samples, and `RULES` holds its remediation
- Findings for meshes without twist seams are unchanged; `tests/blender/test_geometry_normals.py` passes

### T002: Repair twist seams in clean_mesh

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/meshes.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- In `_settle_normals`, the twist step deletes the faces linked to seam edges, then loose geometry. It runs before the `normal_violations` face deletion and repeats until no seam edge remains.
- `clean_mesh()` returns `faces`, `edges`, and `midpoints` for the twist repair
- AC1, AC2, AC4, and AC5 hold

### T003: Report twist repair from Desktop cleanup

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/cleanup.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- Each object entry carries `twist_repair` with `faces`, `edges`, and up to 5 world-space `samples`, rounded to 6 decimals (AC6)

### T004: Document geometry.twist_seam

**File(s)**: `docs/asset-contract.md`, `docs/skills/model-asset.md`, `skills/model-asset/SKILL.md`, `tests/unit/test_geometry_rule_docs.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `docs/asset-contract.md` section 3, `docs/skills/model-asset.md`, and `skills/model-asset/SKILL.md` each name `geometry.twist_seam` and explain that it reports a seam where a part joins itself with reversed winding
- `docs/skills/model-asset.md` states that a `geometry.twist_seam` sample index is an edge index and its position is the edge midpoint
- A test in `tests/unit/test_geometry_rule_docs.py` asserts all three documents name `geometry.twist_seam`, and it passes under `repository.tests`

### T005: Add regression coverage

**File(s)**: `tests/blender/normals_fixtures.py`, `tests/blender/test_twist_seams.py`, `tests/blender/test_clean_normals.py`
**Type**: Create
**Depends**: T002, T003
**Acceptance**:
- `normals_fixtures.klein(nu, nv)` builds the figure-8 Klein bottle exactly as #232's T003 specifies, and `test_clean_normals.py` imports it from there
- SCN001 (AC1): on `klein(32, 3)`, the faces that `clean_mesh()` removes equal the faces linked to `twist_seam_edges` after `recalc_island_normals` on a copy, 6 faces in all. `geometry_findings` on the result reports neither `geometry.normals` nor `geometry.twist_seam`.
- SCN002 (AC2): three further `clean_mesh()` and `geometry_findings` passes leave positions and polygon vertex lists unchanged, with no finding
- SCN003 (AC3): on the uncleaned fixture, `geometry_findings` reports `geometry.twist_seam` with count 5, every sample at the midpoint of a seam edge, and no `geometry.normals`
- SCN004 (AC4): two copies give equal positions, polygon vertex lists, and normals
- SCN005 (AC5): `contract_fixtures.build_crate`, a correctly facing quad, and an inside-out `create_cube` each report `twist_repair` faces 0 and no `geometry.twist_seam`. The cube is flagged 6 `geometry.normals` faces before cleanup, the quad passes, and the crate keeps its triangle count.
- SCN006 (AC6): `cleanup_desktop("Twist")` reports `twist_repair` faces 6, edges 5, and samples at world-space seam midpoints. The crate asset reports 0, 0, and `[]`.
- `test_clean_normals.py` SCN004 accepts removed faces that are twist seam faces or faces flagged after twist repair, and still asserts that no face is added and that the two copies are identical
- On the pre-fix code, SCN001, SCN003, and SCN006 fail and SCN005 passes
- `scripts/run-blender-tests.sh` (gate-blender-headless), `repository.tests`, `repository.lint`, `repository.format`, and `repository.types` pass

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #243 | 2026-11-18 | Initial defect tasks |
