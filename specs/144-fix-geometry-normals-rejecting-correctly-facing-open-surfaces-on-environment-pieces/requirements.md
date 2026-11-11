# Defect Report: geometry.normals rejects correctly facing open surfaces

**Issue**: #144
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Reproduction

1. Author an `environment_piece` collection containing a mesh object with a single upward-facing quad (a floor), away from the origin, for example spanning (3.37, -2.11, 0.4) to (7.9, 1.63, 0.4). Try several placements.
2. Add an object made of a floor quad and a back-wall quad sharing one edge, both facing into the room.
3. Run the validate contract operator, or the finalize `validate` step, on the collection.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | Open-sheet islands whose faces are wound consistently produce no `geometry.normals` finding wherever they sit. Closed islands are still required to face outward. |
| **Actual** | Validation fails with `geometry.normals` ("<object> has N face(s) whose normals are inconsistent or inward.") for some placements of the single quad, and always for the floor-plus-wall sheet. The remediation tells the author to recalculate normals outside. |

## Acceptance Criteria

### AC1: A correctly facing single open quad passes wherever it sits

**Given** a mesh that is one planar quad (floor, roof plane, decal, or ground sheet), axis-aligned or tilted, at any position relative to the object origin
**When** the geometry checks run on it
**Then** no `geometry.normals` finding is reported, and the result is the same for every placement

### AC2: A consistently wound open sheet passes regardless of which way it faces

**Given** an open-sheet island of several connected faces wound consistently, such as a floor and back wall facing into a room or a welded grid ground sheet
**When** the geometry checks run on it
**Then** no `geometry.normals` finding is reported

### AC3: Inconsistent winding inside an open sheet is still reported

**Given** an open-sheet island in which one face is wound opposite to its neighbours
**When** the geometry checks run on it
**Then** a `geometry.normals` finding is reported for the object and its count covers the inconsistent face(s)

### AC4: Closed islands are still required to face outward

**Given** a closed island with one face flipped, or a closed island turned entirely inside out
**When** the geometry checks run on it
**Then** a `geometry.normals` finding is reported, as today

### AC5: Islands are judged independently

**Given** one mesh containing a correct closed box, a correct open floor quad, and a closed box with one flipped face
**When** the geometry checks run on it
**Then** exactly the flipped face of the defective box is counted in the `geometry.normals` finding

### AC6: Welded touching closed primitives pass

**Given** two correctly facing closed boxes that touch at a vertex, along an edge, or across part of a face, merged by distance into one mesh
**When** the geometry checks run on it
**Then** no `geometry.normals` finding is reported

### AC7: Remediation text fits open surfaces

**Given** a `geometry.normals` finding
**When** the report is produced
**Then** its remediation no longer tells the author to blanket-recalculate normals outside for open surfaces; it distinguishes closed parts (face outward) from open sheets (wind consistently, face the viewer)

### AC8: The authoring rule is documented

**Given** an author building an `environment_piece` from many primitives
**When** they read `docs/asset-contract.md` §3 and the `/model-asset` skill
**Then** both state what the validator accepts:
- open sheets are allowed where nothing sees underneath, and must be wound consistently and face the viewer;
- closed parts must face outward;
- touching primitives must either be merged so they share vertices, or kept from sharing vertex positions (for example with a gap of about 0.6 mm), because coincident unmerged vertices raise `geometry.duplicates`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `geometry.normals` evaluates each connected island of a mesh separately. | Must |
| FR2 | An island with boundary edges (an open sheet) is checked only for consistent winding between neighbouring faces, never for outward versus inward orientation. | Must |
| FR3 | A closed island keeps the current requirement: every face points outward. | Must |
| FR4 | The result for a mesh does not depend on its position or on the positions of other islands in the same mesh. | Must |
| FR5 | The rule id `geometry.normals`, the finding shape, and both callers (`contract_core/validate.py`, `inspect_core/spatial.py`) keep working unchanged; the check still never mutates the scene. | Must |
| FR6 | Regression tests cover AC1–AC6, including position-varied single quads and welded touching boxes. | Must |
| FR7 | The `geometry.normals` remediation text in `contract_core/report.py` is updated per AC7. | Must |
| FR8 | `docs/asset-contract.md` §3, `skills/model-asset/SKILL.md`, and `docs/skills/model-asset.md` document the environment-piece authoring rule per AC8 and describe `geometry.normals` as it now behaves. | Must |

## Out of Scope

- An explicit per-asset "open surface" marker or any other opt-out property.
- Detecting an open sheet that is consistently wound but faces away from the viewer.
- Changing `geometry.duplicates`, `geometry.loose`, or `geometry.zero_area`, or the `/model-asset` `non_manifold` finding.
- Changing the cleanup steps that call `recalc_face_normals` (`variants_core/cleanup.py`, `scripts/blender/meshy_session.py`).

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #144 | 2026-11-11 | Initial defect report |
