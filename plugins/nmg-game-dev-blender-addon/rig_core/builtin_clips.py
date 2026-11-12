"""Built-in procedural clip definitions for rig_humanoid (UE5 Mannequin, 26 bones). No bpy.

Poses are stick-figure targets in character space (the character faces -Y, +X is its left, +Z up):
  dir : {bone: (x, y, z)}     world direction the bone's Y axis should point along (limbs)
  rot : {bone: (rx, ry, rz)}  extra character-space Euler rotation in degrees
                              (pelvis, spine, neck, head)
  off : (x, y, z)             pelvis offset in leg lengths
Because targets are directions, one definition bakes onto any rig_humanoid character
(see procedural.py). The pose data and clip set are ported from the ghost1 consumer project's
anim_lib.py.

A clip is ClipDef(name, keys, mirror_half, loop). keys is a tuple of (frame, pose) at
AUTHORED_FPS. mirror_half keys author the first half of a cycle; the second half is those keys
mirrored and shifted by the half length. loop clips must close: the first and last expanded
poses are equal.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

AUTHORED_FPS = 30

Pose = dict[str, Any]
Vec3 = tuple[float, float, float]

_ZERO: Vec3 = (0.0, 0.0, 0.0)
# Feet stay flat in every clip unless a clip gives them an explicit direction.
_FOOT: Vec3 = (0.0, -0.96, -0.27)


def pose(
    *,
    dir: Mapping[str, Vec3] | None = None,
    rot: Mapping[str, Vec3] | None = None,
    off: Vec3 = _ZERO,
) -> Pose:
    """Build a complete pose with the three fields always present."""
    return {"dir": dict(dir or {}), "rot": dict(rot or {}), "off": tuple(off)}


def merge(base: Pose, over: Mapping[str, Any]) -> Pose:
    """Return base with the override's directions, rotations, and (when given) offset applied."""
    out = {"dir": dict(base["dir"]), "rot": dict(base["rot"]), "off": base["off"]}
    if "off" in over:
        out["off"] = tuple(over["off"])
    out["dir"].update(over.get("dir", {}))
    out["rot"].update(over.get("rot", {}))
    return out


def derive(
    base: Pose, off: Vec3 | None = None, rot: Mapping[str, Vec3] | None = None, **dirs: Vec3
) -> Pose:
    """Shorthand for merge: derive(STAND, rot={...}, upperarm_l=(...)) overrides what it names."""
    over: dict[str, Any] = {"dir": dirs, "rot": dict(rot or {})}
    if off is not None:
        over["off"] = off
    return merge(base, over)


def mirror(pose_: Pose) -> Pose:
    """Swap left and right: _l and _r keys trade places, x is negated, and rotations keep x."""

    def swap(bone: str) -> str:
        if bone.endswith("_l"):
            return bone[:-2] + "_r"
        if bone.endswith("_r"):
            return bone[:-2] + "_l"
        return bone

    off = pose_["off"]
    return {
        "dir": {swap(bone): (-x, y, z) for bone, (x, y, z) in pose_["dir"].items()},
        "rot": {bone: (rx, -ry, -rz) for bone, (rx, ry, rz) in pose_["rot"].items()},
        "off": (-off[0], off[1], off[2]),
    }


@dataclass(frozen=True)
class ClipDef:
    name: str
    keys: tuple[tuple[int, Pose], ...]
    mirror_half: bool = False
    loop: bool = False


# ----------------------------------------------------------------------------- poses
STAND = pose(
    dir={
        "upperarm_l": (0.22, 0.05, -1),
        "lowerarm_l": (0.12, -0.25, -1),
        "hand_l": (0.1, -0.3, -1),
        "upperarm_r": (-0.22, 0.05, -1),
        "lowerarm_r": (-0.12, -0.25, -1),
        "hand_r": (-0.1, -0.3, -1),
        "thigh_l": (0.06, 0, -1),
        "calf_l": (0.02, 0.03, -1),
        "thigh_r": (-0.06, 0, -1),
        "calf_r": (-0.02, 0.03, -1),
        "foot_l": _FOOT,
        "foot_r": _FOOT,
    }
)

# Brawler guard: left side leads, fists up.
GUARD = merge(
    STAND,
    {
        "off": (0, 0, -0.07),
        "rot": {"pelvis": (0, 0, -22), "spine_03": (-6, 0, 8), "head": (4, 0, 14)},
        "dir": {
            "thigh_l": (0.18, -0.38, -1),
            "calf_l": (0.02, 0.22, -1),
            "thigh_r": (-0.28, 0.3, -1),
            "calf_r": (-0.05, 0.35, -1),
            "upperarm_l": (0.35, -0.45, -0.8),
            "lowerarm_l": (-0.2, -0.55, 0.8),
            "hand_l": (-0.2, -0.5, 0.85),
            "upperarm_r": (-0.45, 0.1, -0.9),
            "lowerarm_r": (0.25, -0.6, 0.75),
            "hand_r": (0.25, -0.55, 0.8),
        },
    },
)


def _stride(
    sw: float, knee: float, lift: float, arm: float, lean: float, bob: float
) -> tuple[Pose, Pose]:
    """Contact and passing poses for one leg of a cycle; the mirror supplies the other leg."""
    contact = derive(
        STAND,
        off=(0, 0, -bob),
        rot={"spine_03": (-lean, 0, 0), "pelvis": (0, 0, -6), "spine_05": (0, 0, 10)},
        thigh_l=(0.05, -sw, -1),
        calf_l=(0.02, -sw * 0.25, -1),
        thigh_r=(-0.05, sw * 0.8, -1),
        calf_r=(-0.02, sw * 1.6, -1),
        upperarm_l=(0.2, arm, -1),
        lowerarm_l=(0.1, arm * 0.4 - 0.2, -1),
        upperarm_r=(-0.2, -arm, -1),
        lowerarm_r=(-0.1, -arm - 0.5, -0.8),
    )
    passing = derive(
        STAND,
        off=(0, 0, 0.0),
        rot={"spine_03": (-lean, 0, 0)},
        thigh_l=(0.05, 0.05, -1),
        calf_l=(0.02, 0.05, -1),
        thigh_r=(-0.05, -knee * 0.6, -1),
        calf_r=(-0.02, knee + lift, -1),
        upperarm_l=(0.2, 0.0, -1),
        lowerarm_l=(0.1, -0.25, -1),
        upperarm_r=(-0.2, 0.0, -1),
        lowerarm_r=(-0.1, -0.3, -1),
    )
    return contact, passing


_JAB = derive(
    GUARD,
    off=(0, -0.06, -0.08),
    rot={"pelvis": (0, 0, -8), "spine_03": (-8, 0, -14), "head": (4, 0, 6)},
    upperarm_l=(0.15, -1, 0.05),
    lowerarm_l=(0.0, -1, 0.05),
    hand_l=(0, -1, 0.05),
)
_CROSS = derive(
    GUARD,
    off=(0, -0.1, -0.1),
    rot={"pelvis": (0, 0, 18), "spine_03": (-10, 0, 30), "head": (4, 0, -24)},
    upperarm_r=(-0.1, -1, 0.02),
    lowerarm_r=(0.05, -1, 0.05),
    hand_r=(0.05, -1, 0.05),
    upperarm_l=(0.5, 0.1, -0.7),
    lowerarm_l=(-0.1, -0.5, 0.8),
    calf_r=(-0.05, 0.6, -1),
)
_WIND = derive(
    GUARD,
    off=(0, 0.04, -0.2),
    rot={"pelvis": (0, 0, 30), "spine_03": (10, 0, 20), "head": (0, 0, -30)},
    upperarm_r=(-0.5, 0.5, -0.8),
    lowerarm_r=(-0.1, -0.2, -1),
    thigh_l=(0.2, -0.5, -0.9),
    calf_l=(0, 0.5, -1),
)
_UPPER = derive(
    GUARD,
    off=(0, -0.12, 0.02),
    rot={"pelvis": (0, 0, -30), "spine_03": (-14, 0, -30), "head": (-8, 0, 30)},
    upperarm_r=(-0.1, -0.7, 0.75),
    lowerarm_r=(0.05, -0.25, 1),
    hand_r=(0.05, -0.2, 1),
    upperarm_l=(0.5, 0.3, -0.7),
    lowerarm_l=(0.2, -0.3, -0.6),
    thigh_r=(-0.2, 0.45, -1),
    calf_r=(-0.05, 0.6, -1),
)
_CHAMBER = derive(
    GUARD,
    off=(0, 0, -0.03),
    rot={"spine_03": (8, 0, 0)},
    thigh_r=(-0.1, -0.9, 0.1),
    calf_r=(-0.05, 0.3, -1),
    thigh_l=(0.1, -0.05, -1),
    calf_l=(0.02, 0.1, -1),
)
_KICK = derive(
    GUARD,
    off=(0, -0.04, -0.02),
    rot={"spine_03": (16, 0, 0), "head": (-8, 0, 0)},
    thigh_r=(-0.08, -1, 0.15),
    calf_r=(-0.05, -1, 0.2),
    foot_r=(0, -0.2, 1),
    thigh_l=(0.1, -0.05, -1),
    calf_l=(0.02, 0.12, -1),
    upperarm_l=(0.6, 0.2, -0.6),
    upperarm_r=(-0.6, 0.3, -0.6),
)
_CROUCH = derive(
    STAND,
    off=(0, 0, -0.3),
    rot={"spine_03": (-18, 0, 0)},
    thigh_l=(0.15, -0.8, -0.7),
    calf_l=(0.05, 0.75, -0.8),
    thigh_r=(-0.15, -0.8, -0.7),
    calf_r=(-0.05, 0.75, -0.8),
    upperarm_l=(0.3, 0.5, -0.8),
    upperarm_r=(-0.3, 0.5, -0.8),
)
_TUCK = derive(
    STAND,
    rot={"spine_03": (-8, 0, 0)},
    thigh_l=(0.2, -0.75, -0.6),
    calf_l=(0.05, 0.5, -1),
    thigh_r=(-0.2, -0.45, -0.9),
    calf_r=(-0.05, 0.7, -0.8),
    upperarm_l=(0.7, -0.2, 0.5),
    upperarm_r=(-0.7, -0.2, 0.5),
    lowerarm_l=(0.5, -0.3, 0.8),
    lowerarm_r=(-0.5, -0.3, 0.8),
)
_FLY = derive(
    STAND,
    rot={"pelvis": (22, 0, 0), "spine_03": (-10, 0, 0), "head": (-12, 0, 0)},
    thigh_r=(-0.1, -1, -0.12),
    calf_r=(-0.08, -1, -0.1),
    foot_r=(0, -0.3, 1),
    thigh_l=(0.25, -0.5, -0.7),
    calf_l=(0.05, 0.95, -0.2),
    upperarm_l=(0.8, 0.3, 0.1),
    lowerarm_l=(0.5, -0.5, 0.5),
    upperarm_r=(-0.6, 0.5, -0.3),
    lowerarm_r=(-0.2, -0.3, 0.9),
)
_FLINCH = derive(
    GUARD,
    off=(0, 0.1, -0.06),
    rot={"pelvis": (-6, 0, 0), "spine_03": (22, 0, 10), "head": (20, 0, 14)},
    upperarm_l=(0.7, 0.2, -0.5),
    lowerarm_l=(0.5, -0.4, 0.3),
    upperarm_r=(-0.7, 0.3, -0.5),
    lowerarm_r=(-0.5, -0.3, 0.3),
)
_AIR = derive(
    STAND,
    off=(0, 0.25, -0.15),
    rot={"pelvis": (-50, 0, 0), "spine_03": (20, 0, 0), "head": (-20, 0, 0)},
    thigh_l=(0.2, -0.9, 0.2),
    calf_l=(0.1, -0.6, -0.6),
    thigh_r=(-0.2, -0.8, 0.5),
    calf_r=(-0.1, -0.5, -0.7),
    foot_l=(0, -0.6, 0.6),
    foot_r=(0, -0.6, 0.6),
    upperarm_l=(0.8, -0.3, 0.4),
    lowerarm_l=(0.7, -0.5, 0.3),
    upperarm_r=(-0.8, -0.3, 0.4),
    lowerarm_r=(-0.7, -0.5, 0.3),
)
_DOWN = derive(
    STAND,
    off=(0, 0.55, -0.86),
    rot={"pelvis": (-90, 0, 0), "head": (0, 0, 20)},
    thigh_l=(0.25, -1, 0.02),
    calf_l=(0.15, -1, -0.02),
    thigh_r=(-0.3, -1, 0.02),
    calf_r=(-0.1, -1, 0.25),
    foot_l=(0.3, -0.3, 1),
    foot_r=(-0.3, -0.3, 1),
    upperarm_l=(1, 0.3, 0.0),
    lowerarm_l=(0.8, 0.8, 0.0),
    hand_l=(0.5, 1, 0),
    upperarm_r=(-1, -0.4, 0.0),
    lowerarm_r=(-1, -0.6, 0.0),
    hand_r=(-1, -0.6, 0),
)
_SIT = derive(
    STAND,
    off=(0, 0.35, -0.62),
    rot={"pelvis": (-25, 0, 0), "spine_03": (-30, 0, 0)},
    thigh_l=(0.25, -1, 0.35),
    calf_l=(0.05, -0.3, -1),
    thigh_r=(-0.25, -1, 0.3),
    calf_r=(-0.05, -0.2, -1),
    upperarm_l=(0.4, 0.5, -0.8),
    lowerarm_l=(0.2, 0.2, -1),
    upperarm_r=(-0.4, 0.5, -0.8),
    lowerarm_r=(-0.2, 0.2, -1),
)
_GRAB = derive(
    GUARD,
    off=(0, -0.05, -0.08),
    rot={"spine_03": (-10, 0, 0)},
    upperarm_l=(0.3, -0.9, -0.1),
    lowerarm_l=(-0.25, -0.9, 0.3),
    upperarm_r=(-0.3, -0.9, -0.1),
    lowerarm_r=(0.25, -0.9, 0.3),
    hand_l=(-0.3, -0.9, 0.2),
    hand_r=(0.3, -0.9, 0.2),
)
_KNEE = derive(
    _GRAB,
    off=(0, -0.02, -0.02),
    rot={"spine_03": (-22, 0, 0)},
    thigh_r=(-0.1, -1, 0.45),
    calf_r=(-0.05, 0.5, -1),
    upperarm_l=(0.3, -0.8, -0.5),
    upperarm_r=(-0.3, -0.8, -0.5),
)
_LOAD = derive(
    _GRAB,
    off=(0, 0.05, -0.18),
    rot={"pelvis": (0, 0, 40), "spine_03": (6, 0, 30)},
    thigh_l=(0.3, -0.5, -0.9),
    calf_l=(0, 0.5, -1),
)
_HURL = derive(
    GUARD,
    off=(0, -0.12, -0.1),
    rot={"pelvis": (0, 0, -50), "spine_03": (-16, 0, -40), "head": (0, 0, 40)},
    upperarm_l=(0.9, -0.5, 0.1),
    lowerarm_l=(0.9, -0.5, 0.2),
    upperarm_r=(0.3, -1, 0.15),
    lowerarm_r=(0.4, -1, 0.1),
)
_HELD = derive(
    STAND,
    off=(0, 0, -0.04),
    rot={"spine_03": (14, 0, 0), "head": (18, 0, 0)},
    upperarm_l=(0.5, 0.2, -0.8),
    lowerarm_l=(0.4, -0.1, -1),
    upperarm_r=(-0.5, 0.2, -0.8),
    lowerarm_r=(-0.4, -0.1, -1),
    thigh_l=(0.1, -0.15, -1),
    calf_l=(0.03, 0.3, -1),
    thigh_r=(-0.1, -0.1, -1),
    calf_r=(-0.03, 0.3, -1),
)
_FLEX = derive(
    STAND,
    off=(0, 0, -0.12),
    rot={"spine_03": (-16, 0, 0), "head": (-6, 0, 0)},
    thigh_l=(0.4, -0.2, -1),
    calf_l=(0.0, 0.3, -1),
    thigh_r=(-0.4, -0.2, -1),
    calf_r=(0.0, 0.3, -1),
    upperarm_l=(0.8, -0.1, -0.5),
    lowerarm_l=(0.3, -0.4, 0.85),
    upperarm_r=(-0.8, -0.1, -0.5),
    lowerarm_r=(-0.3, -0.4, 0.85),
)
_SKY = derive(
    _FLEX,
    off=(0, 0.02, -0.05),
    rot={"spine_03": (22, 0, 0), "head": (30, 0, 0)},
    upperarm_l=(0.9, 0.2, -0.3),
    lowerarm_l=(0.7, -0.2, 0.7),
    upperarm_r=(-0.9, 0.2, -0.3),
    lowerarm_r=(-0.7, -0.2, 0.7),
)
_HIGH = derive(
    _FLEX,
    off=(0, 0, 0.0),
    rot={"spine_03": (10, 0, 14)},
    upperarm_r=(-0.3, 0.2, 1),
    lowerarm_r=(-0.1, 0.1, 1),
    hand_r=(0, 0, 1),
)
_SLAM = derive(
    STAND,
    off=(0, -0.1, -0.5),
    rot={"pelvis": (20, 0, 0), "spine_03": (-40, 0, -12), "head": (20, 0, 0)},
    thigh_l=(0.3, -1, -0.3),
    calf_l=(0.05, 0.4, -1),
    thigh_r=(-0.3, 0.1, -1),
    calf_r=(-0.1, 1, -0.15),
    foot_r=(0, 0.3, -1),
    upperarm_r=(-0.1, -0.6, -1),
    lowerarm_r=(0.0, -0.3, -1),
    hand_r=(0, -0.2, -1),
    upperarm_l=(0.7, 0.4, -0.4),
    lowerarm_l=(0.4, 0.5, 0.3),
)
_THROW_BACK = derive(
    GUARD,
    off=(0, 0.05, -0.12),
    rot={"pelvis": (0, 0, 30), "spine_03": (8, 0, 26)},
    upperarm_r=(-0.7, 0.6, 0.2),
    lowerarm_r=(-0.2, 0.3, 0.9),
)
_BIRD = derive(
    GUARD,
    off=(0, -0.14, -0.1),
    rot={"pelvis": (0, 0, -24), "spine_03": (-14, 0, -30), "head": (4, 0, 24)},
    upperarm_r=(0.0, -1, 0.12),
    lowerarm_r=(0.0, -1, 0.15),
    hand_r=(0, -0.6, 0.8),
    upperarm_l=(0.7, 0.4, -0.5),
    lowerarm_l=(0.5, 0.2, -0.8),
)
_TALK_1 = derive(
    STAND,
    rot={"head": (-3, 0, 6)},
    upperarm_r=(-0.3, -0.25, -1),
    lowerarm_r=(-0.1, -0.9, 0.3),
    hand_r=(0, -0.8, 0.5),
)
_TALK_2 = derive(
    STAND,
    rot={"head": (2, 0, -5), "spine_03": (-2, 0, -3)},
    upperarm_r=(-0.4, -0.2, -1),
    lowerarm_r=(-0.4, -0.8, 0.1),
    hand_r=(-0.4, -0.8, 0.3),
    upperarm_l=(0.3, -0.1, -1),
    lowerarm_l=(0.2, -0.7, -0.4),
)
_RIDE = derive(
    STAND,
    off=(0, 0.0, -0.42),
    rot={"pelvis": (-8, 0, 0), "spine_03": (-6, 0, 0), "head": (6, 0, 0)},
    thigh_l=(0.3, -1, -0.12),
    calf_l=(0.05, -0.15, -1),
    thigh_r=(-0.3, -1, -0.12),
    calf_r=(-0.05, -0.15, -1),
    upperarm_l=(0.35, -0.8, -0.45),
    lowerarm_l=(0.0, -1, 0.05),
    hand_l=(-0.2, -1, 0),
    upperarm_r=(-0.35, -0.8, -0.45),
    lowerarm_r=(0.0, -1, 0.05),
    hand_r=(0.2, -1, 0),
)
_RIDE_BOB = derive(_RIDE, rot={"pelvis": (-8, 0, 0), "spine_03": (-7, 0, 0), "head": (5, 0, 0)})
_RIDE_KICK = derive(
    _RIDE,
    rot={"pelvis": (-8, -10, 0), "spine_03": (-6, 12, 0)},
    thigh_l=(1, -0.3, 0.05),
    calf_l=(1, -0.1, 0.0),
    foot_l=(0.2, -0.2, 1),
)


_IDLE_A = derive(STAND, rot={"spine_03": (1.5, 0, 0)})
_IDLE_B = derive(
    STAND,
    off=(0, 0, -0.012),
    rot={"spine_03": (-1.5, 0, 0), "head": (1.5, 0, 0)},
    upperarm_l=(0.26, 0.05, -1),
    upperarm_r=(-0.26, 0.05, -1),
)
_FIGHT_BOUNCE = derive(
    GUARD,
    off=(0, 0, -0.10),
    rot={"pelvis": (0, 0, -22), "spine_03": (-8, 0, 8), "head": (5, 0, 14)},
)
_WALK_CONTACT, _WALK_PASS = _stride(0.48, 0.5, 0.25, 0.3, 3, 0.03)
_RUN_CONTACT, _RUN_PASS = _stride(0.85, 0.9, 0.9, 0.65, 12, 0.06)
_RIDE_KICK_R = mirror(_RIDE_KICK)

BUILTIN_CLIPS: dict[str, ClipDef] = {
    clip.name: clip
    for clip in (
        ClipDef("Idle", ((1, _IDLE_A), (30, _IDLE_B), (60, _IDLE_A)), loop=True),
        ClipDef("FightIdle", ((1, GUARD), (12, _FIGHT_BOUNCE), (24, GUARD)), loop=True),
        ClipDef(
            "Walk",
            ((1, _WALK_CONTACT), (7, _WALK_PASS), (13, mirror(_WALK_CONTACT))),
            mirror_half=True,
            loop=True,
        ),
        ClipDef(
            "Run",
            ((1, _RUN_CONTACT), (5, _RUN_PASS), (9, mirror(_RUN_CONTACT))),
            mirror_half=True,
            loop=True,
        ),
        ClipDef("Punch1", ((1, GUARD), (4, _JAB), (6, _JAB), (11, GUARD))),
        ClipDef("Punch2", ((1, GUARD), (5, _CROSS), (7, _CROSS), (12, GUARD))),
        ClipDef("Punch3", ((1, GUARD), (5, _WIND), (9, _UPPER), (12, _UPPER), (18, GUARD))),
        ClipDef("Kick", ((1, GUARD), (4, _CHAMBER), (7, _KICK), (9, _KICK), (14, GUARD))),
        ClipDef("Jump", ((1, STAND), (4, _CROUCH), (8, _TUCK), (20, _TUCK))),
        ClipDef("JumpKick", ((1, _TUCK), (4, _FLY), (20, _FLY))),
        ClipDef("Hit", ((1, GUARD), (3, _FLINCH), (6, _FLINCH), (11, GUARD))),
        ClipDef(
            "Knockdown",
            (
                (1, _FLINCH),
                (7, _AIR),
                (13, _DOWN),
                (15, derive(_DOWN, off=(0, 0.55, -0.82))),
                (18, _DOWN),
            ),
        ),
        ClipDef("Down", ((1, _DOWN), (30, _DOWN)), loop=True),
        ClipDef("GetUp", ((1, _DOWN), (10, _SIT), (18, _CROUCH), (26, GUARD))),
        ClipDef(
            "Grab", ((1, GUARD), (5, _GRAB), (25, derive(_GRAB, off=(0, -0.05, -0.1))), (45, _GRAB))
        ),
        ClipDef("GrabKnee", ((1, _GRAB), (4, _KNEE), (6, _KNEE), (11, _GRAB))),
        ClipDef("Throw", ((1, _GRAB), (6, _LOAD), (10, _HURL), (13, _HURL), (19, GUARD))),
        ClipDef(
            "Held",
            (
                (1, _HELD),
                (15, derive(_HELD, rot={"spine_03": (18, 0, 6), "head": (20, 0, -8)})),
                (30, _HELD),
            ),
            loop=True,
        ),
        ClipDef(
            "Roar",
            (
                (1, GUARD),
                (6, _FLEX),
                (12, _SKY),
                (22, _SKY),
                (27, _HIGH),
                (31, _SLAM),
                (38, _SLAM),
                (46, GUARD),
            ),
        ),
        ClipDef("Special", ((1, GUARD), (5, _THROW_BACK), (9, _BIRD), (16, _BIRD), (22, GUARD))),
        ClipDef(
            "Talk",
            ((1, STAND), (12, _TALK_1), (26, _TALK_2), (40, _TALK_1), (54, STAND)),
            loop=True,
        ),
        ClipDef("Ride", ((1, _RIDE), (30, _RIDE_BOB), (60, _RIDE)), loop=True),
        ClipDef("RideKickL", ((1, _RIDE), (4, _RIDE_KICK), (7, _RIDE_KICK), (12, _RIDE))),
        ClipDef("RideKickR", ((1, _RIDE), (4, _RIDE_KICK_R), (7, _RIDE_KICK_R), (12, _RIDE))),
    )
}


def expand(clip: ClipDef) -> list[tuple[int, Pose]]:
    """Return every (frame, pose) of a clip, with the mirrored second half when mirror_half is set.

    Raises ValueError when a loop clip does not close, since the authored keys must return to start.
    """
    keys = list(clip.keys)
    if clip.mirror_half:
        first_frame = clip.keys[0][0]
        half_frame = clip.keys[-1][0]
        keys += [
            (half_frame + (frame - first_frame), mirror(pose_)) for frame, pose_ in clip.keys[1:]
        ]
    if clip.loop and keys[-1][1] != keys[0][1]:
        raise ValueError(f"Clip {clip.name} is a loop, but its last pose is not its first.")
    return keys


def targets(clip: ClipDef) -> frozenset[str]:
    """Bones that any expanded pose gives a direction or an Euler rotation."""
    bones: set[str] = set()
    for _, pose_ in expand(clip):
        bones.update(pose_["dir"])
        bones.update(pose_["rot"])
    return frozenset(bones)


def clip_digest(clip: ClipDef) -> str:
    """SHA-256 of the canonical JSON of the clip's declared definition, with floats at 6 places."""
    payload = {
        "name": clip.name,
        "mirror_half": clip.mirror_half,
        "loop": clip.loop,
        "keys": [[frame, _canonical_pose(pose_)] for frame, pose_ in clip.keys],
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_pose(pose_: Pose) -> dict[str, Any]:
    return {
        "dir": {bone: _canonical_vector(value) for bone, value in sorted(pose_["dir"].items())},
        "rot": {bone: _canonical_vector(value) for bone, value in sorted(pose_["rot"].items())},
        "off": _canonical_vector(pose_["off"]),
    }


def _canonical_vector(value: Iterable[float]) -> list[float]:
    return [round(float(component), 6) + 0.0 for component in value]
