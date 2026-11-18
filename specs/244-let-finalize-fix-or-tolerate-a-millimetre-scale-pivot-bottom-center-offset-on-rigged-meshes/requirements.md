# Defect Report: A millimetre-scale pivot offset on a rigged mesh blocks finalize

**Issue**: #244
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/140-fix-finalize-export-failing-the-contract-on-mobile-lods-the-variants-step-decimated/

## Reproduction

1. Make a rigged asset: armature `SK_<Name>` and mesh `SM_<Name>` with an Armature modifier, identity object transforms, and the rig at rest.
2. Translate the mesh data, not the object, so that the bounding-box bottom center sits at `(0.0006, 0.0013, -0.0007)`.
3. Run `finalize all`, or run contract validate on the collection.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | Authored validate accepts the offset on a rigged asset. The variants step moves the Desktop mesh data onto the origin, so both exported variants pass the pivot checks. |
| **Actual** | `pivot.bottom_center` fails on `SM_<Name>`, and no finalize step can fix it, so `finalize all` stops at validate. |

## Acceptance Criteria

### AC1: A millimetre-scale offset on a rigged mesh no longer blocks finalize

**Given** a rigged asset at rest whose skinned mesh has its bounding-box bottom center at `(0.0006, 0.0013, -0.0007)`
**When** authored validate runs, then the variants step
**Then** validate reports no `pivot.bottom_center` finding, and after the variants step the Desktop bottom center is within 1 mm of the world origin

### AC2: The re-seat moves only mesh data

**Given** the same asset, with a second skinned part `SM_<Name>_Part` parented to the root
**When** the variants step re-seats the Desktop mesh
**Then** only mesh data moves, and every part moves by the same world offset. The Armature modifiers, vertex groups and weights, the rig's bones, and every object transform are unchanged.

### AC3: A rigged asset already on the origin is left alone

**Given** a rigged asset whose bottom center is exactly on the origin
**When** the variants step runs
**Then** its Desktop mesh data is unchanged, and the step reports that no re-seat was needed

### AC4: A large offset still fails clearly

**Given** a rigged asset whose bottom center is 2 cm from the origin
**When** authored validate runs
**Then** `pivot.bottom_center` fails, and the finding states that finalize re-seats a rigged mesh only within 5 mm of the origin and that the mesh data must be moved closer

### AC5: Static assets keep their current behavior

**Given** a static asset with its bottom center 1.3 mm from the origin, and one 0.8 mm from it
**When** authored validate runs, then the variants step
**Then** the 1.3 mm asset fails `pivot.bottom_center` and the 0.8 mm asset passes. The static Desktop mesh data is not re-seated.

### AC6: Exported variants agree

**Given** the rigged asset from AC1
**When** the variants step runs, then export-time validate, export, and the re-import check
**Then** export-time validate reports no `pivot.bottom_center` finding, and the re-import check reports no pivot finding for either the Desktop or the Mobile variant

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Authored validation of a rigged asset (one whose collection holds an ARMATURE named `SK_<Name>`) allows the Desktop bottom center to be up to 5 mm from the origin on each axis. The origin itself, export-time validation, and static assets keep the 1 mm tolerance. | Must |
| FR2 | The variants step moves the Desktop mesh data of a rigged asset by the negative of the bottom-center offset, so the bottom center is on the world origin. It measures the box the pivot check measures, moves every Desktop part by the same world offset, and changes no origin, transform, modifier, vertex group, or bone. | Must |
| FR3 | The re-seat does nothing when the offset is exactly zero. The variants step reports whether it re-seated and by what offset. | Must |
| FR4 | The `pivot.bottom_center` remediation and `docs/asset-contract.md` section 2 state the 5 mm rigged allowance and that finalize re-seats within it | Must |
| FR5 | Blender headless tests cover AC1–AC6 | Must |

## Out of Scope

- Measuring a rig left in a non-rest pose (#236)
- Re-seating static Desktop meshes
- Moving object origins
- Adding a new finalize step

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #244 | 2026-11-18 | Initial defect report |
