# Tasks: Built-in procedural clip library for import_animations

**Issue**: #136
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Pure pose solver

**File(s)**: `plugins/nmg-game-dev-blender-addon/rig_core/procedural.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- No `bpy` or `mathutils` import.
- `RestSkeleton` holds each Manny bone's rest 3×3, parent, and head, plus the leg length as the mean over both sides of thigh plus calf length.
- `solve(rest, pose)` walks `MANNY_BONES` parent first:
  - `dir` bones use the minimal rotation onto the target direction;
  - `rot` bones apply the character-space Euler;
  - other bones inherit.
- It returns local quaternions by `rest⁻¹ · parentAcc⁻¹ · boneAcc · rest`, and the pelvis location as `off` × leg length in the pelvis's local frame (FR3, FR4).
- `continuous` keeps quaternion sign continuity.

### T002: Built-in clip definitions

**File(s)**: `plugins/nmg-game-dev-blender-addon/rig_core/builtin_clips.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- No `bpy` import.
- `AUTHORED_FPS = 30`.
- `pose`, `merge`, `mirror`, `expand`, and `clip_digest` behave as the design describes.
- `BUILTIN_CLIPS` holds Idle, FightIdle, Walk, Run, Punch1, Punch2, Punch3, Kick, Jump, JumpKick, Hit, Knockdown, Down, GetUp, Grab, GrabKnee, Throw, Held, Roar, Special, Talk, Ride, RideKickL, and RideKickR (FR2).
- Every targeted bone is a Manny bone.
- `Walk` and `Run` are mirrored half cycles. `Idle`, `FightIdle`, `Walk`, and `Run` loop.
- `Jump` and `Down` have a non-zero pelvis `off` (FR5–FR7).

### T003: Built-in library in import_animations

**File(s)**: `plugins/nmg-game-dev-blender-addon/rig_core/retarget.py`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- `import_animations(collection_name, library_dir=None, clips=None, motion_prompt=None, *, library=None)`. The existing positional file calls and file-clip provenance are unchanged (AC11, FR11).
- Checks run in this order: motion prompt, then library selection (`anim.library_invalid` before any scene change), then rig.
- An unknown built-in clip fails with `anim.clip_not_found`, its remediation listing every built-in name, and nothing is baked (AC9, AC10, AC12, FR8, FR10).
- `bake_builtin_clip` keys the solver output at `round(frame × fps / 30)`, with sign continuity, on targeted bones only. It installs the action by clip name with the existing replace logic, leaves no temporary action, opens no file, and resets the rig to rest (AC1, AC3, AC8, FR1, FR5, FR13).
- Provenance `source` = `{"library": "builtin", "file": null, "sha256": clip_digest, "skeleton": "manny"}`, stored with file-clip provenance (AC7, FR9).

### T004: Operator library selection

**File(s)**: `plugins/nmg-game-dev-blender-addon/operators/import_animations.py`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- `library_source` enum `FOLDER` (default) or `BUILTIN`. `BUILTIN` calls `import_animations` with `library="builtin"` and no folder.
- The result is stored on `scene.nmg_game_dev.last_result`, and the operator returns `FINISHED` on `ok` (AC13, FR12).

### T005: Documentation

**File(s)**: `docs/rigging-and-animation.md`, `docs/asset-contract.md`
**Type**: Modify
**Depends**: T003, T004
**Acceptance**:
- `docs/rigging-and-animation.md` documents `library="builtin"`, every built-in clip name, subset selection, the `anim.library_invalid` cases, the operator's library choice, and that clips play in place.
- `docs/asset-contract.md` states that a built-in clip's `source` has `library` `"builtin"`, `skeleton` `"manny"`, `file` `null`, and the definition's SHA-256 (FR14).

### T006: Unit tests for the pure solver and definitions

**File(s)**: `tests/unit/test_builtin_clips.py`
**Type**: Create
**Depends**: T001, T002
**Acceptance**:
- `procedural.py`, `builtin_clips.py`, and `skeleton.py` load under plain CPython. A synthetic package module whose `__path__` is `rig_core/` is registered in `sys.modules`, so `rig_core/__init__.py` and `bpy` are never imported.
- On two synthetic rest skeletons (T-pose, and arms 45° below horizontal with different limb lengths), every `dir` bone's solved world Y axis matches its target within 2° for every key of every clip (AC4).
- The pelvis location equals `off` × each skeleton's leg length (AC5).
- `expand` gives a mirrored second half for `Walk` and `Run`, and last pose = first pose for the four looping clips (AC6).
- `clip_digest` is stable across calls and changes when a pose changes (AC7, AC8).
- Every AC2 name is present (AC2).
- Runs in `repository.tests`.

### T007: Blender tests on two rigs

**File(s)**: `tests/blender/rig_fixtures.py`, `tests/blender/test_rig_builtin_clips.py`, `tests/blender/test_rig_operators.py`
**Type**: Create, Modify
**Depends**: T003, T004
**Acceptance**:
- `rig_fixtures.py` adds a second humanoid builder with different limb lengths and shoulder width and arms 45° below horizontal. Both rigs are built with `rig_humanoid`.
- Tests run in headless background Blender through `gate-blender-headless` and never connect to a live Blender session.
- SCN001–SCN012 cover AC1–AC12 on both rigs, each with the oracle stated in the scenario: keyframes on the targeted bones, rest pose after the bake, and no file access (asserted by patching `open` / `Path.read_bytes` during the bake).
- The AC4 2° direction check and the AC5 pelvis check run on the evaluated pose at each key frame.
- AC7 runs through the `export_rigged` sidecar and the FBX re-import action list. AC8 compares a second bake for identical keys and provenance, with no leftover `__nmg_tmp_` actions.
- AC11 mixes the existing `build_library` file clips with built-in clips.
- `test_rig_operators.py` adds SCN013 for the operator with `library_source="BUILTIN"` (AC13).
- `gate-blender-headless`, `repository.tests`, `repository.lint`, `repository.format`, and `repository.types` pass.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #136 | 2026-11-11 | Initial feature tasks |
