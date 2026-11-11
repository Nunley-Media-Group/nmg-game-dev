# Defect Report: Meshy a-pose arm raise destroys legs on stylized characters

**Issue**: #135
**Date**: 2026-11-11
**Status**: Approved
**Author**: Claude Code
**Related Spec**: specs/106-raise-meshy-a-pose-arms-to-within-the-rig-humanoid-arm-drop-limit-on-import/

## Reproduction

1. Build an `a-pose` character with a large head, shoulders at about 0.6 of its height H, arms dropped about 55°, and a wide stance, boots, or a skirt that reaches more than 0.10·H from the midline.
2. Import it with `pose="a-pose"` through `import_glb` in `scripts/blender/meshy_session.py` (or a `generate_model` job).
3. Compare the imported `SM_<Name>` with the GLB, and read `arm_raise` in the result.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | Only arm vertices move. Each arm ends 48° below horizontal, measured from the character's real shoulder. Legs, boots, skirt, torso, and head keep the positions normalization gave them. The result reports where each shoulder and hand tip are. A caller can import an `a-pose` model with no raise. |
| **Actual** | The shoulder pivot is placed at fixed realistic-human proportions `(x_c ± 0.10·H, y_c, z_min + 0.81·H)`, inside the head of a stylized body. The drop is over-measured, the arms rise to a near T-pose, and leg, boot, and skirt vertices inside the 20° angular window rotate with the arms. No input turns the raise off. |

## Acceptance Criteria

### AC1: Legs, boots, and skirts do not move on a stylized character

**Given** an `a-pose` stylized character whose shoulders sit at about 0.6·H, whose arms drop about 55°, and whose wide-stance legs, boots, and skirt reach more than 0.10·H from the midline
**When** it is imported with the arm raise
**Then** every vertex of the legs, boots, skirt, torso, and head is where normalization left it, and only arm vertices have moved

### AC2: The arm is raised from the detected shoulder

**Given** the same stylized character
**When** it is imported with the arm raise
**Then** each side's `drop_before_deg` is the drop of the line from the detected shoulder to the hand tip (55° within 3°), `drop_after_deg` is 48° within 0.5°, and the arm is not raised above that

### AC3: The shoulder is found from the mesh

**Given** an `a-pose` character with a gap between each arm and the torso
**When** it is imported with the arm raise
**Then** each side's shoulder is taken from the armpit: the highest horizontal slice in which the torso and that arm are separate intervals that stay separate in the slices below it, and the reported shoulder lies within 0.03·H of the fixture's true shoulder

### AC4: Arm selection follows the arm and is limited by its length

**Given** an `a-pose` character with geometry that is outboard of the shoulder but not connected to the arm through the slices below the armpit, or farther from the shoulder than the arm's length
**When** it is imported with the arm raise
**Then** that geometry does not move, and every moved vertex lies within the arm's length of the detected shoulder

### AC5: The detected landmarks are reported

**Given** an `a-pose` import where a side's shoulder was detected
**When** the import result is read
**Then** that side of `arm_raise` holds `detected: true`, `shoulder` and `hand_tip` as world-space `[x, y, z]` in meters as they are after the raise, with the left side at x > 0 and the right at x < 0, both inside the mesh's bounding box, alongside `drop_before_deg`, `drop_after_deg`, and `rotation_deg`

### AC6: A side with no detectable shoulder is left untouched

**Given** an `a-pose` character with one arm fused to the torso, so no armpit exists on that side
**When** it is imported with the arm raise
**Then** the import succeeds, no vertex on that side moves, that side of `arm_raise` reports `detected: false` with `reason` `no_armpit` and `rotation_deg` 0, and the other side is still raised to 48° within 0.5°

### AC7: The raise can be skipped

**Given** an `a-pose` generate request with `raise_arms` false (`generate_model(raise_arms=False)` or CLI `generate --no-arm-raise`)
**When** the model is generated and imported
**Then** Meshy still receives `pose_mode` `a-pose`, the import still normalizes the mesh, no vertex is moved by an arm raise, and `arm_raise` is `null`

### AC8: Realistic humanoids still import correctly

**Given** the existing realistic-proportion `a-pose` box humanoid with arms dropped 55°
**When** it is imported with the arm raise
**Then** each arm ends at 48° within 0.5°, a side already at 48° or less keeps every vertex and still reports its shoulder, and vertex count, face count, connectivity, and face orientation are unchanged

### AC9: Other poses are unchanged

**Given** a `t-pose` import or an import with no pose
**When** it is imported
**Then** no vertex is moved by an arm raise and `arm_raise` is `null`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | The arm raise finds each shoulder from the mesh by armpit detection over horizontal slices, not from fixed bounding-box proportions | Must |
| FR2 | The arm raise selects the vertices to move by following the arm's slice intervals down from the armpit, not by an angular window around the pivot | Must |
| FR3 | No vertex farther from the detected shoulder than the arm's length (shoulder to hand tip) moves | Must |
| FR4 | The drop is measured from the detected shoulder to that arm's hand tip, and the raise targets 48° as today | Must |
| FR5 | Each side of `arm_raise` reports `detected`, the `shoulder` and `hand_tip` world-space points after the raise when detected, and a `reason` when not | Must |
| FR6 | A side with no detectable shoulder moves no vertex, and the import still succeeds | Must |
| FR7 | `generate_model` (`raise_arms`, default true) and the `generate` CLI command (`--no-arm-raise`) can turn the arm raise off for an `a-pose` import; the raise stays on by default | Must |
| FR8 | The raise stays vertex math only: no modifier, no armature, and unchanged topology | Must |
| FR9 | A stylized-character fixture (low shoulders, large head, wide stance, boots, skirt, detached outboard geometry) and a fused-arm fixture are added to the Blender tests next to `build_humanoid` | Must |
| FR10 | `docs/mcp/meshy.md` ("Pose", "Arm raise", "Status document", "CLI", "Tools") describes the detection, the new `arm_raise` fields, the undetected case, and the skip option | Must |

## Out of Scope

- Changing `rig_humanoid` pose limits or its landmark checks
- Detecting the other `rig_humanoid` landmarks (elbow, wrist, hip, knee, ankle, toe, pelvis, neck, head top)
- Passing the reported landmarks to `rig_humanoid` automatically
- Reposing legs, hands, or `t-pose` output
- Caller-supplied shoulder positions for the raise
- Repairing collections that were already imported with a bad raise

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #135 | 2026-11-11 | Initial defect report |
