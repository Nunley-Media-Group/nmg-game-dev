# Design: Humanoid rigging and animation import

**Issue**: #32
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## Overview

A new add-on package, `plugins/nmg-game-dev-blender-addon/rig_core/`, holds all behavior as plain functions. The agent calls them through `execute_blender_code` (`from nmg_game_dev_blender_addon.rig_core import rig_humanoid, import_animations, export_rigged`). Three thin operators wrap them. The skeleton tables, landmark validation, and library parsing are pure Python with no `bpy`. Only `rig.py`, `retarget.py`, and `export.py` touch Blender data. Nothing in the package imports a network module or calls an external service.

## Architecture

```
agent (prompt → body_type + landmarks) ──► rig_humanoid(collection, body_type, landmarks)
                                             ├─ landmarks.validate(...)        pure; fails before any scene change
                                             └─ rig.build(...)                 SK_<Name> (Manny bones) + ARMATURE_AUTO skinning
                                         ──► import_animations(collection, library_dir, clips, motion_prompt)
                                             ├─ library.load(library_dir)      pure; library.json + bone map
                                             └─ retarget.bake_clip(...)        per clip: import FBX/BVH → transfer → action → cleanup
                                         ──► export_rigged(collection, out_dir)
                                             └─ export.write(...)              SM_<Name>.fbx + PNGs + nmg-animations.json
operators nmggamedev.rig_humanoid / import_animations / export_rigged ─► same functions ─► scene.nmg_game_dev.last_result
```

### Modules

| Path | Contents |
|------|----------|
| `rig_core/__init__.py` | Re-exports `rig_humanoid`, `import_animations`, `export_rigged`, and the status constants |
| `rig_core/outcome.py` | `STATUS_OK = "ok"`, `STATUS_FALLBACK = "fallback required"`, `STATUS_SPIKE = "follow-up spike required"`; `ok(**data)` and `fail(status, code, message, remediation)` result-dict builders; `MIXAMO_FALLBACK_NOTE`, appended to every fallback remediation |
| `rig_core/skeleton.py` | `MANNY_BONES`: ordered `(name, parent)` tuples for the 26 bones; `LANDMARK_KEYS`; `bone_layout(landmarks) -> {bone: (head, tail)}` |
| `rig_core/landmarks.py` | `validate(body_type, landmarks, bbox) -> dict | None` (returns a failure result or `None`) |
| `rig_core/library.py` | `load(library_dir) -> Library`; `BONE_MAPS = {"mixamo": {...}, "manny": {...}}`; `resolve_source_bone(name, bone_map)` strips any `prefix:` (for example `mixamorig:`) before lookup |
| `rig_core/rig.py` | `rig_humanoid`: remove the existing rig, create `SK_<Name>`, parent with automatic weights, check weights, store landmarks |
| `rig_core/retarget.py` | `import_animations`, `bake_clip` |
| `rig_core/export.py` | `export_rigged` |
| `operators/rig_humanoid.py`, `operators/import_animations.py`, `operators/export_rigged.py` | Operators |

## API / Interface Changes

| Interface | Input | Output | Behavior |
|-----------|-------|--------|----------|
| `rig_humanoid(collection, body_type, landmarks)` | collection name `<Name>`; `body_type` in `humanoid`, `quadruped`, `non_biped`; dict of `LANDMARK_KEYS` → `[x, y, z]` in meters, world space | result dict | AC1, AC3 |
| `import_animations(collection, library_dir, clips=None, motion_prompt=None)` | `clips=None` means every clip in the library | result dict with `clips: [...]` | AC2, AC3 |
| `export_rigged(collection, out_dir)` | | result dict with `fbx`, `sidecar`, `textures` | AC2 |
| `nmggamedev.rig_humanoid` | `collection_name`, `body_type` (EnumProperty, default `humanoid`), `landmarks_path` (FILE_PATH, JSON) | `FINISHED` / `CANCELLED` | AC4 |
| `nmggamedev.import_animations` | `collection_name`, `library_dir` (DIR_PATH), `clips` (comma-separated, empty = all), `motion_prompt` | `FINISHED` / `CANCELLED` | AC4 |
| `nmggamedev.export_rigged` | `collection_name`, `out_dir` (DIR_PATH) | `FINISHED` / `CANCELLED` | AC4 |

Every function returns a dict with `status`. A failure adds `code`, `message`, and `remediation`. Operators store `json.dumps(result, sort_keys=True)` on `scene.nmg_game_dev.last_result` (adding the `last_result` StringProperty to `NmgGameDevPipelineProps` if it isn't already there). On failure they call `self.report({"ERROR"}, f"{code}: {message} — {remediation}")`.

### Landmarks and validation

`LANDMARK_KEYS`: `pelvis`, `neck`, `head_top`, `shoulder_{l,r}`, `elbow_{l,r}`, `wrist_{l,r}`, `hand_tip_{l,r}`, `hip_{l,r}`, `knee_{l,r}`, `ankle_{l,r}`, `toe_{l,r}`. The character faces −Y, so its left side is +X.

Checks run in this order, on the landmarks and the `SM_<Name>` world bounding box. The first failure is returned:

| Check | Failure |
|-------|---------|
| `body_type != "humanoid"` | spike `rig.unsupported_body` |
| Collection `<Name>` with mesh `SM_<Name>` missing | fallback `rig.asset_not_found` |
| A key is missing or non-finite | fallback `rig.landmarks_missing` |
| A landmark lies outside the bounding box expanded by 2% of height | fallback `rig.landmarks_outside_mesh` |
| `_l` landmark x ≤ 0 or `_r` landmark x ≥ 0; mirrored pairs differ by more than 5% of height after mirroring X; or z is not ordered `head_top > neck > pelvis > knee > ankle` with `hip` between `pelvis` and `knee` | fallback `rig.unclear_humanoid` |
| Shoulder→wrist more than 5° above horizontal or more than 50° below it; elbow or knee bend greater than 15°; or hip→ankle more than 15° from vertical | fallback `rig.pose_not_neutral` |

Height is `head_top.z − min(ankle.z)`. Validation runs before any scene change, so a failure leaves the scene untouched.

### Rig build (`rig.py`)

1. Remove any existing `SK_<Name>` object and its armature data, plus the Armature modifiers it left on the collection's meshes.
2. Create armature object `SK_<Name>` at the world origin with identity transforms, linked to collection `<Name>`. Add the `MANNY_BONES` edit bones with heads and tails from `bone_layout`:
   - `root` runs from the origin up 0.1 × height.
   - `pelvis` runs from `pelvis` toward the spine.
   - `spine_01`–`spine_05` divide `pelvis`→`neck` evenly; `neck_01` and `neck_02` divide `neck`→the head base at 85% of the head span; `head` runs to `head_top`.
   - `clavicle_*` runs from 20% along `neck`→`shoulder_*` (lowered 5% of height) to `shoulder_*`; `upperarm_*`→`elbow_*`→`wrist_*`→`hand_tip_*` for the arm chain.
   - `thigh_*` runs from `hip_*` to `knee_*`, `calf_*` to `ankle_*`, `foot_*` from `ankle_*` to the ball at 70% along `ankle_*`→`toe_*`, and `ball_*` to `toe_*`.
   - Bone rolls come from a fixed rule per chain, so results are deterministic. All bones are deform bones.
3. Parent every mesh in the collection whose parent is not another collection mesh to `SK_<Name>` with `parent_set(type="ARMATURE_AUTO")`, keeping their world transforms.
4. Fail with fallback `rig.weights_failed` if any vertex has no non-zero deform-bone weight. In that case, remove the armature again. The remediation asks for a single manifold mesh or merged parts.
5. Store `nmg_body_type` and `nmg_landmarks` (JSON) as custom properties on `SK_<Name>`.

### Animation library (`library.py`)

`<library_dir>/library.json`:

```json
{"name": "fixture-lib", "skeleton": "mixamo",
 "clips": [{"name": "Idle", "file": "idle.fbx", "frame_start": 1, "frame_end": 30},
           {"name": "Walk", "file": "walk.bvh"}]}
```

- `skeleton` is `mixamo`, `manny`, or `custom`. `custom` requires a `bone_map` of source → Manny names.
- `frame_start` and `frame_end` are optional and default to the source action's range.
- Clip names match `^[A-Za-z][A-Za-z0-9_]*$` and are unique. Files are relative paths ending in `.fbx` or `.bvh` and must exist.
- Any violation returns fallback `anim.library_invalid`.

The `mixamo` map: `Hips→pelvis`, `Spine→spine_01`, `Spine1→spine_03`, `Spine2→spine_05`, `Neck→neck_01`, `Head→head`, and for each side, `{Left,Right}Shoulder→clavicle`, `Arm→upperarm`, `ForeArm→lowerarm`, `Hand→hand`, `UpLeg→thigh`, `Leg→calf`, `Foot→foot`, `ToeBase→ball`. `manny` is the identity map over the 26 bones. Required mapped bones are `pelvis`, `thigh_*`, `calf_*`, `upperarm_*`, `lowerarm_*`, and `head`. If any of them is missing, the result is fallback `anim.bone_map_incomplete`, naming them.

### Retarget (`retarget.py`)

`import_animations` checks inputs in this order:

1. A non-empty `motion_prompt` returns spike `anim.text_motion_unsupported`.
2. A missing `SK_<Name>` returns fallback `anim.rig_missing`.
3. `library.load` failures come next.
4. A requested clip the library doesn't list returns fallback `anim.clip_not_found`, naming the clip.

All of these checks run before any import. Then, for each clip, `bake_clip`:

1. Imports the file into a temporary collection with `bpy.ops.import_scene.fbx(use_anim=True)` or `bpy.ops.import_anim.bvh()`.
2. For every frame in the range, walks the target bones in hierarchy order. For each mapped bone it sets the world rotation `R_t = R_s · R_s_rest⁻¹ · R_t_rest`, converts it to pose-local, and keyframes `rotation_quaternion`. `pelvis` also gets a location of `rest + (src − src_rest) × (target pelvis rest height / source pelvis rest height)`. Unmapped bones stay at rest.
3. Stores the result as action `<clip name>` with `use_fake_user=True`. An existing action with that name is replaced.
4. Deletes the temporary objects, armature data, and imported actions.

The provenance per clip is `{"name", "frame_start", "frame_end", "frame_count", "fps", "source": {"library", "file", "sha256", "skeleton"}}`. It is stored on `SK_<Name>["nmg_animations"]` as JSON keyed by clip name and returned in `clips`.

### Export (`export.py`)

`export_rigged` requires `SK_<Name>` and returns fallback `export.rig_missing` otherwise. During export, `SK_<Name>` is temporarily renamed to `Armature` so UE's FBX importer doesn't add the armature object as an extra root bone. The name is restored in a `finally` block. The FBX call uses contract §7 settings plus the animation options:

- `use_selection=True` on the armature and the collection's meshes
- `object_types={"ARMATURE","MESH"}`, `use_mesh_modifiers=True`, `mesh_smooth_type="FACE"`
- `apply_scale_options="FBX_SCALE_UNITS"`, `path_mode="STRIP"`, `embed_textures=False`
- `add_leaf_bones=False`, `use_armature_deform_only=True`, `primary_bone_axis="Y"`, `secondary_bone_axis="X"`
- `bake_anim=True`, `bake_anim_use_all_actions=True`, `bake_anim_use_nla_strips=False`, `bake_anim_force_startend_keying=True`

Images used by the meshes' materials are saved as PNG beside the FBX under their own names.

`out_dir/nmg-animations.json` (keys sorted):

```json
{"asset": "Hero", "armature": "SK_Hero", "skeleton": "ue5_manny", "fbx": "SM_Hero.fbx",
 "bones": ["root", "pelvis", "..."],
 "clips": [{"name": "Idle", "frame_start": 1, "frame_end": 30, "frame_count": 30, "fps": 30,
            "source": {"library": "fixture-lib", "file": "idle.fbx", "sha256": "…", "skeleton": "mixamo"}}]}
```

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Deform-only UE5 Mannequin skeleton built from agent landmarks | Selected | Interview decision. The skeleton drops into UE without retargeting and works with Manny-based animation |
| Rigify control rig | Rejected | It adds in-Blender animator controls the pipeline doesn't use, and its DEF bone names would need renaming for UE |
| Auto-detect landmarks from mesh cross-sections | Rejected | Interview decision that rigging is prompt-driven. Heuristics are fragile on clothed characters |
| Retarget in Unreal with the IK Retargeter | Rejected | It puts the animation path on UE automation and #68. Baking in Blender keeps import a single FBX |
| Retarget with Copy Rotation constraints and an NLA bake | Rejected | Rest-relative rotation transfer per frame is deterministic and handles T- vs A-pose rest differences directly |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #32 | 2026-10-29 | Initial feature design |
