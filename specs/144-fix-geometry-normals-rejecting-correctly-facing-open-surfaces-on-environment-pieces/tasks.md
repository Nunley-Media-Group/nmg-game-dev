# Tasks: geometry.normals rejects correctly facing open surfaces

**Issue**: #144
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Judge normals per island

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- The `geometry.normals` count is the sum over edge-connected islands. Open islands (any edge with one linked face) count the minority of faces whose winding disagrees with their neighbours across two-face edges. Closed islands count faces that `recalc_face_normals` restricted to that island reverses (FR1–FR3).
- The count is independent of mesh position and of other islands (FR4).
- The rule id, target, and message shape are unchanged. `geometry_findings` still works only on the caller's copy and frees its bmesh (FR5).

### T002: Update the geometry.normals remediation

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/report.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- The `geometry.normals` remediation is design.md's text. It distinguishes closed parts (recalculate outside on that part) from open sheets (flip only inconsistent faces, wind consistently, face the viewer), and no longer gives a blanket "recalculate outside" instruction for open surfaces (AC7, FR7).

### T003: Add behavioral regression coverage

**File(s)**: `tests/blender/test_geometry_normals.py`
**Type**: Create
**Depends**: T001, T002
**Acceptance**:
- SCN001 (AC1):
  - 500 seeded random placements of one upward-facing axis-aligned quad, and 500 of one tilted quad, built with bmesh at positions within ±10 m of the origin, give no `geometry.normals` finding from `geometry_findings`.
  - The issue's quad from (3.37, -2.11, 0.4) to (7.9, 1.63, 0.4) gives none.
- SCN002 (AC2): a floor-plus-back-wall sheet facing into the room, and a welded 8×8 grid ground sheet, give no finding.
- SCN003 (AC3): the same sheets with one face's winding reversed give a finding with count 1.
- SCN004 (AC4): a closed box with one flipped face gives count 1, and a box turned inside out gives count 6.
- SCN005 (AC5): one mesh with a correct box, a floor quad, and a box with one flipped face gives exactly count 1.
- SCN006 (AC6):
  - Two correct boxes touching at a vertex, along an edge, and across part of a face, each merged with `remove_doubles`, give no finding.
  - 200 seeded random welded touching-box arrangements give no finding.
- SCN007 (AC7): the `geometry.normals` remediation mentions both closed parts and open sheets, and does not consist only of "Recalculate normals outside".
- Both callers stay compatible:
  - `validate_asset` on the compliant Crate fixture plus an added floor-quad object reports no `geometry.normals` finding;
  - `inspect_asset` returns no `geometry.normals` entry for that floor object (FR5).
- The SCN001, SCN002, and SCN005 tests fail against the pre-fix `_flipped_faces` and pass after T001. All tests pass through `scripts/run-blender-tests.sh` (`gate-blender-headless`) in headless background Blender, without any live Blender or Unreal editor.

### T004: Document the environment-piece authoring rule

**File(s)**: `docs/asset-contract.md`, `skills/model-asset/SKILL.md`, `docs/skills/model-asset.md`, `tests/unit/test_geometry_rule_docs.py`
**Type**: Modify, Create
**Depends**: T001
**Acceptance**:
- §3 of `docs/asset-contract.md` and both `/model-asset` documents state the following (FR8, AC8):
  - open sheets are allowed where nothing sees underneath and must be wound consistently and face the viewer;
  - closed parts must face outward;
  - `geometry.normals` checks open sheets for consistent winding and closed parts for outward faces;
  - touching primitives are either merged by distance so they share vertices, or kept about 0.6 mm apart, because coincident unmerged vertices raise `geometry.duplicates`.
- The §6 budget table is unchanged.
- SCN008 (AC8): `tests/unit/test_geometry_rule_docs.py` asserts that each of the three documents names open sheets, winding, outward-facing closed parts, and `geometry.duplicates` for touching primitives. `uv run pytest tests/unit tests/bdd -q` (`repository.tests`) and `plugin.validate` pass.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #144 | 2026-11-11 | Initial defect tasks |
