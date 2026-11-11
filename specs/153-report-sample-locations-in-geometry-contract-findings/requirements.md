# Requirements: Report sample locations in geometry contract findings

**Issue**: #153
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As a** developer fixing an asset that fails a geometry contract check
**I want** each geometry finding to say where the offending elements are
**So that** I can go straight to the problem in Blender without writing a custom script

## Background

`geometry_findings(name, mesh)` in `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py` builds a bmesh from an evaluated mesh copy. It emits `geometry.loose`, `geometry.zero_area`, `geometry.duplicates` (via `bmesh.ops.find_doubles`), and `geometry.normals`. Each finding is `{rule, target, message, remediation}`, built by `contract_core/report.py::finding`, and its message carries only a count. The function receives no world transform.

Two callers hold the source object when they call it:
- `contract_core/validate.py::_mesh_findings`, the contract validation that finalize uses;
- `inspect_core/spatial.py`, which builds the per-part `geometry` list of the `/model-asset` spatial inspector.

An asset assembled from many closed primitives joined into one mesh makes a bare count hard to act on. A few located samples per finding, capped so reports stay small, let the developer go straight to the problem.

## Acceptance Criteria

### AC1: Duplicate-vertex finding locates the duplicates

**Given** a mesh object with a non-identity world transform, built from two closed boxes joined into one mesh that share one vertex position, with each box's vertices assigned to its own vertex group
**When** contract validation runs on the asset
**Then** the `geometry.duplicates` finding carries a `count` equal to the number of duplicate vertices, and a `samples` list whose entries each give:
- the world-space `position` of a duplicate vertex;
- its vertex `index`;
- the index of the vertex it coincides with (`coincides_with`);
- the vertex-group names of the coincident pair, which name both boxes' groups

### AC2: Face findings locate the faces

**Given** a mesh with zero-area faces and a mesh with inward-flipped faces
**When** contract validation runs
**Then** the `geometry.zero_area` and `geometry.normals` findings each carry `count` and `samples`, whose entries give the face `index`, the world-space `position` of the face center, and the vertex-group names of the face's vertices

### AC3: Loose-vertex finding locates the vertices

**Given** a mesh with loose vertices
**When** contract validation runs
**Then** the `geometry.loose` finding carries `count` and `samples` with each loose vertex's `index`, world-space `position`, and vertex-group names

### AC4: Samples are capped and deterministic

**Given** a mesh with more than 5 offending elements for a geometry rule
**When** contract validation runs twice on the unchanged asset
**Then** the finding's `count` is the full number of offending elements, `samples` holds exactly the first 5 by ascending element index, and both runs produce identical samples

### AC5: Elements outside any vertex group

**Given** a mesh with a geometry defect and no vertex groups
**When** contract validation runs
**Then** each sample's vertex-group list is empty and the finding is otherwise complete

### AC6: Spatial inspector carries the same detail

**Given** an asset part with a geometry defect
**When** the `/model-asset` spatial inspector reports that part
**Then** the part's `geometry` entries carry the same `count` and `samples` fields as contract validation

### AC7: Clean meshes are unchanged

**Given** a mesh with no geometry defects
**When** contract validation and the spatial inspector run
**Then** no geometry findings are emitted, and pass/fail results are unchanged from today

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `geometry.loose`, `geometry.zero_area`, `geometry.duplicates`, and `geometry.normals` findings add `count` (total offending elements) and `samples` (list), keeping `rule`, `target`, `message`, and `remediation` | Must |
| FR2 | Each sample gives the element `index` (vertex for loose and duplicates, face for zero_area and normals), its world-space `position` as three floats (vertex position or face center), and the sorted names of the vertex groups its vertices belong to | Must |
| FR3 | A duplicate-vertex sample also gives `coincides_with`, the index of the vertex the duplicate coincides with, and its vertex groups cover both vertices of the pair | Must |
| FR4 | `samples` is capped at 5, chosen as the lowest element indices, so output is deterministic | Must |
| FR5 | The finding `message` keeps the count and names the first sample's world-space position | Should |
| FR6 | The spatial inspector's per-part `geometry` entries carry the same fields as contract validation | Must |
| FR7 | `docs/skills/model-asset.md` documents `count` and `samples` on the geometry entries | Must |

## Out of Scope

- Changing the detection thresholds (`DUPLICATE_DISTANCE`, `ZERO_AREA_LIMIT`) or which elements count as defects.
- Automatically fixing or selecting the offending elements in Blender.
- Location samples for non-geometry rules (UV, material, budget, naming, and the spatial inspector's blocking rules).
- A configurable sample cap.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #153 | 2026-11-11 | Initial feature spec |
