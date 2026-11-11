# Tasks: Report sample locations in geometry contract findings

**Issue**: #153
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Located samples in geometry findings

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `geometry_findings(name, mesh, matrix_world=None, group_names=())` keeps positional `(name, mesh)` calls working.
- Each of the four rules collects its sorted offending indices. The normals helper returns face indices, and the count is their length.
- Each finding adds `count` (the full total) and `samples`: at most 5, the lowest indices first. Each sample gives:
  - `index`;
  - world-space `position` (three floats rounded to 6 places): the vertex position or face center;
  - sorted `vertex_groups`, where a face covers its vertices and a duplicate covers the duplicate and its coincident vertex, and the list is empty when there are no groups;
  - `coincides_with`, for duplicates only.
- The message keeps the count and appends the first sample's position.
- Clean meshes emit nothing, and detection is unchanged (AC1–AC5, AC7, FR1–FR5).

### T002: Pass the world matrix and group names from both callers

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/validate.py`, `plugins/nmg-game-dev-blender-addon/inspect_core/spatial.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `_mesh_findings` and `_measure` pass `obj.matrix_world` and the object's vertex-group names in index order.
- Both create the evaluated copy with `preserve_all_data_layers=True`, so deform weights are present.
- Finding annotations widen to `dict[str, Any]`.
- The spatial inspector's per-part `geometry` entries carry the same `count` and `samples` (AC6, FR6).
- `passed` and blocking results are unchanged (AC7).

### T003: Documentation

**File(s)**: `docs/skills/model-asset.md`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- The per-part `geometry` entry section documents `count` and `samples`, the sample fields (`index`, world-space `position`, `vertex_groups`, and `coincides_with` for duplicates), and the cap of 5 lowest indices (FR7).

### T004: Blender tests

**File(s)**: `tests/blender/test_contract_validate.py`, `tests/blender/test_inspect_spatial.py`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- Tests run in headless background Blender through `gate-blender-headless` and never connect to a live Blender session.
- SCN001: two closed boxes joined into one mesh, sharing one vertex position, each in its own vertex group. The object has a non-identity world transform (translated, rotated, and scaled). `geometry.duplicates` has the right `count`, and each sample has the duplicate `index`, `coincides_with`, a world `position` equal to `matrix_world @ co` within 1e-5, and `vertex_groups` naming both boxes' groups.
- SCN002: meshes with zero-area faces and with inward-flipped faces give face samples with the face center in world space and the vertex-group names.
- SCN003: loose vertices give vertex samples.
- SCN004: more than 5 offending elements give a full `count` and exactly the first 5 indices, and two runs give equal samples.
- SCN005: a defect on a mesh with no vertex groups gives empty `vertex_groups`.
- SCN006 (`test_inspect_spatial.py`): a part with a defect has `geometry` entries equal in `count` and `samples` to contract validation.
- SCN007: clean meshes give no geometry findings, and `passed` is unchanged.
- `gate-blender-headless`, `repository.tests`, `repository.lint`, `repository.format`, and `repository.types` pass.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #153 | 2026-11-11 | Initial feature tasks |
