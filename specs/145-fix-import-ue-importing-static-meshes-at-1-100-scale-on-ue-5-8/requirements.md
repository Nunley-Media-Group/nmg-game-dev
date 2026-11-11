# Defect Report: import_ue imports static meshes at 1/100 scale on UE 5.8

**Issue**: #145
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt/

## Reproduction

1. Use a UE 5.8 project onboarded with nmg-game-dev, with Interchange FBX import at its default.
2. In Blender, author a non-rigged collection with two or more parts. Make at least one part larger than one metre and place its origin away from the asset origin.
3. Run finalize so `import_ue` runs.
4. Observe `import_ue.pivot_mismatch` with a measured value 1/100 of the expected one, for example `min on axis 0 is -8.0000 cm; the Blender part expects -799.9987 cm`.
5. Name one part's mesh datablock `SM_<Name>_<Part>.001` and run finalize again. Observe that no static mesh named `SM_<Name>_<Part>` is reported.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | A static import arrives at the authored size: each static mesh's local bounds match the Blender part's local bounds in centimetres within 0.01 cm. Each part keeps its own pivot. Each static mesh is named after its part object. A reimport over an existing asset reports the bounds of the new geometry. |
| **Actual** | Every static mesh is 1/100 of its authored size and the pivot check fails. Static meshes are named after mesh datablocks, so a part whose datablock name differs from its object name is missing from the result. |

## Acceptance Criteria

### AC1: Static meshes import at the authored size

**Given** a non-rigged asset exported by finalize, with a part larger than one metre
**When** `import_ue` imports a variant on UE 5.8
**Then** each static mesh's local bounds equal the Blender part's local bounds in centimetres within 0.01 cm
**And** the pivot check passes

### AC2: Part pivots are preserved on a multi-part asset

**Given** a non-rigged asset with two or more parts whose origins are away from the asset origin
**When** `import_ue` imports a variant
**Then** each static mesh's bounds are relative to its own part origin, as in Blender
**And** no part's translation is baked into its vertices

### AC3: Static meshes are named after part objects

**Given** a part object `SM_<Name>_<Part>` whose mesh datablock has a different name, such as `SM_<Name>_<Part>.001`
**When** `import_ue` imports the variant
**Then** the result holds a static mesh named `SM_<Name>_<Part>` (the export name with `_Mobile` removed for the Mobile variant)
**And** every snapshot part has a static mesh

### AC4: A reimport reports the new geometry

**Given** a destination folder that already holds the asset's static meshes from an earlier import, including one made at 1/100 scale
**When** `import_ue` imports the variant again
**Then** the reported bounds and the saved assets' bounds are those of the new import at the authored size
**And** the pivot check passes

### AC5: Desktop and Mobile both import correctly

**Given** a non-rigged multi-part asset
**When** finalize runs `import_ue` for both variants
**Then** AC1, AC2, and AC3 hold for the Desktop variant and for the Mobile variant

### AC6: Rigged imports are unchanged

**Given** a rigged character
**When** `import_ue` imports its Desktop and Mobile variants
**Then** the Skeletal Mesh import options and code path are the same as before this fix, so the mesh arrives at the size it has today
**And** the pivot check passes

### AC7: An end-to-end test covers a multi-part static asset

**Given** a fixture collection with two or more parts, each away from the origin and at least one larger than a metre, that a checked-in builder script produces in headless Blender without a manual step
**When** a developer runs `pytest tests/e2e --runslow` against live Blender and UE 5.8
**Then** the test runs finalize on that fixture and asserts that both variants import, that there is one static mesh per part named after its object, and that the pivot check passes
**And** without `--runslow` the test is collected and skipped, so it never runs in the default suite or a registered gate

### AC8: Other import behavior is preserved

**Given** any static asset
**When** `import_ue` imports it
**Then** texture settings, `MI_<Name>_<Part>` creation and binding, the `NMG_RESULT` schema, the error codes, and the 0.01 cm pivot tolerance are as they are today

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | A static import applies the FBX unit conversion, so mesh geometry is in centimetres at the authored size | Must |
| FR2 | Each part of a multi-part static asset keeps its own pivot; part translation is not baked into vertices | Must |
| FR3 | Each static mesh asset is named after its part object's export name, whatever the mesh datablock is called | Must |
| FR4 | After a reimport over existing assets, the reported and saved bounds are those of the new import | Must |
| FR5 | The fix works with Interchange FBX import at its default and does not read or set `Interchange.FeatureFlags.Import.FBX` | Must |
| FR6 | The exported FBX stays valid for the rigged path; rigged import size and behavior do not change | Must |
| FR7 | The pivot tolerance stays 0.01 cm and the `NMG_RESULT` schema and error codes do not change | Must |
| FR8 | An opt-in (`--runslow`) e2e test with a generated multi-part fixture (parts away from the origin, at least one larger than a metre) checks size, pivots, and naming on both variants | Must |
| FR9 | Unit tests assert the static import options and post-import steps the fix settles on | Must |

## Out of Scope

- Resolving imported meshes when the import task lists only the first one (#141)
- Renaming mesh datablocks at export and the validate finding for a datablock shared between parts (#142)
- Supporting the legacy FBX importer
- Changing the scale of rigged (skeletal) imports
- Animation clip import through finalize (#138)

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #145 | 2026-11-11 | Initial defect report |
