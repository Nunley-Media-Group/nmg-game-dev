# Requirements: estimate_landmarks proposes rig_humanoid landmarks from the mesh

**Issue**: #137
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As an** agent rigging a cast of generated humanoid characters
**I want** `estimate_landmarks(collection)` to propose the 19 `rig_humanoid` landmarks from the mesh
**So that** I only review and correct the landmarks instead of working out every point by hand

## Background

`rig_humanoid(collection_name, body_type, landmarks)` in `plugins/nmg-game-dev-blender-addon/rig_core/rig.py` validates 19 world-space landmarks (`LANDMARK_KEYS` in `rig_core/skeleton.py`) and builds `SK_<Name>`. Nothing in `rig_core` proposes landmarks.

Two `rig_humanoid` defects block a script that places a character and rigs it in one go:

- `_mesh_bounds` reads `matrix_world`, which Blender does not recompute after a transform change until the view layer updates, so a mesh moved in the same script is checked at its old position.
- The `rig.asset_not_found`, `rig.landmarks_outside_mesh`, and `rig.weights_failed` texts print the literal `SM_<Name>` / `<Name>`.

The character faces −Y, with its left side at +X.

## Acceptance Criteria

### AC1: Landmarks are proposed for an A-pose humanoid

**Given** a collection `<Name>` holding a symmetric A-pose humanoid `SM_<Name>` with known joint positions
**When** the agent calls `estimate_landmarks("<Name>")`
**Then** the result has `status` `ok`, `confidence` `high`, an empty `warnings` list, and `landmarks` with all 19 keys as `[x, y, z]` in meters, world space
**And** each landmark is within 5% of the character's height of its known joint position
**And** each `_l` landmark has x > 0 and each `_r` landmark has x < 0

### AC2: A high-confidence proposal rigs without edits

**Given** the `landmarks` from a `high` confidence result
**When** the agent passes them unchanged to `rig_humanoid("<Name>", "humanoid", landmarks)`
**Then** `rig_humanoid` returns `status` `ok`

### AC3: Stylized proportions and accessories do not mislead it

**Given** an A-pose stylized character with a large head, shoulders at about 0.6 of its height, and a hat brim, earrings, or glasses that stick out sideways above the shoulders
**When** the agent calls `estimate_landmarks`
**Then** the shoulders are placed at the arms, not at the accessory
**And** the result meets AC1

### AC4: An asymmetric stance is reported as low confidence

**Given** an A-pose humanoid whose legs or arms are not mirrored across X to within 5% of its height
**When** the agent calls `estimate_landmarks`
**Then** the result has `status` `ok` and `confidence` `low`
**And** `landmarks` holds all 19 keys as measured on each side, not mirror-averaged
**And** `warnings` names each asymmetric left/right pair

### AC5: A mesh with no A-pose arms or no legs is a failure, not a guess

**Given** a mesh in which no arm can be followed downward from an armpit on both sides (a T-pose, or arms fused to the torso), or in which no crotch is found
**When** the agent calls `estimate_landmarks`
**Then** the result has a failure `status`, the code `rig.arms_not_found` or `rig.crotch_not_found`, a `message` naming what was not found, and a `remediation`
**And** it has no `landmarks`

### AC6: A missing mesh is reported

**Given** a collection name that does not exist, or a collection with no root mesh `SM_<Name>`
**When** the agent calls `estimate_landmarks`
**Then** the result is the `rig.asset_not_found` failure and its message names the expected mesh `SM_<Name>` with the real name

### AC7: Estimating changes nothing

**Given** any collection
**When** `estimate_landmarks` returns, with any status
**Then** the scene's objects, mesh data, transforms, selection, active object, and mode are unchanged

### AC8: rig_humanoid uses the mesh's current position

**Given** `SM_<Name>` moved, rotated, or scaled in a script with no view-layer update afterwards
**When** the same script calls `rig_humanoid` with landmarks that are correct for the new position
**Then** `rig_humanoid` returns `status` `ok`
**And** `estimate_landmarks` called at that point returns landmarks at the new position

### AC9: rig_humanoid messages name the mesh

**Given** a collection `Hero`
**When** `rig_humanoid` fails with `rig.asset_not_found`, `rig.landmarks_outside_mesh`, or `rig.weights_failed`
**Then** the `message` and `remediation` say `SM_Hero` and `Hero`
**And** no result contains the literal text `SM_<Name>` or `<Name>`

### AC10: The agent flow is documented

**Given** `docs/rigging-and-animation.md`
**When** an agent reads the flow
**Then** it says to call `estimate_landmarks`, review and correct the proposal, and then call `rig_humanoid`
**And** it documents the result fields, the confidence values, the A-pose limit, and the failure codes

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `rig_core` exports `estimate_landmarks(collection_name)`, which returns a result dict in the same `status` / `code` / `message` / `remediation` shape as the other `rig_core` functions | Must |
| FR2 | A successful result carries `landmarks` (all 19 `LANDMARK_KEYS`, world space, meters), `confidence` (`high` or `low`), and `warnings` (a list, empty when confidence is high) | Must |
| FR3 | Landmarks are found by slicing: cut the mesh into 200 horizontal slices and split each slice's x-values into intervals at gaps larger than 0.012 of the height | Must |
| FR4 | The crotch is the lowest slice, between 15% and 70% of the slices, where one interval spans the midline and continues to do so for the next 6 slices above it | Must |
| FR5 | The armpit is the highest slice below 92% of the slices with a central torso interval plus a separate interval on each side from which an arm can be followed downward, slice to slice by overlap, for at least 12% of the slices | Must |
| FR6 | Shoulder, elbow, wrist, and hand tip come from an axis fitted through the arm-interval centres | Must |
| FR7 | The neck is the narrowest central interval above the shoulders; hips, knees, ankles, and toes come from the leg intervals below the crotch | Must |
| FR8 | An asymmetric left/right pair lowers confidence to `low` and adds a warning naming the pair; landmarks are returned as measured | Must |
| FR9 | No arm on both sides, or no crotch, returns a failure result with no landmarks | Must |
| FR10 | `estimate_landmarks` does not modify the scene | Must |
| FR11 | `rig_humanoid` and `estimate_landmarks` read mesh transforms that are current at call time, with no view-layer update needed from the caller | Must |
| FR12 | Every `rig_humanoid` failure message and remediation substitutes the real collection and mesh names | Must |
| FR13 | `docs/rigging-and-animation.md` documents the estimate, review, rig flow and the new function's contract | Must |

## Out of Scope

- T-pose estimation
- Quadruped and other non-biped bodies
- A Blender operator or panel button for the estimate
- `rig_humanoid` estimating landmarks itself when none are supplied
- Any change to `rig_humanoid`'s symmetry, vertical-order, or pose limits
- Finger, face, or twist-bone landmarks
- Changes to the Meshy import arm raise (#135)

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #137 | 2026-11-11 | Initial feature spec |
