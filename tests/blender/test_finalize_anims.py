"""Per-clip animation export under Blender headless: SCN001-SCN003 and SCN011 of #138.

A rig ``SK_Hero`` in collection ``Hero`` holds clips in three ways: a provenance clip, an action
on the rig's NLA track, and an unrelated action that nothing holds.  Each test exports through
``finalize_core.anims`` and, where it matters, re-imports the written FBX into a fresh scene.

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


def _rig() -> Any:
    """Build SK_Hero in collection Hero with a root and a spine bone."""
    collection = bpy.data.collections.new(_COLLECTION)
    bpy.context.scene.collection.children.link(collection)
    data = bpy.data.armatures.new(_ARMATURE)
    rig = bpy.data.objects.new(_ARMATURE, data)
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


def test_one_armature_only_fbx_per_clip_and_each_reimports_as_one_clip(
    scene_with_clips: Any, tmp_path: Path
) -> None:
    # SCN001 and AC1: each clip is its own FBX.  Re-imported, it has the armature named Armature,
    # no mesh, and exactly one action.
    out = tmp_path / "Animations"
    records = scene_with_clips.export_clips(_COLLECTION, ["Idle", "Wave"], out)

    assert [record["file"] for record in records] == ["A_Hero_Idle.fbx", "A_Hero_Wave.fbx"]
    for record in records:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.fbx(filepath=str(out / record["file"]))
        armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
        meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
        assert [obj.name for obj in armatures] == ["Armature"]
        assert meshes == []
        assert len(bpy.data.actions) == 1


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
    assert (folder / "A_Hero_Idle.fbx").is_file()
    assert not (folder / "A_Hero_Wave.fbx").exists()
