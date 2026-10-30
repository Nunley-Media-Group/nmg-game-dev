"""Animation import: AC2 (library retargeting, export, provenance) and AC3 (honest statuses)."""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .rig_fixtures import MANNY_BONE_NAMES, build_hero, build_library, reset_scene  # noqa: E402

_REIMPORT_CHECK = """\
import json
import math
import sys

import bpy

fbx_path, bvh_path = sys.argv[sys.argv.index("--") + 1 :][:2]
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

bpy.ops.import_scene.fbx(filepath=fbx_path)
rig = next(obj for obj in bpy.data.objects if obj.type == "ARMATURE")
bones = list(rig.data.bones)
rig_objects = sorted((obj.name, obj.type) for obj in bpy.data.objects)

bpy.ops.import_anim.bvh(filepath=bvh_path)
source = next(obj for obj in bpy.data.objects if obj.type == "ARMATURE" and obj is not rig)
source_bone = next(
    bone.name for bone in source.data.bones if bone.name.rsplit(":", 1)[-1] == "LeftUpLeg"
)


def rest_relative(armature, bone_name, frame):
    bpy.context.scene.frame_set(frame)
    evaluated = armature.evaluated_get(bpy.context.evaluated_depsgraph_get())
    pose = evaluated.pose.bones[bone_name].matrix
    rest = armature.data.bones[bone_name].matrix_local
    return pose.to_3x3() @ rest.to_3x3().inverted(), pose.to_translation(), rest.to_translation()


walk = next(action for action in bpy.data.actions if action.name.rsplit("|", 1)[-1] == "Walk")
rig.animation_data_create().action = walk
samples = []
for frame in (10, 25):
    target_delta, target_pos, target_rest = rest_relative(rig, "thigh_l", frame)
    source_delta, _, _ = rest_relative(source, source_bone, frame)
    difference = target_delta.to_quaternion().rotation_difference(source_delta.to_quaternion())
    samples.append({
        "frame": frame,
        "angle_deg": math.degrees(difference.angle),
        "head_shift": (target_pos - target_rest).length,
    })

result = {
    "bones": [bone.name for bone in bones],
    "root_bones": [bone.name for bone in bones if bone.parent is None],
    "armatures": sum(1 for _, kind in rig_objects if kind == "ARMATURE"),
    "object_types": sorted({kind for _, kind in rig_objects}),
    "actions": {
        action.name.rsplit("|", 1)[-1]: list(action.frame_range) for action in bpy.data.actions
    },
    "samples": samples,
}
print("NMG_RESULT:" + json.dumps(result, sort_keys=True))
"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def rigged_library(enabled_addon: str, tmp_path: Path) -> tuple[Any, Path]:
    reset_scene()
    rig_core = importlib.import_module(f"{enabled_addon}.rig_core")
    assert rig_core.rig_humanoid("Hero", "humanoid", build_hero())["status"] == "ok"
    return rig_core, build_library(tmp_path / "library")


def test_ac2_library_clips_bake_and_export_with_provenance(
    rigged_library: tuple[Any, Path], tmp_path: Path
) -> None:
    rig_core, library = rigged_library

    baked = rig_core.import_animations("Hero", str(library))

    assert baked["status"] == "ok", baked
    clips = {clip["name"]: clip for clip in baked["clips"]}
    assert set(clips) == {"Idle", "Walk"}
    assert (clips["Idle"]["frame_start"], clips["Idle"]["frame_end"]) == (1, 30)
    assert clips["Idle"]["frame_count"] == 30
    assert (clips["Walk"]["frame_start"], clips["Walk"]["frame_end"]) == (1, 40)
    assert clips["Walk"]["frame_count"] == 40
    assert clips["Walk"]["fps"] == bpy.context.scene.render.fps
    assert clips["Walk"]["source"] == {
        "library": "fixture-lib",
        "file": "walk.bvh",
        "sha256": _sha256(library / "walk.bvh"),
        "skeleton": "mixamo",
    }
    assert bpy.data.actions["Idle"].use_fake_user
    assert bpy.data.actions["Walk"].use_fake_user
    assert [obj.name for obj in bpy.data.objects if obj.type == "ARMATURE"] == ["SK_Hero"]

    out_dir = tmp_path / "out"
    exported = rig_core.export_rigged("Hero", str(out_dir))

    assert exported["status"] == "ok", exported
    assert (out_dir / "SM_Hero.fbx").is_file()
    sidecar = json.loads((out_dir / "nmg-animations.json").read_text(encoding="utf-8"))
    assert sidecar["asset"] == "Hero"
    assert sidecar["armature"] == "SK_Hero"
    assert sidecar["skeleton"] == "ue5_manny"
    assert sidecar["fbx"] == "SM_Hero.fbx"
    assert sidecar["bones"] == list(MANNY_BONE_NAMES)
    assert [clip["name"] for clip in sidecar["clips"]] == ["Idle", "Walk"]
    idle_source = sidecar["clips"][0]["source"]
    assert idle_source == {
        "library": "fixture-lib",
        "file": "idle.fbx",
        "sha256": _sha256(library / "idle.fbx"),
        "skeleton": "mixamo",
    }
    assert bpy.data.objects.get("SK_Hero") is not None
    assert bpy.data.objects.get("Armature") is None


def test_ac2_fresh_blender_reimport_has_mannequin_bones_and_matching_thigh(
    rigged_library: tuple[Any, Path], tmp_path: Path
) -> None:
    rig_core, library = rigged_library
    assert rig_core.import_animations("Hero", str(library))["status"] == "ok"
    out_dir = tmp_path / "out"
    assert rig_core.export_rigged("Hero", str(out_dir))["status"] == "ok"
    script = tmp_path / "reimport_check.py"
    script.write_text(_REIMPORT_CHECK, encoding="utf-8")

    completed = subprocess.run(
        [
            bpy.app.binary_path,
            "--background",
            "--factory-startup",
            "--python",
            str(script),
            "--",
            str(out_dir / "SM_Hero.fbx"),
            str(library / "walk.bvh"),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )

    # Blender exits 0 even when a --python script raises, so look for the result marker.
    marker = [line for line in completed.stdout.splitlines() if line.startswith("NMG_RESULT:")]
    assert marker, f"re-import check printed no result:\n{completed.stderr[-2000:]}"
    result = json.loads(marker[0].removeprefix("NMG_RESULT:"))
    assert sorted(result["bones"]) == sorted(MANNY_BONE_NAMES)
    assert len(result["bones"]) == 26
    assert result["root_bones"] == ["root"]
    assert result["armatures"] == 1
    assert "EMPTY" not in result["object_types"]
    assert result["actions"]["Idle"] == [1.0, 30.0]
    assert result["actions"]["Walk"] == [1.0, 40.0]
    for sample in result["samples"]:
        assert sample["angle_deg"] < 1.0, sample
        assert sample["head_shift"] < 1e-3, sample


def test_ac3_text_motion_request_is_a_spike(rigged_library: tuple[Any, Path]) -> None:
    rig_core, library = rigged_library

    result = rig_core.import_animations("Hero", str(library), motion_prompt="a slow limp")

    assert result["status"] == "follow-up spike required"
    assert result["code"] == "anim.text_motion_unsupported"
    assert result["message"] and result["remediation"]


def test_ac3_unknown_clip_names_the_clip(rigged_library: tuple[Any, Path]) -> None:
    rig_core, library = rigged_library
    actions_before = {action.name for action in bpy.data.actions}

    result = rig_core.import_animations("Hero", str(library), clips=["Run"])

    assert result["status"] == "fallback required"
    assert result["code"] == "anim.clip_not_found"
    assert "Run" in result["message"]
    assert "Mixamo" in result["remediation"]
    assert {action.name for action in bpy.data.actions} == actions_before


def test_ac3_missing_rig_reports_rig_missing(rigged_library: tuple[Any, Path]) -> None:
    rig_core, library = rigged_library

    result = rig_core.import_animations("Ghost", str(library))

    assert result["status"] == "fallback required"
    assert result["code"] == "anim.rig_missing"


def test_ac3_invalid_library_names_the_problem(
    rigged_library: tuple[Any, Path], tmp_path: Path
) -> None:
    rig_core, _ = rigged_library
    library = tmp_path / "bad"
    library.mkdir()
    manifest = {
        "name": "bad",
        "skeleton": "mixamo",
        "clips": [{"name": "9Idle", "file": "x.fbx"}],
    }
    (library / "library.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = rig_core.import_animations("Hero", str(library))

    assert result["status"] == "fallback required"
    assert result["code"] == "anim.library_invalid"
    assert "9Idle" in result["message"]


def test_ac3_custom_bone_map_must_reach_required_targets(
    rigged_library: tuple[Any, Path], tmp_path: Path
) -> None:
    rig_core, library = rigged_library
    manifest = tmp_path / "custom"
    manifest.mkdir()
    (manifest / "library.json").write_text(
        json.dumps(
            {
                "name": "custom",
                "skeleton": "custom",
                "bone_map": {"Hips": "pelvis", "Spine": "spine_01"},
                "clips": [{"name": "Idle", "file": "idle.fbx"}],
            }
        ),
        encoding="utf-8",
    )
    (manifest / "idle.fbx").write_bytes((library / "idle.fbx").read_bytes())

    result = rig_core.import_animations("Hero", str(manifest))

    assert result["status"] == "fallback required"
    assert result["code"] == "anim.bone_map_incomplete"
    assert "thigh_l" in result["message"]
