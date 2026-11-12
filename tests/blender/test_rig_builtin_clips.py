"""Built-in procedural clips on two rig_humanoid rigs of different proportions (SCN001-SCN012).

Oracles read the evaluated pose at each authored key frame. The scene runs at 30 fps so an authored
frame is the scene frame. Each rig is built in its own scene: built-in actions are named after their
clip, so two rigs in one scene would share and replace each other's actions.
"""

from __future__ import annotations

import importlib
import json
import math
import pathlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .rig_fixtures import build_hero, build_library, build_variant, reset_scene  # noqa: E402

RIGS = ("Hero", "Variant")
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
_FILE_STATUS = "fallback required"


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.rig_core")


@pytest.fixture()
def clips(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.rig_core.builtin_clips")


@pytest.fixture()
def procedural(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.rig_core.procedural")


def _build_rig(core: Any, name: str) -> Any:
    """Reset the scene, build one humanoid called name, and return its SK_<name> armature."""
    reset_scene()
    bpy.context.scene.render.fps = 30
    landmarks = build_hero() if name == "Hero" else build_variant()
    assert core.rig_humanoid(name, "humanoid", landmarks)["status"] == "ok"
    return bpy.data.objects[f"SK_{name}"]


def _fcurves(action: Any) -> list[Any]:
    return [
        curve
        for layer in action.layers
        for strip in layer.strips
        for bag in strip.channelbags
        for curve in bag.fcurves
    ]


def _key_table(action: Any) -> dict[tuple[str, int], list[tuple[float, float]]]:
    return {
        (curve.data_path, curve.array_index): [tuple(point.co) for point in curve.keyframe_points]
        for curve in _fcurves(action)
    }


def _play(armature: Any, clip_name: str) -> None:
    armature.animation_data_create().action = bpy.data.actions[clip_name]


def _pose_at(armature: Any, frame: int) -> Any:
    """Evaluated pose bones (armature space) at frame, indexable by bone name."""
    bpy.context.scene.frame_set(frame)
    return armature.evaluated_get(bpy.context.evaluated_depsgraph_get()).pose.bones


def _y_axis(pose_bone: Any) -> Any:
    return pose_bone.matrix.to_3x3() @ _vector(0.0, 1.0, 0.0)


def _signature(pose_bones: Any) -> list[float]:
    return [value for pose_bone in pose_bones for row in pose_bone.matrix for value in row]


def _vector(x: float, y: float, z: float) -> Any:
    from mathutils import Vector  # noqa: PLC0415

    return Vector((x, y, z))


def _angle_degrees(a: Any, b: Any) -> float:
    return math.degrees(_vector(*a).normalized().angle(_vector(*b).normalized()))


def _leg_length(armature: Any) -> float:
    bones = armature.data.bones
    return (
        sum(
            (bones[f"calf_{side}"].head_local - bones[f"thigh_{side}"].head_local).length
            + (bones[f"foot_{side}"].head_local - bones[f"calf_{side}"].head_local).length
            for side in ("l", "r")
        )
        / 2.0
    )


def _assert_rest_pose(armature: Any) -> None:
    for pose_bone in armature.pose.bones:
        assert tuple(pose_bone.rotation_quaternion) == pytest.approx((1.0, 0.0, 0.0, 0.0), abs=1e-6)
        assert tuple(pose_bone.location) == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)


def _no_file_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("built-in baking must not read a file")

    monkeypatch.setattr("builtins.open", refuse)
    monkeypatch.setattr(pathlib.Path, "read_bytes", refuse)
    monkeypatch.setattr(pathlib.Path, "read_text", refuse)


def _action_names() -> set[str]:
    return {action.name for action in bpy.data.actions}


@pytest.fixture(params=RIGS)
def rig(request: pytest.FixtureRequest) -> Iterator[str]:
    yield request.param


# ----------------------------------------------------------------------------- SCN001, SCN002
def test_scn001_scn002_every_builtin_clip_bakes_with_no_file_access(
    core: Any, clips: Any, rig: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    armature = _build_rig(core, rig)
    _no_file_reads(monkeypatch)

    result = core.import_animations(rig, library="builtin")

    assert result["status"] == "ok", result
    names = [clip["name"] for clip in result["clips"]]
    assert set(AC2_CLIPS) <= set(names)
    assert names == list(clips.BUILTIN_CLIPS)
    for clip in clips.BUILTIN_CLIPS.values():
        paths = {curve.data_path for curve in _fcurves(bpy.data.actions[clip.name])}
        for bone in clips.targets(clip):
            assert f'pose.bones["{bone}"].rotation_quaternion' in paths, (clip.name, bone)
    assert not [name for name in _action_names() if name.startswith("__nmg_tmp_")]
    _assert_rest_pose(armature)


# ----------------------------------------------------------------------------- SCN003
def test_scn003_a_subset_bakes_only_the_requested_clips(core: Any, clips: Any, rig: str) -> None:
    _build_rig(core, rig)

    result = core.import_animations(rig, library="builtin", clips=["Idle", "Walk"])

    assert result["status"] == "ok", result
    assert [clip["name"] for clip in result["clips"]] == ["Idle", "Walk"]
    built_in = {name for name in _action_names() if name in clips.BUILTIN_CLIPS}
    assert built_in == {"Idle", "Walk"}


# ----------------------------------------------------------------------------- SCN004
def test_scn004_targeted_limbs_point_along_their_direction_within_2_degrees(
    core: Any, clips: Any, rig: str
) -> None:
    armature = _build_rig(core, rig)
    names = ["Idle", "Walk", "Punch3", "Kick", "Jump", "Talk"]
    assert core.import_animations(rig, library="builtin", clips=names)["status"] == "ok"

    for name in names:
        _play(armature, name)
        for frame, pose in clips.expand(clips.BUILTIN_CLIPS[name]):
            evaluated = _pose_at(armature, frame)
            for bone, target in pose["dir"].items():
                error = _angle_degrees(_y_axis(evaluated[bone]), target)
                assert error <= 2.0, f"{rig} {name} frame {frame} {bone}: {error:.3f} deg"


# ----------------------------------------------------------------------------- SCN005
def test_scn005_pelvis_moves_by_offset_times_leg_length(core: Any, clips: Any, rig: str) -> None:
    armature = _build_rig(core, rig)
    assert core.import_animations(rig, library="builtin", clips=["Jump", "Down"])["status"] == "ok"
    leg = _leg_length(armature)
    rest_head = armature.data.bones["pelvis"].head_local

    for name in ("Jump", "Down"):
        _play(armature, name)
        for frame, pose in clips.expand(clips.BUILTIN_CLIPS[name]):
            displacement = _pose_at(armature, frame)["pelvis"].matrix.to_translation() - rest_head
            expected = [component * leg for component in pose["off"]]
            for got, want in zip(displacement, expected, strict=True):
                assert got == pytest.approx(want, abs=1e-4), f"{rig} {name} frame {frame}"


# ----------------------------------------------------------------------------- SCN006
def test_scn006_cycles_are_mirrored_and_the_four_cycles_loop(
    core: Any, clips: Any, rig: str
) -> None:
    armature = _build_rig(core, rig)
    names = ["Idle", "FightIdle", "Walk", "Run"]
    assert core.import_animations(rig, library="builtin", clips=names)["status"] == "ok"

    for name in names:
        _play(armature, name)
        expanded = clips.expand(clips.BUILTIN_CLIPS[name])
        first = _signature(_pose_at(armature, expanded[0][0]))
        last = _signature(_pose_at(armature, expanded[-1][0]))
        assert len(first) == len(last)
        assert max(abs(a - b) for a, b in zip(first, last, strict=True)) <= 1e-4, name

    for name in ("Walk", "Run"):
        _play(armature, name)
        expanded = clips.expand(clips.BUILTIN_CLIPS[name])
        for left, right in (
            ("upperarm_l", "upperarm_r"),
            ("thigh_l", "thigh_r"),
            ("calf_l", "calf_r"),
        ):
            for source, mirrored in ((0, 2), (1, 3)):
                y_left = _y_axis(_pose_at(armature, expanded[source][0])[left])
                y_right = _y_axis(_pose_at(armature, expanded[mirrored][0])[right])
                reflected = (-y_left[0], y_left[1], y_left[2])
                error = _angle_degrees(tuple(y_right), reflected)
                assert error <= 2.0, (
                    f"{rig} {name} {left} at keys {source}/{mirrored}: {error:.3f} deg"
                )


# ----------------------------------------------------------------------------- SCN007
def test_scn007_provenance_matches_the_definition_and_survives_export(
    core: Any, clips: Any, rig: str, tmp_path: Path
) -> None:
    _build_rig(core, rig)
    names = ["Idle", "Walk", "Jump"]

    baked = core.import_animations(rig, library="builtin", clips=names)

    assert baked["status"] == "ok", baked
    by_name = {clip["name"]: clip for clip in baked["clips"]}
    for name in names:
        clip = by_name[name]
        definition = clips.BUILTIN_CLIPS[name]
        assert clip["fps"] == bpy.context.scene.render.fps
        assert clip["frame_start"] == clips.expand(definition)[0][0]
        assert clip["frame_end"] == clips.expand(definition)[-1][0]
        assert clip["frame_count"] == clip["frame_end"] - clip["frame_start"] + 1
        assert clip["source"] == {
            "library": "builtin",
            "file": None,
            "sha256": clips.clip_digest(definition),
            "skeleton": "manny",
        }

    out_dir = tmp_path / "out"
    exported = core.export_rigged(rig, str(out_dir))

    assert exported["status"] == "ok", exported
    sidecar = json.loads((out_dir / "nmg-animations.json").read_text(encoding="utf-8"))
    assert [clip["name"] for clip in sidecar["clips"]] == sorted(names)
    for clip in sidecar["clips"]:
        assert clip["source"]["library"] == "builtin"
        assert clip["source"]["file"] is None
        assert clip["source"]["sha256"] == clips.clip_digest(clips.BUILTIN_CLIPS[clip["name"]])

    reset_scene()
    assert bpy.ops.import_scene.fbx(filepath=str(out_dir / f"SM_{rig}.fbx")) == {"FINISHED"}
    reimported = {action.name.rsplit("|", 1)[-1] for action in bpy.data.actions}
    assert set(names) <= reimported


# ----------------------------------------------------------------------------- SCN008
def test_scn008_baking_again_replaces_the_action_with_identical_keys_and_provenance(
    core: Any, rig: str
) -> None:
    _build_rig(core, rig)
    first = core.import_animations(rig, library="builtin", clips=["Idle"])
    keys_first = _key_table(bpy.data.actions["Idle"])
    actions_first = sorted(action.name for action in bpy.data.actions)

    second = core.import_animations(rig, library="builtin", clips=["Idle"])

    assert second["status"] == "ok", second
    assert second["clips"] == first["clips"]
    assert _key_table(bpy.data.actions["Idle"]) == keys_first
    assert sorted(action.name for action in bpy.data.actions) == actions_first
    assert not [action.name for action in bpy.data.actions if action.name.startswith("__nmg_tmp_")]


# ----------------------------------------------------------------------------- SCN009
def test_scn009_unknown_clip_is_reported_and_nothing_is_baked(
    core: Any, clips: Any, rig: str
) -> None:
    _build_rig(core, rig)
    actions_before = sorted(action.name for action in bpy.data.actions)

    result = core.import_animations(rig, library="builtin", clips=["Idle", "Bogus"])

    assert result["status"] == _FILE_STATUS
    assert result["code"] == "anim.clip_not_found"
    assert all(name in result["remediation"] for name in clips.BUILTIN_CLIPS)
    assert sorted(action.name for action in bpy.data.actions) == actions_before


# ----------------------------------------------------------------------------- SCN010
def test_scn010_invalid_library_selection_changes_nothing(
    core: Any, rig: str, tmp_path: Path
) -> None:
    armature = _build_rig(core, rig)
    actions_before = sorted(action.name for action in bpy.data.actions)
    selections = (
        {"library_dir": str(tmp_path), "library": "builtin"},
        {"library_dir": None, "library": None},
        {"library_dir": None, "library": "mixamo"},
    )

    for selection in selections:
        result = core.import_animations(rig, **selection)
        assert result["status"] == _FILE_STATUS, selection
        assert result["code"] == "anim.library_invalid", selection
        assert sorted(action.name for action in bpy.data.actions) == actions_before, selection
        assert armature.get("nmg_animations") is None, selection
        _assert_rest_pose(armature)


# ----------------------------------------------------------------------------- SCN011
def test_scn011_file_and_builtin_clips_share_one_rig(core: Any, rig: str, tmp_path: Path) -> None:
    _build_rig(core, rig)
    library = build_library(tmp_path / "library")

    from_file = core.import_animations(rig, str(library))
    from_builtin = core.import_animations(rig, library="builtin", clips=["Jump"])

    assert from_file["status"] == "ok", from_file
    assert from_builtin["status"] == "ok", from_builtin
    assert {clip["name"]: clip["source"]["file"] for clip in from_file["clips"]} == {
        "Idle": "idle.fbx",
        "Walk": "walk.bvh",
    }
    out_dir = tmp_path / "out"
    assert core.export_rigged(rig, str(out_dir))["status"] == "ok"
    sidecar = json.loads((out_dir / "nmg-animations.json").read_text(encoding="utf-8"))
    sources = {clip["name"]: clip["source"] for clip in sidecar["clips"]}
    assert set(sources) == {"Idle", "Walk", "Jump"}
    assert sources["Idle"]["file"] == "idle.fbx"
    assert sources["Jump"]["library"] == "builtin"
    assert sources["Jump"]["file"] is None


# ----------------------------------------------------------------------------- SCN012
def test_scn012_missing_rig_and_text_motion_keep_their_statuses(core: Any, rig: str) -> None:
    reset_scene()
    missing = core.import_animations("Ghost", library="builtin")
    assert missing["code"] == "anim.rig_missing", missing

    _build_rig(core, rig)
    spike = core.import_animations(rig, library="builtin", motion_prompt="a slow limp")
    assert spike["code"] == "anim.text_motion_unsupported", spike
    assert spike["status"] == "follow-up spike required"
