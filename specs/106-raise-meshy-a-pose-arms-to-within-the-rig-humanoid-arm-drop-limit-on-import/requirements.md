# Requirements: Raise Meshy A-pose arms to within the rig_humanoid arm-drop limit on import

**Issue**: #106
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/98-add-optional-meshy-model-generation-and-retexturing-through-the-meshy-api/

## User Story

**As an** agent rigging a Meshy-generated humanoid
**I want** A-pose imports adjusted so the arms fall within `rig_humanoid`'s neutral-pose limit
**So that** `rig_humanoid` accepts truthful shoulder and wrist landmarks without hand reposing

## Background

Meshy's `a-pose` output drops the arms about 55° below horizontal. `rig_humanoid` rejects arms dropped more than 50° (`_MAX_ARM_DROP_DEG` in `rig_core/landmarks.py`) with `rig.pose_not_neutral`, measuring elevation along the shoulder-to-wrist line. The validator stays as it is. Instead, the Meshy import raises each arm about its shoulder to a 48° target, which leaves 2° of margin. The Meshy generate job takes `pose` (`a-pose` | `t-pose`) and passes it to the API as `pose_mode`. `scripts/blender/meshy_session.py` `import_glb` makes no pose adjustment today.

The shoulder and hand are found from the mesh's own world bounding box (height `H`, floor `z_min`, midline `x_c` and `y_c`):

- **Hand tip (per side):** the vertex with the largest `x` (left, +X) or smallest `x` (right, −X).
- **Shoulder pivot (per side):** `(x_c ± 0.10·H, y_c, z_min + 0.81·H)`.
- **Arm drop:** the angle below horizontal of the line from the pivot to the hand tip.

## Acceptance Criteria

### AC1: Steep A-pose is raised

**Given** a generate job with `pose: a-pose` whose imported mesh has an arm drop greater than 48° on either side
**When** the import completes
**Then** each side whose drop exceeds 48° is rotated up about its shoulder pivot, around the front-to-back (Y) axis, so its drop is 48° ± 0.5°. Vertices within `0.10·H` of the midline, and vertices outside that side's arm region, do not move. The rotation blends linearly over the next `0.04·H` outward, so the vertex and face counts and connectivity are unchanged and no face's normal flips direction

### AC2: Compliant poses untouched

**Given** a generate job with `pose: t-pose`, with no pose, or with `pose: a-pose` and a drop of 48° or less on a side
**When** the import completes
**Then** no vertex on that side moves

### AC3: Result reports the adjustment

**Given** an A-pose import
**When** the import result and the job result are read
**Then** both carry `arm_raise` with `left` and `right`, each holding `drop_before_deg`, `drop_after_deg`, and `rotation_deg` (0 when skipped). Non-A-pose imports carry `arm_raise: null`

### AC4: Rigs afterward

**Given** an adjusted A-pose humanoid whose shoulder landmarks are at the pivots and whose wrist landmarks lie on the raised arms
**When** `rig_core.landmarks.validate("humanoid", landmarks, bbox)` runs
**Then** it does not return `rig.pose_not_neutral`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Measure each arm's drop on A-pose imports with the pivot and hand-tip rule above | Must |
| FR2 | Rotate arm vertices about the shoulder pivot with a linear blend over `0.04·H`, to a 48° drop | Must |
| FR3 | Report `arm_raise` per side in the `import_glb` and generate-job results, and document it in `docs/mcp/meshy.md` | Must |

## Out of Scope

- Changing `rig_humanoid` pose limits
- Reposing legs, hands, or T-pose output
- Agent-supplied shoulder or wrist positions for the raise

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #106 | 2026-10-31 | Initial feature spec |
