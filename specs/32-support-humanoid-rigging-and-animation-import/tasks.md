# Tasks: Humanoid rigging and animation import

**Issue**: #32
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Pure-Python skeleton, landmarks, library, and outcome modules

**File(s)**: `plugins/nmg-game-dev-blender-addon/rig_core/outcome.py`, `plugins/nmg-game-dev-blender-addon/rig_core/skeleton.py`, `plugins/nmg-game-dev-blender-addon/rig_core/landmarks.py`, `plugins/nmg-game-dev-blender-addon/rig_core/library.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- `MANNY_BONES`, `LANDMARK_KEYS`, and `bone_layout` match design § Landmarks and validation and § Rig build (FR1)
- `landmarks.validate` implements the design check table in order, with its status and code for each failure (FR3, AC3)
- `library.load` and `BONE_MAPS` implement design § Animation library, including `anim.library_invalid` and `anim.bone_map_incomplete` (FR2)
- Every `fallback required` result's remediation ends with `MIXAMO_FALLBACK_NOTE`, and no module imports `socket`, `urllib`, `http`, or `requests` (FR4)
- No module in this task imports `bpy`

### T002: Rig build

**File(s)**: `plugins/nmg-game-dev-blender-addon/rig_core/rig.py`, `plugins/nmg-game-dev-blender-addon/rig_core/__init__.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- `rig_humanoid` validates first, then builds `SK_<Name>` with the 26 Manny deform bones, skins with `ARMATURE_AUTO`, fails with `rig.weights_failed` (removing the armature) on unweighted vertices, stores landmarks, and replaces an existing rig on rerun (FR1, AC1)
- It never enables Rigify or any add-on, and never opens a network connection (FR4)

### T003: Library retargeting

**File(s)**: `plugins/nmg-game-dev-blender-addon/rig_core/retarget.py`
**Type**: Create
**Depends**: T002
**Acceptance**:
- `import_animations` runs the design's input checks before any import (`anim.text_motion_unsupported`, `anim.rig_missing`, `anim.clip_not_found`) (AC3)
- `bake_clip` imports FBX or BVH, transfers rest-relative rotations and scaled pelvis location, stores action `<clip name>` (replacing an existing one), records provenance on `SK_<Name>`, and removes temporary data (FR2, AC2)

### T004: Rigged export

**File(s)**: `plugins/nmg-game-dev-blender-addon/rig_core/export.py`
**Type**: Create
**Depends**: T003
**Acceptance**:
- `export_rigged` writes `SM_<Name>.fbx` with the design FBX settings and temporary `Armature` rename (restored in `finally`), the material PNGs, and `nmg-animations.json` in the design schema with sorted keys (FR5, AC2)

### T005: Operators and panel

**File(s)**: `plugins/nmg-game-dev-blender-addon/operators/rig_humanoid.py`, `plugins/nmg-game-dev-blender-addon/operators/import_animations.py`, `plugins/nmg-game-dev-blender-addon/operators/export_rigged.py`, `plugins/nmg-game-dev-blender-addon/operators/__init__.py`, `plugins/nmg-game-dev-blender-addon/__init__.py`, `plugins/nmg-game-dev-blender-addon/panels/main_panel.py`, `plugins/nmg-game-dev-blender-addon/property_groups/pipeline_props.py`
**Type**: Create | Modify
**Depends**: T004
**Acceptance**:
- The three operators are registered with the design properties, call `rig_core`, store `last_result`, return `FINISHED` on `ok`, and return `CANCELLED` with the code, message, and remediation reported otherwise (FR6, AC4)
- `NmgGameDevPipelineProps` has `last_result` (added only if absent), and the panel lists the operators

### T006: Docs and changelog

**File(s)**: `docs/asset-contract.md`, `docs/rigging-and-animation.md`, `CHANGELOG.md`
**Type**: Create | Modify
**Depends**: T005
**Acceptance**:
- `docs/asset-contract.md` gains a "Rigged characters" subsection: `SK_<Name>` armature at the world origin with identity transforms, `SM_<Name>` parented to it, UE5 Mannequin deform bone names, and FBX export that includes the armature and baked clips (FR8)
- `docs/rigging-and-animation.md` leads with the agent flow (declare body type → supply landmarks → `rig_humanoid` → `import_animations` → `export_rigged`), then documents landmark keys and the side convention, the `library.json` format and bone maps, the result statuses and codes, and the operator names (FR8)
- `CHANGELOG.md` `[Unreleased]` gets a bullet ending with `(#32)`
- `markdownlint docs/ steering/ *.md` passes

### T007: Blender headless tests

**File(s)**: `tests/blender/rig_fixtures.py`, `tests/blender/test_rig_humanoid.py`, `tests/blender/test_rig_animation.py`, `tests/blender/test_rig_operators.py`
**Type**: Create
**Depends**: T005
**Acceptance**:
- `rig_fixtures.py` builds `Hero`: a T-pose humanoid of joined primitives, voxel-remeshed into one manifold mesh, with matching landmarks. It also builds a Mixamo-named source armature with keyed `Idle` (30 frames, exported as FBX) and `Walk` (40 frames, exported as BVH) in a temp library with `library.json`, plus a `network_blocked` fixture that patches `socket.socket.connect` to record and raise
- `test_rig_humanoid.py` covers AC1 (bones and hierarchy, parenting and modifier, all vertices weighted, no connection attempts, Rigify not enabled, idempotent rerun) and AC3's `rig.unsupported_body`, `rig.unclear_humanoid`, and `rig.pose_not_neutral` cases (scene unchanged, Mixamo note in fallback remediation)
- `test_rig_animation.py` covers AC2: re-import in a `bpy.app.binary_path --background --factory-startup` subprocess shows the 26 bones, no leaf or extra root bones, and `Idle` and `Walk` actions with their frame ranges; the `thigh_l` and `LeftUpLeg` rotation delta is within 1°; and the sidecar fields include SHA-256 values equal to the source files' hashes. It also covers AC3's `anim.text_motion_unsupported` and `anim.clip_not_found` cases
- `test_rig_operators.py` covers AC4: each operator's `last_result` equals the direct call's result, plus `FINISHED` / `CANCELLED` return values
- Passes with `BLENDER_APP` set to Blender 5.2 under `scripts/run-blender-tests.sh`, and under the `repository.lint` and `repository.types` validations

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #32 | 2026-10-29 | Initial feature tasks |
