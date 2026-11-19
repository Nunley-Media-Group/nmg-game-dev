"""Per-clip animation export under Blender headless: SCN001-SCN003 and SCN011 of #138.

A rig ``SK_Hero`` in collection ``Hero`` holds clips in three ways: a provenance clip, an action
on the rig's NLA track, and an unrelated action that nothing holds.  Each test exports through
``finalize_core.anims`` and, where it matters, re-imports the written GLB into a fresh scene.

Run with scripts/run-blender-tests.sh.  Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

_COLLECTION = "Hero"
_ARMATURE = f"SK_{_COLLECTION}"


def _reset() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for armature in list(bpy.data.armatures):
        bpy.data.armatures.remove(armature)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def _rig(name: str = _COLLECTION) -> Any:
    """Build SK_<name> in collection <name> with a root and a spine bone."""
    armature = f"SK_{name}"
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    data = bpy.data.armatures.new(armature)
    rig = bpy.data.objects.new(armature, data)
    collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    root = data.edit_bones.new("root")
    root.head = (0.0, 0.0, 0.0)
    root.tail = (0.0, 0.0, 0.5)
    spine = data.edit_bones.new("spine")
    spine.head = (0.0, 0.0, 0.5)
    spine.tail = (0.0, 0.0, 1.0)
    spine.parent = root
    bpy.ops.object.mode_set(mode="OBJECT")
    return rig


def _clip(rig: Any, name: str, frames: tuple[int, int], lift: float) -> Any:
    """Key the root bone from ``frames`` as a fake-user action named ``name``."""
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = action
    bone = rig.pose.bones["root"]
    for frame in frames:
        bone.location = (0.0, 0.0, lift * frame)
        bone.keyframe_insert(data_path="location", frame=frame)
    rig.animation_data.action = None
    return action


@pytest.fixture()
def anims(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.finalize_core.anims")


@pytest.fixture()
def scene_with_clips(anims: Any) -> Any:
    """A rig with provenance clip Idle, NLA-held Wave, and unrelated Other."""
    _reset()
    rig = _rig()
    _clip(rig, "Idle", (1, 10), 0.1)
    wave = _clip(rig, "Wave", (1, 6), 0.2)
    provenance = {
        "Idle": {
            "name": "Idle",
            "frame_start": 1,
            "frame_end": 10,
            "frame_count": 10,
            "fps": 24,
            "source": {"library": "lib", "file": "idle.fbx", "sha256": "abc", "skeleton": "manny"},
        }
    }
    rig["nmg_animations"] = json.dumps(provenance, sort_keys=True)
    track = rig.animation_data.nla_tracks.new()
    track.strips.new("Wave", 1, wave)
    _clip(rig, "Other", (1, 4), 0.3)
    yield anims
    _reset()


def test_the_clip_set_is_provenance_plus_the_rigs_actions_and_excludes_other(
    scene_with_clips: Any,
) -> None:
    # AC2 and FR2: Idle (provenance) and Wave (NLA) are exported.  Other is not.
    names = [action.name for action in scene_with_clips.resolve_clips(_COLLECTION)]

    assert names == ["Idle", "Wave"]


def test_one_armature_only_glb_per_clip_and_each_reimports_as_one_clip(
    scene_with_clips: Any, tmp_path: Path
) -> None:
    # SCN001 and AC1: each clip is its own GLB.  Re-imported, it has the armature named Armature,
    # no mesh, and exactly one action spanning the clip's frames.
    out = tmp_path / "Animations"
    records = scene_with_clips.export_clips(_COLLECTION, ["Idle", "Wave"], out)

    assert [record["file"] for record in records] == ["A_Hero_Idle.glb", "A_Hero_Wave.glb"]
    assert list(out.glob("*.fbx")) == []
    for record in records:
        bpy.ops.wm.read_homefile(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(out / record["file"]), disable_bone_shape=True)
        armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
        meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
        assert [obj.name for obj in armatures] == ["Armature"]
        assert meshes == []
        (action,) = bpy.data.actions
        start, end = action.frame_range
        assert round(end - start) + 1 == record["frame_count"], record["name"]


def _glb_animation_times(path: Path) -> tuple[float, float]:
    """Return the earliest and latest key time across every animation sampler in ``path``."""
    import struct

    data = path.read_bytes()
    (length,) = struct.unpack_from("<I", data, 12)
    document = json.loads(data[20 : 20 + length])
    inputs = [
        document["accessors"][sampler["input"]]
        for animation in document["animations"]
        for sampler in animation["samplers"]
    ]
    return min(item["min"][0] for item in inputs), max(item["max"][0] for item in inputs)


def test_a_clip_starting_after_frame_0_is_slid_to_time_0(
    scene_with_clips: Any, tmp_path: Path
) -> None:
    # #249 AC3: Godot keeps key times as written, so a clip keyed from frame 1 to 10 must start at
    # time 0 and last (frame_end - frame_start) / fps, the length import_anims expects.
    out = tmp_path / "Animations"
    (record,) = scene_with_clips.export_clips(_COLLECTION, ["Idle"], out)
    start, end = _glb_animation_times(out / record["file"])

    assert start == pytest.approx(0.0, abs=1e-6)
    expected = (record["frame_end"] - record["frame_start"]) / record["fps"]
    assert end == pytest.approx(expected, abs=1e-4)


def test_the_sidecar_fields_match_the_exported_actions_and_sources(
    scene_with_clips: Any, tmp_path: Path
) -> None:
    # SCN003 and AC3: frame range, frame count, fps, and source per clip.
    records = {
        record["name"]: record
        for record in scene_with_clips.export_clips(_COLLECTION, ["Idle", "Wave"], tmp_path)
    }

    idle = records["Idle"]
    assert (idle["frame_start"], idle["frame_end"], idle["frame_count"]) == (1, 10, 10)
    scene = bpy.context.scene
    assert idle["fps"] == pytest.approx(scene.render.fps / scene.render.fps_base)
    assert idle["source"] == {
        "library": "lib",
        "file": "idle.fbx",
        "sha256": "abc",
        "skeleton": "manny",
    }
    assert records["Wave"]["source"] == "authored"
    assert records["Wave"]["frame_count"] == 6


def test_an_invalid_clip_name_is_reported_by_the_probe_and_writes_nothing(
    scene_with_clips: Any, tmp_path: Path
) -> None:
    # SCN011: an action whose name breaks the rule is reported with valid_name false, and the
    # export raises before any file is written.
    bad = bpy.data.actions.new("Run-Fast")
    bad.use_fake_user = True
    rig = bpy.data.objects[_ARMATURE]
    rig.animation_data_create()
    track = rig.animation_data.nla_tracks.new()
    track.strips.new("Run-Fast", 1, bad)

    report = scene_with_clips.probe(_COLLECTION)
    flags = {clip["name"]: clip["valid_name"] for clip in report["clips"]}
    assert flags["Run-Fast"] is False
    assert flags["Idle"] is True

    out = tmp_path / "Animations"
    with pytest.raises(scene_with_clips.AnimError) as info:
        scene_with_clips.export_clips(_COLLECTION, ["Run-Fast"], out)
    assert info.value.code == "finalize.clip_name_invalid"
    assert not out.exists() or not any(out.iterdir())


def test_the_rig_keeps_its_name_and_actions_after_an_export(
    scene_with_clips: Any, tmp_path: Path
) -> None:
    # After export the name, action, and NLA mute states are restored.
    rig = bpy.data.objects[_ARMATURE]
    before_action = rig.animation_data.action
    before_mutes = [track.mute for track in rig.animation_data.nla_tracks]

    scene_with_clips.export_clips(_COLLECTION, ["Idle", "Wave"], tmp_path)

    assert rig.name == _ARMATURE
    assert rig.animation_data.action is before_action
    assert [track.mute for track in rig.animation_data.nla_tracks] == before_mutes


def test_the_clip_hash_changes_when_a_keyframe_changes(scene_with_clips: Any) -> None:
    # FR7 input: the clip hash covers the keyframes, so an edit to Idle changes its hash only.
    rig = bpy.data.objects[_ARMATURE]
    before = {clip["name"]: clip["hash"] for clip in scene_with_clips.probe(_COLLECTION)["clips"]}

    action = bpy.data.actions["Idle"]
    rig.animation_data_create()
    rig.animation_data.action = action
    rig.pose.bones["root"].location = (0.0, 0.0, 9.0)
    rig.pose.bones["root"].keyframe_insert(data_path="location", frame=5)
    rig.animation_data.action = None

    after = {clip["name"]: clip["hash"] for clip in scene_with_clips.probe(_COLLECTION)["clips"]}
    assert after["Idle"] != before["Idle"]
    assert after["Wave"] == before["Wave"]


def test_the_entry_step_probes_and_exports_through_finalize_core(
    enabled_addon: str, scene_with_clips: Any, tmp_path: Path
) -> None:
    # The envelope path: run_step's probe and export modes, as finalize_entry.py calls them.
    core = importlib.import_module(f"{enabled_addon}.finalize_core")
    request = {
        "collection": _COLLECTION,
        "category": "Characters",
        "asset_class": "character",
        "export_root": str(tmp_path),
    }
    probe = core.run_step("export_anims", request, tmp_path / "job", {"mode": "probe"})
    assert probe["ok"] is True
    assert [clip["name"] for clip in probe["outputs"]["clips"]] == ["Idle", "Wave"]

    exported = core.run_step(
        "export_anims", request, tmp_path / "job", {"mode": "export", "clips": ["Idle"]}
    )
    assert exported["ok"] is True
    folder = tmp_path / "Characters" / _COLLECTION / "Animations"
    assert (folder / "A_Hero_Idle.glb").is_file()
    assert not (folder / "A_Hero_Wave.glb").exists()


# ----------------------------------------------------------------------------- #233 AC1-AC6
# A clip's name is its action's name minus an optional @SK_<Name> suffix.  Each case holds its
# actions on the rig's NLA track, so the rig holds them without an active action.


def _hold(rig: Any, action: Any) -> None:
    """Hold ``action`` on ``rig`` as an NLA strip, so the rig holds it as a clip."""
    track = rig.animation_data_create().nla_tracks.new()
    track.strips.new(action.name, 1, action)


def _root_lift(action: Any) -> float:
    """Return the largest root location Z that the re-imported action keys."""
    keys = [
        point.co[1]
        for layer in action.layers
        for strip in layer.strips
        for bag in strip.channelbags
        for curve in bag.fcurves
        if curve.data_path == 'pose.bones["root"].location' and curve.array_index == 2
        for point in curve.keyframe_points
    ]
    return max(keys)


@pytest.fixture()
def one_file(anims: Any) -> Any:
    """An empty file for a case to build its rigs in; cleared before and after."""
    _reset()
    yield anims
    _reset()


@pytest.fixture()
def two_characters(one_file: Any) -> Any:
    """Two rigs in one file, each with its own Idle: SK_StreetThug and SK_Cop (AC1, AC2)."""
    thug = _rig("StreetThug")
    _hold(thug, _clip(thug, "Idle@SK_StreetThug", (1, 10), 0.1))
    cop = _rig("Cop")
    _hold(cop, _clip(cop, "Idle@SK_Cop", (1, 10), 0.3))
    return one_file


def test_ac1_an_suffixed_action_probes_and_exports_under_its_bare_name(
    two_characters: Any, tmp_path: Path
) -> None:
    # AC1: Idle@SK_StreetThug probes as Idle and exports A_StreetThug_Idle.glb named Idle.
    report = two_characters.probe("StreetThug")

    assert [(clip["name"], clip["valid_name"]) for clip in report["clips"]] == [("Idle", True)]
    assert report["rig_mismatch"] == []
    assert report["duplicates"] == []
    (record,) = two_characters.export_clips("StreetThug", ["Idle"], tmp_path)
    assert record["name"] == "Idle"
    assert record["file"] == "A_StreetThug_Idle.glb"
    assert (tmp_path / "A_StreetThug_Idle.glb").is_file()


def test_ac2_two_characters_in_one_file_each_export_their_own_clip(
    two_characters: Any, tmp_path: Path
) -> None:
    # AC2: each character's Idle is its own action.  Re-imported, the root's lift differs per rig.
    records = two_characters.export_clips("StreetThug", ["Idle"], tmp_path)
    records += two_characters.export_clips("Cop", ["Idle"], tmp_path)

    assert [record["file"] for record in records] == ["A_StreetThug_Idle.glb", "A_Cop_Idle.glb"]
    lifts: dict[str, float] = {}
    for record in records:
        bpy.ops.wm.read_homefile(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(tmp_path / record["file"]), disable_bone_shape=True)
        (action,) = bpy.data.actions
        lifts[record["file"]] = _root_lift(action)
    assert lifts["A_Cop_Idle.glb"] == pytest.approx(3 * lifts["A_StreetThug_Idle.glb"], rel=1e-3)
    assert lifts["A_StreetThug_Idle.glb"] > 0.0


def test_ac3_an_unsuffixed_clip_hash_is_the_hash_of_its_action_name(
    scene_with_clips: Any,
) -> None:
    # AC3: an unsuffixed action hashes as its clip name equal to its action name, as before.
    rig = bpy.data.objects[_ARMATURE]
    action = bpy.data.actions["Idle"]
    provenance = scene_with_clips.provenance_of(rig).get("Idle")
    expected = scene_with_clips.clip_hash(rig, action.name, action, provenance)

    hashes = {clip["name"]: clip["hash"] for clip in scene_with_clips.probe(_COLLECTION)["clips"]}

    assert hashes["Idle"] == expected


def test_ac4_a_suffix_naming_another_rig_stops_the_export_before_any_write(
    one_file: Any, tmp_path: Path
) -> None:
    # AC4: StreetThug holds Idle@SK_Cop.  The probe reports it and the export writes nothing.
    thug = _rig("StreetThug")
    _hold(thug, _clip(thug, "Idle@SK_StreetThug", (1, 10), 0.1))
    _hold(thug, _clip(thug, "Idle@SK_Cop", (1, 10), 0.3))

    report = one_file.probe("StreetThug")
    assert report["rig_mismatch"] == ["Idle@SK_Cop"]
    assert [clip["name"] for clip in report["clips"]] == ["Idle"]

    out = tmp_path / "Animations"
    with pytest.raises(one_file.AnimError) as info:
        one_file.export_clips("StreetThug", ["Idle"], out)
    assert info.value.code == "finalize.clip_rig_mismatch"
    assert "Idle@SK_Cop" in info.value.message
    assert info.value.remediation
    assert not out.exists()


def test_ac5_two_actions_giving_one_clip_name_stop_the_export_before_any_write(
    one_file: Any, tmp_path: Path
) -> None:
    # AC5: StreetThug holds Idle and Idle@SK_StreetThug.  Both are clip Idle, so nothing exports.
    thug = _rig("StreetThug")
    _hold(thug, _clip(thug, "Idle", (1, 10), 0.1))
    _hold(thug, _clip(thug, "Idle@SK_StreetThug", (1, 10), 0.2))

    report = one_file.probe("StreetThug")
    assert report["duplicates"] == [{"name": "Idle", "actions": ["Idle", "Idle@SK_StreetThug"]}]
    assert report["clips"] == []

    out = tmp_path / "Animations"
    with pytest.raises(one_file.AnimError) as info:
        one_file.export_clips("StreetThug", ["Idle"], out)
    assert info.value.code == "finalize.clip_name_duplicate"
    assert "Idle" in info.value.message
    assert "Idle@SK_StreetThug" in info.value.message
    assert info.value.remediation
    assert not out.exists()


def test_ac6_the_bare_clip_name_is_still_validated(one_file: Any, tmp_path: Path) -> None:
    # AC6: 1Idle@SK_StreetThug probes as 1Idle with valid_name false, and the export refuses it.
    thug = _rig("StreetThug")
    _hold(thug, _clip(thug, "1Idle@SK_StreetThug", (1, 10), 0.1))

    report = one_file.probe("StreetThug")
    assert [(clip["name"], clip["valid_name"]) for clip in report["clips"]] == [("1Idle", False)]

    out = tmp_path / "Animations"
    with pytest.raises(one_file.AnimError) as info:
        one_file.export_clips("StreetThug", ["1Idle"], out)
    assert info.value.code == "finalize.clip_name_invalid"
    assert "1Idle" in info.value.message
    assert not out.exists()
