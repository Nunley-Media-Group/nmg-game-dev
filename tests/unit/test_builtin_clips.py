"""Built-in clip library in plain CPython (SCN001-SCN012 oracles without Blender).

rig_core/__init__.py imports bpy, so this loads procedural.py, builtin_clips.py, and skeleton.py
through a synthetic package whose __path__ is rig_core/. Two synthetic rest skeletons stand in for
rigs: a T-pose humanoid and one with longer legs and arms 45 degrees below horizontal.
"""

from __future__ import annotations

import dataclasses
import importlib
import math
import sys
import types
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

_RIG_CORE = (
    Path(__file__).resolve().parents[2] / "plugins" / "nmg-game-dev-blender-addon" / "rig_core"
)
_PACKAGE = "nmg_rig_core_pure"


def _ensure_package() -> None:
    if _PACKAGE not in sys.modules:
        package = types.ModuleType(_PACKAGE)
        package.__path__ = [str(_RIG_CORE)]
        sys.modules[_PACKAGE] = package


def _module(name: str) -> Any:
    _ensure_package()
    return importlib.import_module(f"{_PACKAGE}.{name}")


skeleton = _module("skeleton")
procedural = _module("procedural")
builtin_clips = _module("builtin_clips")

AC2_CLIPS = (
    "Idle",
    "FightIdle",
    "Walk",
    "Run",
    "Punch1",
    "Punch2",
    "Punch3",
    "Kick",
    "Jump",
    "JumpKick",
    "Hit",
    "Knockdown",
    "Down",
    "GetUp",
    "Grab",
    "Throw",
    "Roar",
    "Talk",
    "Ride",
)
LIMB_KEYS = frozenset(
    f"{base}_{side}"
    for base in ("clavicle", "upperarm", "lowerarm", "hand", "thigh", "calf", "foot", "ball")
    for side in ("l", "r")
)
CENTRE_KEYS = frozenset(
    {
        "pelvis",
        "spine_01",
        "spine_02",
        "spine_03",
        "spine_04",
        "spine_05",
        "neck_01",
        "neck_02",
        "head",
    }
)


def _landmarks(
    *,
    pelvis_z: float,
    knee_z: float,
    hip_x: float,
    shoulder_x: float,
    shoulder_z: float,
    arm_drop_deg: float,
    upper: float,
    lower: float,
    hand: float,
) -> dict[str, list[float]]:
    """Symmetric landmarks; arm_drop_deg is how far the arms hang below horizontal."""
    cos = math.cos(math.radians(arm_drop_deg))
    sin = math.sin(math.radians(arm_drop_deg))
    marks: dict[str, list[float]] = {
        "pelvis": [0.0, 0.0, pelvis_z],
        "neck": [0.0, 0.0, pelvis_z + 0.42],
        "head_top": [0.0, 0.0, pelvis_z + 0.76],
    }
    for side, sign in (("l", 1.0), ("r", -1.0)):
        shoulder = [sign * shoulder_x, 0.0, shoulder_z]
        elbow = [shoulder[0] + sign * upper * cos, 0.0, shoulder_z - upper * sin]
        wrist = [elbow[0] + sign * lower * cos, 0.0, elbow[2] - lower * sin]
        hand_tip = [wrist[0] + sign * hand * cos, 0.0, wrist[2] - hand * sin]
        marks[f"shoulder_{side}"] = shoulder
        marks[f"elbow_{side}"] = elbow
        marks[f"wrist_{side}"] = wrist
        marks[f"hand_tip_{side}"] = hand_tip
        marks[f"hip_{side}"] = [sign * hip_x, 0.0, pelvis_z - 0.05]
        marks[f"knee_{side}"] = [sign * hip_x, 0.0, knee_z]
        marks[f"ankle_{side}"] = [sign * hip_x, 0.0, 0.08]
        marks[f"toe_{side}"] = [sign * hip_x, -0.15, 0.03]
    return marks


def _sub(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(x - y for x, y in zip(a, b, strict=True))


def _cross(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(v: tuple[float, ...]) -> tuple[float, float, float]:
    length = math.sqrt(sum(x * x for x in v))
    return (v[0] / length, v[1] / length, v[2] / length)


def _rest_rotation(head: Any, tail: Any) -> tuple[Any, Any, Any]:
    """Rows of a rest rotation whose Y axis runs head to tail, with a fixed roll."""
    y = _unit(_sub(tuple(tail), tuple(head)))
    reference = (0.0, 0.0, 1.0) if abs(y[2]) < 0.9 else (1.0, 0.0, 0.0)
    x = _unit(_cross(y, reference))
    z = _cross(x, y)
    return ((x[0], y[0], z[0]), (x[1], y[1], z[1]), (x[2], y[2], z[2]))


def _rest_skeleton(marks: Mapping[str, list[float]]) -> Any:
    layout = skeleton.bone_layout(marks)
    rotations = {bone: _rest_rotation(head, tail) for bone, (head, tail) in layout.items()}
    heads = {bone: tuple(head) for bone, (head, _) in layout.items()}
    return procedural.RestSkeleton.from_bones(rotations, heads)


def _rig_t_pose() -> Any:
    return _rest_skeleton(
        _landmarks(
            pelvis_z=1.0,
            knee_z=0.5,
            hip_x=0.1,
            shoulder_x=0.2,
            shoulder_z=1.45,
            arm_drop_deg=0.0,
            upper=0.3,
            lower=0.3,
            hand=0.1,
        )
    )


def _rig_long_legs_arms_down() -> Any:
    return _rest_skeleton(
        _landmarks(
            pelvis_z=1.05,
            knee_z=0.55,
            hip_x=0.13,
            shoulder_x=0.26,
            shoulder_z=1.5,
            arm_drop_deg=45.0,
            upper=0.26,
            lower=0.24,
            hand=0.1,
        )
    )


RIGS = {"t_pose": _rig_t_pose, "long_legs_arms_down": _rig_long_legs_arms_down}


def _world_rotations(
    rest: Any, quats: Mapping[str, tuple[float, float, float, float]]
) -> dict[str, Any]:
    """Armature-space rotation of each bone, composed the way Blender poses a chain."""
    world: dict[str, Any] = {}
    identity = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    for bone, parent in skeleton.MANNY_BONES:
        rest_rot = rest.rotations[bone]
        relative = (
            rest_rot
            if parent is None
            else procedural.mat_mul(procedural.transpose(rest.rotations[parent]), rest_rot)
        )
        parent_world = identity if parent is None else world[parent]
        local = procedural.quat_to_matrix(quats[bone])
        world[bone] = procedural.mat_mul(parent_world, procedural.mat_mul(relative, local))
    return world


def _angle_degrees(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    ua, ub = _unit(a), _unit(b)
    cosine = max(-1.0, min(1.0, sum(x * y for x, y in zip(ua, ub, strict=True))))
    return math.degrees(math.acos(cosine))


def _column(m: Any, index: int) -> tuple[float, float, float]:
    return (m[0][index], m[1][index], m[2][index])


def _leg_length(rest: Any) -> float:
    heads = rest.heads
    return (
        sum(
            math.dist(heads[f"thigh_{side}"], heads[f"calf_{side}"])
            + math.dist(heads[f"calf_{side}"], heads[f"foot_{side}"])
            for side in ("l", "r")
        )
        / 2.0
    )


# ----------------------------------------------------------------------- AC2, AC6, AC7 definitions
def test_ac2_every_named_clip_is_defined_and_the_set_has_24_clips() -> None:
    assert set(AC2_CLIPS) <= set(builtin_clips.BUILTIN_CLIPS)
    assert len(builtin_clips.BUILTIN_CLIPS) == 24
    assert tuple(builtin_clips.BUILTIN_CLIPS)[:4] == ("Idle", "FightIdle", "Walk", "Run")


def test_authored_fps_is_30() -> None:
    assert builtin_clips.AUTHORED_FPS == 30


def test_every_targeted_bone_is_a_manny_bone_and_uses_the_right_key_set() -> None:
    manny = set(skeleton.MANNY_BONE_NAMES)
    for name, clip in builtin_clips.BUILTIN_CLIPS.items():
        assert builtin_clips.targets(clip) <= manny, name
        for _, pose in builtin_clips.expand(clip):
            assert set(pose["dir"]) <= LIMB_KEYS, name
            assert set(pose["rot"]) <= CENTRE_KEYS, name


def test_walk_and_run_are_mirrored_half_cycles_and_the_four_cycles_loop() -> None:
    clips = builtin_clips.BUILTIN_CLIPS
    assert clips["Walk"].mirror_half and clips["Run"].mirror_half
    for name in ("Idle", "FightIdle", "Walk", "Run"):
        assert clips[name].loop, name
        expanded = builtin_clips.expand(clips[name])
        assert expanded[-1][1] == expanded[0][1], name


def test_second_half_of_walk_and_run_is_the_left_right_mirror_of_the_first() -> None:
    for name in ("Walk", "Run"):
        poses = [pose for _, pose in builtin_clips.expand(builtin_clips.BUILTIN_CLIPS[name])]
        assert poses[2] == builtin_clips.mirror(poses[0]), name
        assert poses[3] == builtin_clips.mirror(poses[1]), name


def test_jump_and_down_move_the_pelvis() -> None:
    for name in ("Jump", "Down"):
        clip = builtin_clips.BUILTIN_CLIPS[name]
        assert any(any(pose["off"]) for _, pose in builtin_clips.expand(clip)), name


def test_loop_clip_that_does_not_close_is_rejected() -> None:
    open_clip = builtin_clips.ClipDef(
        name="Open",
        keys=((1, builtin_clips.STAND), (10, builtin_clips.GUARD)),
        loop=True,
    )
    with pytest.raises(ValueError, match="Open"):
        builtin_clips.expand(open_clip)


def test_clip_digest_is_stable_and_changes_when_a_pose_changes() -> None:
    idle = builtin_clips.BUILTIN_CLIPS["Idle"]
    assert builtin_clips.clip_digest(idle) == builtin_clips.clip_digest(idle)
    changed_pose = builtin_clips.derive(builtin_clips.STAND, upperarm_l=(0.3, 0.05, -1))
    changed = dataclasses.replace(
        idle,
        keys=((idle.keys[0][0], changed_pose), *idle.keys[1:]),
    )
    assert builtin_clips.clip_digest(changed) != builtin_clips.clip_digest(idle)


# ----------------------------------------------------------------------------- AC4, AC5 on two rigs
@pytest.mark.parametrize("rig_name", list(RIGS))
def test_ac4_every_targeted_limb_points_along_its_direction_within_2_degrees(rig_name: str) -> None:
    rest = RIGS[rig_name]()
    for name, clip in builtin_clips.BUILTIN_CLIPS.items():
        for frame, pose in builtin_clips.expand(clip):
            quats, _ = procedural.solve(rest, pose)
            world = _world_rotations(rest, quats)
            for bone, target in pose["dir"].items():
                error = _angle_degrees(_column(world[bone], 1), target)
                assert error <= 2.0, f"{rig_name} {name} frame {frame} {bone}: {error:.3f} deg"


@pytest.mark.parametrize("rig_name", list(RIGS))
def test_ac5_pelvis_displacement_is_offset_times_leg_length(rig_name: str) -> None:
    rest = RIGS[rig_name]()
    leg = _leg_length(rest)
    assert rest.leg_length == pytest.approx(leg)
    for name in ("Jump", "Down"):
        for frame, pose in builtin_clips.expand(builtin_clips.BUILTIN_CLIPS[name]):
            quats, location = procedural.solve(rest, pose)
            world = _world_rotations(rest, quats)
            root_to_pelvis = procedural.mat_mul(
                procedural.transpose(rest.rotations["root"]), rest.rotations["pelvis"]
            )
            displacement = procedural._apply(  # noqa: SLF001 — checks the composed pose chain
                procedural.mat_mul(world["root"], root_to_pelvis), location
            )
            expected = tuple(component * leg for component in pose["off"])
            for got, want in zip(displacement, expected, strict=True):
                assert got == pytest.approx(want, abs=1e-9), f"{rig_name} {name} frame {frame}"


# ----------------------------------------------------------------------------- solver helpers
def test_continuous_flips_a_quaternion_onto_the_side_of_its_predecessor() -> None:
    previous = (1.0, 0.0, 0.0, 0.0)
    flipped = (-0.5, 0.5, 0.5, 0.5)
    assert procedural.continuous(previous, flipped) == (0.5, -0.5, -0.5, -0.5)
    assert procedural.continuous(None, flipped) == flipped


def test_matrix_quaternion_round_trip_and_rotation_between() -> None:
    raw = (0.6, 0.48, -0.36, 0.52)
    norm = math.sqrt(sum(x * x for x in raw))
    quat = (raw[0] / norm, raw[1] / norm, raw[2] / norm, raw[3] / norm)
    back = procedural.matrix_to_quat(procedural.quat_to_matrix(quat))
    assert back == pytest.approx(quat, abs=1e-9)
    turn = procedural.rotation_between((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    assert _column(turn, 0) == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)
    flip = procedural.rotation_between((0.0, 0.0, 1.0), (0.0, 0.0, -1.0))
    assert _column(flip, 2) == pytest.approx((0.0, 0.0, -1.0), abs=1e-9)


def test_mirror_is_an_involution_and_swaps_sides() -> None:
    pose = builtin_clips.BUILTIN_CLIPS["Punch2"].keys[1][1]
    assert builtin_clips.mirror(builtin_clips.mirror(pose)) == pose
    mirrored = builtin_clips.mirror(pose)
    assert mirrored["dir"]["upperarm_l"] == (
        -pose["dir"]["upperarm_r"][0],
        pose["dir"]["upperarm_r"][1],
        pose["dir"]["upperarm_r"][2],
    )


def test_merge_only_replaces_the_offset_when_the_override_names_one() -> None:
    merged = builtin_clips.merge(builtin_clips.GUARD, {"dir": {"hand_r": (1.0, 0.0, 0.0)}})
    assert merged["off"] == builtin_clips.GUARD["off"]
    assert merged["dir"]["hand_r"] == (1.0, 0.0, 0.0)
    assert merged["dir"]["upperarm_l"] == builtin_clips.GUARD["dir"]["upperarm_l"]
