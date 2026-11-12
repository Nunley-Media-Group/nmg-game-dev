# Tasks: Meshy a-pose arm raise destroys legs on stylized characters

**Issue**: #135
**Date**: 2026-11-11
**Status**: Approved
**Author**: Claude Code
**Related Spec**: specs/106-raise-meshy-a-pose-arms-to-within-the-rig-humanoid-arm-drop-limit-on-import/

## Implementation Tasks

### T001: Detect shoulders and track arms in the session arm raise

**File(s)**: `scripts/blender/meshy_session.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `_raise_arms` finds each side's armpit and shoulder from horizontal slices as in design.md, with no fixed shoulder proportions (`SHOULDER_HEIGHT`, `SHOULDER_HALF_WIDTH`, `ARM_CONE_EXTRA_DEG`, `_hand_tip` removed) (FR1).
- Vertices are selected by tracked slice intervals below the armpit plus the shoulder cap, and none farther than the arm length from the shoulder moves (FR2, FR3).
- The drop is measured shoulder → hand tip and raised to 48° with the existing blend; only vertex coordinates change (FR4, FR8).
- Each side reports `detected`, `shoulder`, `hand_tip`, drops, and `rotation_deg`; an undetected side reports `detected: false`, `reason: "no_armpit"`, null points and drops, `rotation_deg` 0, and moves no vertex (FR5, FR6).
- The raise runs only when `pose == "a-pose"` and `payload.get("raise_arms", True)` is true; otherwise `arm_raise` is `null`. The module docstring describes the new payload key and result fields.

### T002: Add the raise_arms skip option end to end

**File(s)**: `src/nmg_game_dev/meshy/request.py`, `src/nmg_game_dev/meshy/jobs.py`, `src/nmg_game_dev/meshy/session.py`, `src/nmg_game_dev/meshy/__main__.py`, `mcp-servers/meshy/src/meshy_mcp/server.py`, `mcp-servers/meshy/tools.json`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `GenerateRequest.raise_arms` defaults to `True`; `generate_model(raise_arms=...)` and CLI `generate --no-arm-raise` set it (FR7).
- The job stores `raise_arms` in `request.json` and passes it to `MeshySession.import_glb`, whose payload carries `"raise_arms": false` only when false.
- `pose_mode` sent to Meshy is unchanged by `raise_arms`.
- `tools.json` declares `raise_arms` as a boolean with default `true`; `uv run python scripts/validate-mcp-tools.py` (`gate-mcp-schema`) passes.

### T003: Add stylized and fused-arm fixtures

**File(s)**: `tests/meshy_arm_geometry.py`, `tests/blender/meshy_fixtures.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- A pure-Python geometry description of a stylized character: H = 1.8 m, shoulders at 0.6·H on the torso's outboard edge, a head wider than the torso whose bottom is above the shoulder cap, arms dropped 55° whose axes pass through the true shoulders, wide-stance legs, boots, and a skirt reaching more than 0.10·H from the midline, plus a detached box outboard of each arm below its hand tip; it exposes the true shoulders, hand tips, and the vertex positions of each non-arm part (FR9).
- A fused-arm variant in which the right arm touches the torso at every slice (no armpit) and the left arm keeps a gap (FR9).
- `tests/blender/meshy_fixtures.py` exports each as one GLB mesh next to `build_humanoid`, with symmetric X/Y extents so recentering moves nothing.
- `raise_arm_landmarks` accepts optional per-side pivots (default `side_pivot`) so landmarks can rotate about a reported shoulder.

### T004: Blender regression coverage for detection, selection, and reporting

**File(s)**: `tests/blender/test_meshy_session.py`
**Type**: Modify
**Depends**: T001, T003
**Acceptance**:
- AC1: importing the stylized fixture with `a-pose` leaves every leg, boot, skirt, torso, and head vertex at its normalized position, and some arm vertices move.
- AC2: each side's `drop_before_deg` is 55° within 3° and `drop_after_deg` is 48° within 0.5°, and no arm is raised above 48°.
- AC3: each reported shoulder lies within 0.03·H of the fixture's true shoulder.
- AC4: the detached boxes do not move, and every moved vertex lies within `|hand_tip − shoulder|` of the reported shoulder.
- AC5: each detected side reports `shoulder` and `hand_tip` as 3-float lists, left x > 0, right x < 0, both inside the imported mesh's bounding box, alongside the drop and rotation fields.
- AC6: the fused-arm fixture imports with `ok: true`; the right side reports `detected: false`, `reason: "no_armpit"`, `rotation_deg` 0, and none of its x < 0 vertices move; the left side ends at 48° within 0.5°.
- AC7 (session): `import_glb` with `pose: "a-pose"` and `raise_arms: false` returns `arm_raise: null` and the same positions as a no-pose import, with normalization applied.
- AC8: the existing box-humanoid tests still pass with the new report shape; a 45° side keeps every vertex and reports `detected: true` with its shoulder.
- AC9: the existing t-pose / no-pose test still asserts no movement and `arm_raise` null.
- Tests fail against the #106 implementation on the stylized fixture and pass with T001; evidence is `scripts/run-blender-tests.sh` (`gate-blender-headless`).

### T005: Unit coverage for the skip option

**File(s)**: `tests/unit/meshy/test_request.py`, `tests/unit/meshy/test_jobs.py`, `tests/unit/meshy/test_mcp_server.py`, `tests/meshy_fakes.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- AC7: `GenerateRequest(..., raise_arms=False)` validates; an `a-pose` job with `raise_arms=False` sends `pose_mode` `a-pose`, stores `raise_arms: false`, sends `"raise_arms": false` in the `import_glb` payload, and reports `arm_raise` null; the default job omits the key and reports `arm_raise`.
- The CLI `generate --no-arm-raise` builds a request with `raise_arms=False`; `generate_model` exposes `raise_arms` in its input schema.
- The fake session's `ARM_RAISE` carries `detected`, `shoulder`, and `hand_tip`, and returns `arm_raise` null when `raise_arms` is false.
- Evidence: `uv run pytest tests/unit tests/bdd -q` (`repository.tests`).

### T006: BDD scenarios for #135

**File(s)**: `tests/bdd/features/meshy.feature`, `tests/bdd/test_meshy_bdd.py`
**Type**: Modify
**Depends**: T004, T005
**Acceptance**:
- One scenario per AC1–AC9, tagged with the file's next free `@SCN` numbers and a comment mapping them to this spec's SCN001–SCN009.
- Geometry steps bind through `_blender_covers` to the T004 Blender tests; AC5 and AC7 steps also check the contract through the fakes; SCN018 (#106) is updated for the new `arm_raise` side keys, and SCN019's neutral-pose check rotates landmarks about the reported shoulders.
- Evidence: `uv run pytest tests/unit tests/bdd -q` (`repository.tests`).

### T007: Document detection, report fields, and the skip option

**File(s)**: `docs/mcp/meshy.md`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- "Pose" and "Arm raise" describe armpit detection, arm tracking, the arm-length limit, the 48° target, and the undetected side (FR10).
- The `arm_raise` field table lists `detected`, `shoulder`, `hand_tip`, `reason`, and the drop and rotation fields with their null cases.
- "Tools" and "CLI" show `raise_arms` / `--no-arm-raise`; "Status document" notes `arm_raise` is null when the raise is skipped.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #135 | 2026-11-11 | Initial defect tasks |
