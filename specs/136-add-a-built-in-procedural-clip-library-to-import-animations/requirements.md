# Requirements: Built-in procedural clip library for import_animations

**Issue**: #136
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As a** game developer who has just rigged a character with `rig_humanoid`
**I want** `import_animations` to bake a built-in set of clips that needs no animation files
**So that** a new project has playable animations on its rigged characters without sourcing FBX or BVH clips

## Background

`rig_humanoid` builds a UE5 Mannequin rig on any humanoid, whatever its proportions. `import_animations(collection_name, library_dir, clips=None, motion_prompt=None)` in `plugins/nmg-game-dev-blender-addon/rig_core/retarget.py` then loads `library.json` from `library_dir` (`rig_core/library.py`), retargets each FBX or BVH clip onto `SK_<Name>`, and installs it as an action named after the clip. The framework ships no clips, so a new project has rigged characters and nothing to play on them.

The built-in library describes each key pose as stick-figure targets in character space: the character faces −Y, +X is its left, +Z is up. A pose gives:
- a world direction for each limb bone;
- an extra world-axis rotation for the pelvis, spine, and head;
- a pelvis offset measured in leg lengths.

Targets are converted to local bone rotations by walking the hierarchy from the rig's own rest pose, keyframed, and interpolated by Blender. One definition therefore bakes onto any `rig_humanoid` character, regardless of its proportions or A-pose arm angle. Left/right mirroring supplies the second half of a cycle.

## Acceptance Criteria

### AC1: The built-in library bakes with no files

**Given** a character rigged with `rig_humanoid` and no animation library folder
**When** `import_animations` is called for its collection with `library="builtin"` and no `clips`
**Then** the result is `ok`, every built-in clip is an action on `SK_<Name>` named after the clip, each action has keyframes on the bones its poses target, no file is read, and the rig is left in its rest pose

### AC2: The starter set is present

**Given** the built-in library
**When** all of its clips are baked
**Then** the result lists at least `Idle`, `FightIdle`, `Walk`, `Run`, `Punch1`, `Punch2`, `Punch3`, `Kick`, `Jump`, `JumpKick`, `Hit`, `Knockdown`, `Down`, `GetUp`, `Grab`, `Throw`, `Roar`, `Talk`, and `Ride`

### AC3: A subset can be requested

**Given** a rigged character
**When** `import_animations` is called with `library="builtin"` and `clips=["Idle", "Walk"]`
**Then** only `Idle` and `Walk` are baked and listed in the result, and no other built-in clip is added to the rig

### AC4: One definition fits any proportions and A-pose angle

**Given** two `rig_humanoid` characters with different limb lengths, shoulder widths, and rest arm angles (one near T-pose, one with arms 45° below horizontal)
**When** the same built-in clip is baked onto both
**Then** at each key frame every limb bone the pose targets points along the pose's world direction on both rigs, within 2°

### AC5: Pelvis movement scales with leg length

**Given** two rigged characters with different leg lengths
**When** a built-in clip that moves the pelvis (for example `Jump` or `Down`) is baked onto both
**Then** at each key frame the pelvis is displaced from its rest position by the pose's offset multiplied by that character's leg length

### AC6: Cycles are mirrored and loop

**Given** a rigged character
**When** `Walk` and `Run` are baked
**Then** the second half of each cycle is the left/right mirror of the first half
**And** the pose on the last frame matches the pose on the first frame, as it also does for `Idle` and `FightIdle`

### AC7: Provenance is recorded like a file clip

**Given** a rigged character with built-in clips baked
**When** the import result is read, and again after `export_rigged` writes `nmg-animations.json`
**Then** each built-in clip has `name`, `frame_start`, `frame_end`, `frame_count`, `fps`, and a `source` with:
- `library` `"builtin"`;
- `skeleton` `"manny"`;
- `file` `null`;
- a `sha256` that is the digest of that clip's pose definition
**And** the exported FBX holds the clip as an action

### AC8: Baking is repeatable

**Given** a rigged character with a built-in clip already baked
**When** the same clip is baked again
**Then** the action is replaced, not duplicated, its keyframes and its provenance are identical to the first bake, and no temporary object or action is left in the file

### AC9: An unknown built-in clip is reported

**Given** a rigged character
**When** `import_animations` is called with `library="builtin"` and a clip name the built-in library does not have
**Then** the result is `fallback required` with code `anim.clip_not_found`, the remediation lists the built-in clip names, and no clip is baked

### AC10: Invalid library selection is reported

**Given** a rigged character
**When** `import_animations` is called with both a library folder and `library="builtin"`, with neither, or with a `library` value other than `"builtin"`
**Then** the result is `fallback required` with code `anim.library_invalid` and nothing in the scene changes

### AC11: File libraries behave as before

**Given** a library folder with a valid `library.json` and clips
**When** `import_animations(collection, library_dir)` is called as it is today
**Then** the clips bake and their provenance is unchanged
**And** built-in and file clips can be baked onto the same rig, and both appear in `nmg-animations.json`

### AC12: Existing preconditions still apply

**Given** a collection with no `SK_<Name>` rig, or a call with a `motion_prompt`
**When** `import_animations` is called with `library="builtin"`
**Then** the result is `anim.rig_missing` or `anim.text_motion_unsupported` respectively, as for a file library

### AC13: The operator can select the built-in library

**Given** the add-on panel
**When** `nmggamedev.import_animations` is run with the built-in library selected and no library folder
**Then** the built-in clips are baked, the result is stored on `scene.nmg_game_dev.last_result`, and the operator returns `FINISHED`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `import_animations` accepts `library="builtin"` and bakes clips from a library shipped inside the add-on, with no file or network access | Must |
| FR2 | The built-in library ships at least the 19 clips named in AC2 | Must |
| FR3 | Each built-in clip is defined as key poses of stick-figure targets: a world direction per limb bone, an extra world-axis rotation for pelvis, spine, and head, and a pelvis offset in leg lengths | Must |
| FR4 | Targets are converted to local bone rotations by walking the Mannequin hierarchy from the rig's own rest pose, so a definition is independent of proportions and rest arm angle | Must |
| FR5 | Poses are keyframed and Blender interpolates between them; a bone no pose targets stays at rest | Must |
| FR6 | A clip definition can declare left/right mirroring so a cycle is authored as half a cycle | Must |
| FR7 | `Idle`, `FightIdle`, `Walk`, and `Run` end on the pose they start on | Must |
| FR8 | The `clips` argument selects built-in clips by name; an unknown name fails with `anim.clip_not_found` and lists the available names | Must |
| FR9 | Built-in clips record provenance in the same shape as file clips, with `library` `"builtin"`, `skeleton` `"manny"`, `file` `null`, and a `sha256` of the clip's pose definition, and `export_rigged` writes it to `nmg-animations.json` | Must |
| FR10 | Supplying both a library folder and `library="builtin"`, neither, or an unknown `library` value fails with `anim.library_invalid` before the scene changes | Must |
| FR11 | Existing `import_animations(collection, library_dir, ...)` calls and file-clip provenance are unchanged | Must |
| FR12 | `nmggamedev.import_animations` lets the user select the built-in library instead of a folder | Must |
| FR13 | Baking a built-in clip is deterministic and replaces an existing action of the same name | Must |
| FR14 | `docs/rigging-and-animation.md` documents the built-in library, its clip names, and the call; `docs/asset-contract.md` describes the `source` of a built-in clip | Must |
| FR15 | Blender tests cover the built-in library on at least two rigs of different proportions and rest arm angle | Must |

## Out of Scope

- Baking pose definitions supplied by a game project; the pose format is internal.
- Text-driven motion; `motion_prompt` stays unsupported.
- Root motion; locomotion clips play in place.
- Finger, twist, or facial animation, and any bone outside the 26 Mannequin bones.
- Quadruped or other non-humanoid bodies.
- Unreal animation blueprints, state machines, blend spaces, or montages built from the clips.
- A loop flag or other new per-clip fields in `nmg-animations.json`.
- Changes to FBX/BVH retargeting or to the `mixamo`, `manny`, and `custom` bone maps.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #136 | 2026-11-11 | Initial feature spec |
