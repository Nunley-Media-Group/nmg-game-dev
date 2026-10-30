# Rigging and animation

The agent rigs a humanoid it modeled and bakes clips from a local animation
library onto it, all inside Blender. No paid or rate-limited service is
involved. The rig uses UE5 Mannequin bone names, so the exported FBX imports
into Unreal as a skeletal mesh that works with Manny-based animation.

## Agent flow

1. **Declare the body type.** Work it out from the request and your own model.
   Only `humanoid` is auto-rigged.
2. **Supply landmarks.** Give world-space points in meters for the joints
   listed below. The tooling checks them and never detects anatomy itself.
3. **Rig.** Call `rig_humanoid(collection, body_type, landmarks)`. It builds
   `SK_<Name>` and skins `SM_<Name>` on it.
4. **Import animations.** Call `import_animations(collection, library_dir)`.
   Omit `clips` to bake every clip the library lists.
5. **Export.** Call `export_rigged(collection, out_dir)`.

The functions live in the add-on's `rig_core` package. Call them through
`execute_blender_code`:

```python
from nmg_game_dev_blender_addon.rig_core import (
    export_rigged,
    import_animations,
    rig_humanoid,
)

landmarks = {
    "pelvis": [0.0, 0.0, 1.0],
    "neck": [0.0, 0.0, 1.42],
    "head_top": [0.0, 0.0, 1.76],
    # ... all 19 keys in the table below
}
result = rig_humanoid("Hero", "humanoid", landmarks)
if result["status"] == "ok":
    import_animations("Hero", "/path/to/library")
    export_rigged("Hero", "/path/to/out")
```

Every function returns a dict with `status`. A failure adds `code`, `message`,
and `remediation`. Check `status` before you go on to the next step.

## Landmarks

Each value is `[x, y, z]` in meters, in world space. The character faces −Y, so
its left side is +X.

| Key | Meaning |
| --- | --- |
| `pelvis` | Centre of the pelvis |
| `neck` | Base of the neck |
| `head_top` | Top of the head |
| `shoulder_l`, `shoulder_r` | Shoulder joints |
| `elbow_l`, `elbow_r` | Elbow joints |
| `wrist_l`, `wrist_r` | Wrist joints |
| `hand_tip_l`, `hand_tip_r` | Tip of the hand |
| `hip_l`, `hip_r` | Hip joints |
| `knee_l`, `knee_r` | Knee joints |
| `ankle_l`, `ankle_r` | Ankle joints |
| `toe_l`, `toe_r` | Toe tips |

Side convention: an `_l` landmark has x > 0, and an `_r` landmark has x < 0.
Each `_l` landmark mirrors its `_r` partner across the X axis to within 5% of
the character's height.

The checks run in this order, and the first failure is returned:

1. The body type must be `humanoid`.
2. The collection must hold a root mesh `SM_<Name>`.
3. Every landmark key must be present and finite.
4. Every landmark must sit inside the mesh's bounding box, grown by 2% of the
   height.
5. Sides, mirroring, and vertical order must be correct. The vertical order is
   `head_top > neck > pelvis > knee > ankle`, with the hip between the pelvis
   and the knee.
6. The pose must be neutral. Each shoulder-to-wrist line may be at most 5°
   above horizontal and at most 50° below it. Elbows and knees may bend at most
   15°. Each hip-to-ankle line may lean at most 15° from vertical.

Height is `head_top.z` minus the lower of the two ankle heights. Validation runs
before anything in the scene changes.

## Animation library

A library is a folder with a `library.json` and the clip files it lists:

```json
{"name": "fixture-lib", "skeleton": "mixamo",
 "clips": [{"name": "Idle", "file": "idle.fbx", "frame_start": 1, "frame_end": 30},
           {"name": "Walk", "file": "walk.bvh"}]}
```

- `name` is a non-empty string. It is recorded in the provenance.
- `skeleton` is `mixamo`, `manny`, or `custom`.
- `custom` needs a `bone_map` object that maps each source bone name to a Manny
  bone name.
- Each clip needs a `name` that matches `^[A-Za-z][A-Za-z0-9_]*$` and is unique
  within the library. Its `file` is a relative path ending in `.fbx` or `.bvh`,
  inside the library folder.
- `frame_start` and `frame_end` are optional. They default to the source
  action's range.

Bone maps are applied to the source file's bone names. A `prefix:` such as
`mixamorig:` is ignored when matching.

Built-in bone maps:

- `mixamo`: `Hips` → `pelvis`, `Spine` → `spine_01`, `Spine1` → `spine_03`,
  `Spine2` → `spine_05`, `Neck` → `neck_01`, `Head` → `head`. For each side,
  `Shoulder` → `clavicle`, `Arm` → `upperarm`, `ForeArm` → `lowerarm`,
  `Hand` → `hand`, `UpLeg` → `thigh`, `Leg` → `calf`, `Foot` → `foot`, and
  `ToeBase` → `ball`.
- `manny`: identity over the 26 Manny bones.
- `custom`: the library's `bone_map`.

Whatever the map, the source must reach `pelvis`, `thigh_l`, `thigh_r`,
`calf_l`, `calf_r`, `upperarm_l`, `upperarm_r`, `lowerarm_l`, `lowerarm_r`, and
`head`. A map that misses any of them fails with `anim.bone_map_incomplete`.

Each clip is retargeted from rest. Each mapped bone's world rotation relative to
its rest pose is copied onto the same bone of the rig. The pelvis also gets its
translation, scaled by the ratio of the two pelvis heights. Unmapped bones stay
at rest. Each clip is stored as an action named after the clip.

## Result statuses

| Status | Meaning |
| --- | --- |
| `ok` | The step completed. |
| `fallback required` | Fix the input or the library and rerun. |
| `follow-up spike required` | The request is outside the current tooling. |

Codes:

- `rig.unsupported_body` (spike): the body type is `quadruped` or `non_biped`.
- `rig.asset_not_found` (fallback): the collection has no root mesh `SM_<Name>`.
- `rig.landmarks_missing` (fallback): a landmark is missing, not finite, or not
  `[x, y, z]`, or the operator cannot read the landmarks file.
- `rig.landmarks_outside_mesh` (fallback): a landmark is outside the mesh's
  bounding box.
- `rig.unclear_humanoid` (fallback): landmarks are asymmetric, on the wrong
  side, or out of vertical order.
- `rig.pose_not_neutral` (fallback): an arm, elbow, knee, or leg is outside the
  pose limits.
- `rig.weights_failed` (fallback): some vertices get no deform-bone weight.
- `anim.text_motion_unsupported` (spike): a `motion_prompt` was given.
- `anim.rig_missing` (fallback): `SK_<Name>` does not exist yet.
- `anim.library_invalid` (fallback): `library.json` or a clip file breaks the
  rules above.
- `anim.bone_map_incomplete` (fallback): the bone map or the clip file lacks a
  required bone.
- `anim.clip_not_found` (fallback): a requested clip is not in the library.
- `export.rig_missing` (fallback): `SK_<Name>` does not exist, so there is
  nothing to export.
- `export.name_taken` (fallback): an object named `Armature` already exists and
  would clash with the export rename.

An `ok` rig result carries `asset`, `armature`, `body_type`, `bones`, and
`bone_count`. An `ok` import result carries `asset`, `armature`, and `clips`,
where each clip has its provenance. An `ok` export result carries `asset`,
`armature`, `fbx`, `sidecar`, `textures`, and `clips`.

Every `fallback required` remediation ends with an optional note: Mixamo can be
used by hand as a manual fallback. Nothing in nmg-game-dev contacts Mixamo or
any other service.

A rerun of `rig_humanoid` replaces the rig. If skinning fails on the rerun, the
earlier rig has already been removed, so fix the mesh and rerun.

## Operators

The same functions run from the add-on panel, under the NMG tab:

- `nmggamedev.rig_humanoid` wraps `rig_humanoid`. Inputs: collection, body
  type, and a landmarks JSON file.
- `nmggamedev.import_animations` wraps `import_animations`. Inputs: collection,
  library folder, comma-separated clips, and motion prompt.
- `nmggamedev.export_rigged` wraps `export_rigged`. Inputs: collection and
  output folder.

Each operator stores its result on `scene.nmg_game_dev.last_result` and returns
`FINISHED` when the status is `ok`. Otherwise it returns `CANCELLED` and reports
the code, message, and remediation.
