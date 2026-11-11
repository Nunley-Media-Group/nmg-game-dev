# Design: Built-in procedural clip library for import_animations

**Issue**: #136
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Overview

The built-in library is a pose-data module plus a pure pose solver, both free of `bpy`. A thin baking path in `retarget.py` then keys the solver's output onto `SK_<Name>`.

The pose format, solver approach, and clip set follow the ghost1 consumer project's proven `anim_lib.py`:
- the pose format is `dir` / `rot` / `off` in character space;
- the solver uses the rotation difference to each target direction, applied parent first;
- quaternions are keyed with sign continuity;
- the 24 clips are authored at 30 fps.

`import_animations` gains a `library` argument. File-library calls are unchanged.

## Architecture

### Pose data (new `plugins/nmg-game-dev-blender-addon/rig_core/builtin_clips.py`)

- Pure data and small builders, with no imports beyond the standard library and `.skeleton`.
- `AUTHORED_FPS = 30`.
- A **pose** is a mapping with these fields:
  - `dir`: `{bone: (x, y, z)}` for limb bones (clavicle, upperarm, lowerarm, hand, thigh, calf, foot, ball, `_l`/`_r`);
  - `rot`: `{bone: (x_deg, y_deg, z_deg)}`, an extra character-space rotation for `pelvis`, `spine_01`–`spine_05`, `neck_01`, `neck_02`, and `head`;
  - `off`: `(x, y, z)`, the pelvis offset in leg lengths.
  - Unlisted bones keep their rest orientation relative to their parent.
- A **clip** is `ClipDef(name, keys, mirror_half, loop)`:
  - `keys` is a tuple of `(frame, pose)` at 30 fps;
  - `mirror_half=True` means the keys author the first half of a cycle, and the second half is the same keys mirrored and shifted by the half length;
  - `loop=True` appends the first pose at the end frame, so the last frame equals the first.
- Helpers, after ghost1:
  - `pose(**parts)` builds a pose;
  - `merge(base, *overrides)` merges poses;
  - `mirror(pose)` swaps `_l`/`_r` keys and reflects directions and offsets across the YZ plane (negate x). For each `rot`, it negates the y and z Euler components and keeps x.
- `BUILTIN_CLIPS: dict[str, ClipDef]` holds the 24 ghost1 clips: Idle, FightIdle, Walk, Run, Punch1, Punch2, Punch3, Kick, Jump, JumpKick, Hit, Knockdown, Down, GetUp, Grab, GrabKnee, Throw, Held, Roar, Special, Talk, Ride, RideKickL, RideKickR.
  - `Idle`, `FightIdle`, `Walk`, and `Run` set `loop=True` (FR7).
  - `Walk` and `Run` set `mirror_half=True` (FR6).
  - Every clip is in place, with no root motion.
- `expand(clip) -> list[(frame, pose)]` applies mirroring and looping.
- `clip_digest(clip)` is the SHA-256 of the canonical JSON of the clip's declared definition: sorted keys, `(",", ":")` separators, and floats rounded to 6 places (FR9).

### Solver (new `plugins/nmg-game-dev-blender-addon/rig_core/procedural.py`)

- Pure Python, with small quaternion and 3×3 helpers and no `mathutils`, so it runs under CPython.
- **Input** is a `RestSkeleton` read from the rig:
  - each Manny bone's rest orientation (armature-space 3×3 from `matrix_local`), parent, and head;
  - the leg length, measured as the mean over both sides of |hip→knee| + |knee→ankle|, from the `thigh` and `calf` heads and the `foot` head.
- `solve(rest, pose) -> {bone: local_quaternion}, pelvis_location`. It walks `MANNY_BONES` parent first:
  - **`dir` bones.** The accumulated world rotation is the parent's accumulated rotation, then the minimal rotation (rotation difference) taking the bone's resulting Y axis onto the normalized target direction.
  - **`rot` bones.** The accumulated rotation is the parent's accumulated rotation, then the Euler rotation (XYZ, degrees) in character space.
  - **Other bones** inherit the parent's accumulated rotation.
  - Local rotation is `rest⁻¹ · parentAcc⁻¹ · boneAcc · rest`, so the definition is independent of proportions and rest arm angle (FR4).
  - `pelvis_location` is `off × leg_length`, expressed in the pelvis's local rest frame.
- `continuous(previous, current)` flips a quaternion's sign when its dot product with the previous key is negative.

### Baking (`plugins/nmg-game-dev-blender-addon/rig_core/retarget.py`)

- **Signature.** `import_animations(collection_name, library_dir=None, clips=None, motion_prompt=None, *, library=None)`. The positional file-library form is unchanged (FR11).
- **Check order.**
  1. `motion_prompt` → `anim.text_motion_unsupported`.
  2. Library selection: both a folder and `"builtin"`, neither, or a `library` other than `"builtin"` → `anim.library_invalid`. This runs before any scene change (FR10).
  3. Missing rig → `anim.rig_missing` (AC12).
- **Clip selection.**
  - Built-in names are looked up in `BUILTIN_CLIPS`.
  - An unknown name raises `anim.clip_not_found`, whose remediation lists `sorted(BUILTIN_CLIPS)`. This runs before any bake (AC9).
  - `clips=None` or an empty list selects every clip in definition order.
- **`bake_builtin_clip(armature, clip)`.**
  - It reads the `RestSkeleton` once from `armature.data.bones`.
  - It creates a temporary action and keys each expanded pose at `round(frame × scene.render.fps / AUTHORED_FPS)`. Each key gets `rotation_quaternion` on every bone the clip targets (with sign continuity) and `location` on the pelvis.
  - It installs the action with the existing `_install` (replace by name, fake user) and resets the rest pose (AC1, AC8, FR13).
  - No file is opened.
- **Provenance** uses the existing shape and `_PROVENANCE_KEY`:
  - `name`, `frame_start` (first key), `frame_end` (last key), `frame_count`, and `fps` (scene fps);
  - `source` = `{"library": "builtin", "file": null, "sha256": clip_digest(clip), "skeleton": "manny"}`.
  - It is merged with file-clip provenance in the same armature property, so `export_rigged` writes both kinds unchanged (AC7, AC11).
- `rig_core/export.py` needs no change: it already serializes stored provenance as-is. No reader in `src/` parses `source.file`, so a `null` file needs no consumer change.

### Operator (`plugins/nmg-game-dev-blender-addon/operators/import_animations.py`)

- It adds an `EnumProperty` `library_source` with `FOLDER` (default) and `BUILTIN`.
- With `BUILTIN`, it calls `import_animations(name, None, clips, prompt, library="builtin")`. With `FOLDER`, it passes `library_dir` as today.
- It stores the result with `store_rig_result` and returns `FINISHED` on `ok` (AC13, FR12).

## Data Flow

```
import_animations(name, library="builtin", clips)
  → validate prompt / library selection / rig
  → select ClipDefs
  → RestSkeleton from SK_<Name>
  → expand(clip) → solve(rest, pose) per key
  → key quaternions + pelvis location
  → install action <Clip>
  → provenance
  → rest pose
```

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| ghost1 direction-target poses solved per rig | Selected | Proven on a 24-clip consumer run; independent of proportions and A-pose angle |
| Ship FBX/BVH clip files | Rejected | The issue requires no files; proportions would need retargeting |
| ghost1 `<Clip>@<armature>` action names and a loop property | Rejected | The issue fixes action names to the clip name; loop flags are out of scope |
| Solver in `mathutils` | Rejected | Pure Python keeps the math unit-testable under CPython |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #136 | 2026-11-11 | Initial feature design |
