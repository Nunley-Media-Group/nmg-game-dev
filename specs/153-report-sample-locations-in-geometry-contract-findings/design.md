# Design: Report sample locations in geometry contract findings

**Issue**: #153
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Overview

`geometry_findings` collects the offending element indices it already computes, rather than just counting them. It then turns the lowest five into located samples using the source object's world matrix and vertex-group names, which the two callers now pass in. The fields are additive, and detection and `passed` are unchanged.

## Architecture

### `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py`

- **Signature.** `geometry_findings(name, mesh, matrix_world=None, group_names=())`.
  - `matrix_world` is the source object's 4×4 world matrix (`mathutils.Matrix`). `None` means identity.
  - `group_names` lists the source object's vertex-group names in index order.
  - Positional `(name, mesh)` calls keep working.
- `SAMPLE_LIMIT = 5`.
- **Offending indices**, each a sorted list:
  - loose: vertex indices with no linked edges;
  - zero area: face indices with `calc_area() < ZERO_AREA_LIMIT`;
  - duplicates: `find_doubles` `targetmap` pairs `(vert.index, target.index)`, sorted by `vert.index`;
  - normals: the normals helper returns the sorted face indices it counts. Today that is the faces `recalc_face_normals` turns around. Under #144's per-island rule it is each open island's minority faces plus the closed islands' turned faces. The count is the length of the list.
- **Samples.** One `_sample(...)` per element, for the first `SAMPLE_LIMIT` entries only.
  - `index`.
  - `position`: `matrix_world @ vert.co` for a vertex, or `matrix_world @ face.calc_center_median()` for a face. It is a list of three floats rounded to 6 decimals.
  - `vertex_groups`: sorted unique names, resolved from the bmesh deform layer (`bm.verts.layers.deform.active`) against `group_names`. It is empty when the mesh has no deform layer or no groups (AC5).
    - For a face, the names cover the face's vertices.
    - For a duplicate, they cover both the duplicate and the vertex it coincides with.
  - A duplicate sample also carries `coincides_with` (FR3).
- **Finding.** It is `finding(rule, name, message) | {"count": n, "samples": samples}`.
  - The message keeps today's count wording and appends `; first at (x, y, z)` with 4-decimal coordinates (FR5).
  - The finding is emitted only when `n > 0`, so clean meshes are unchanged (AC7).
- The return type widens from `list[dict[str, str]]` to `list[dict[str, Any]]`.

### Callers

- `contract_core/validate.py::_mesh_findings` calls `geometry_findings(obj.name, copy, obj.matrix_world, [group.name for group in obj.vertex_groups])`. Its `findings` annotations widen to `dict[str, Any]`.
- `inspect_core/spatial.py::_measure` makes the same call, so a part's `geometry` entries carry the same fields (AC6).
- Both callers create the evaluated copy with `bpy.data.meshes.new_from_object(..., preserve_all_data_layers=True, depsgraph=depsgraph)`, so deform weights reach the copy. Detection does not change, because the checks read only positions, edges, and faces.

### Report

`contract_core/report.py` and `build_report` stay as they are. Findings already serialize as plain JSON, and `passed` stays true exactly when there are no findings.

### Docs (`docs/skills/model-asset.md`)

- The geometry-entry section documents `count` and `samples`.
- It lists each sample's fields: `index`, world-space `position`, `vertex_groups`, and `coincides_with` for duplicates.
- It states the cap of 5, lowest indices first.

## Data Flow

```
_mesh_findings / _measure (source obj)
  → evaluated copy (deform layers preserved)
  → geometry_findings(name, copy, obj.matrix_world, group names)
  → offending index lists
  → first 5 → located samples
  → finding + count + samples
```

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Union of both vertices' groups for a duplicate sample | Selected | Names both boxes' groups, as AC1 requires, in one field |
| Separate `coincides_with_vertex_groups` field | Rejected | Two fields for one pair; FR2 asks for one group list per sample |
| Local-space positions | Rejected | The issue requires world space; both callers have the object |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #153 | 2026-11-11 | Initial feature design |
