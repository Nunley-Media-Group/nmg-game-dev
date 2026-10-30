"""Humanoid rigging: AC1 (local build, Manny bones, weights, rerun) and AC3 (honest statuses)."""

from __future__ import annotations

import copy
import importlib
import socket
from collections.abc import Callable
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .rig_fixtures import build_hero, reset_scene  # noqa: E402

EXPECTED_PARENTS: dict[str, str | None] = {
    "root": None,
    "pelvis": "root",
    "spine_01": "pelvis",
    "spine_02": "spine_01",
    "spine_03": "spine_02",
    "spine_04": "spine_03",
    "spine_05": "spine_04",
    "neck_01": "spine_05",
    "neck_02": "neck_01",
    "head": "neck_02",
    "clavicle_l": "spine_05",
    "upperarm_l": "clavicle_l",
    "lowerarm_l": "upperarm_l",
    "hand_l": "lowerarm_l",
    "clavicle_r": "spine_05",
    "upperarm_r": "clavicle_r",
    "lowerarm_r": "upperarm_r",
    "hand_r": "lowerarm_r",
    "thigh_l": "pelvis",
    "calf_l": "thigh_l",
    "foot_l": "calf_l",
    "ball_l": "foot_l",
    "thigh_r": "pelvis",
    "calf_r": "thigh_r",
    "foot_r": "calf_r",
    "ball_r": "foot_r",
}


@pytest.fixture()
def network_attempts(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Record every socket connect attempt and refuse it."""
    attempts: list[Any] = []

    def _blocked(self: socket.socket, address: Any) -> None:
        attempts.append(address)
        raise OSError("network connections are blocked for this test")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    return attempts


@pytest.fixture()
def rig_core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.rig_core")


@pytest.fixture()
def hero() -> dict[str, list[float]]:
    reset_scene()
    return build_hero()


def _scene_signature() -> tuple[list[str], int]:
    names = sorted(obj.name for obj in bpy.data.objects)
    vertices = sum(len(mesh.vertices) for mesh in bpy.data.meshes)
    return names, vertices


def test_ac1_rig_builds_manny_skeleton_without_network(
    rig_core: Any, hero: dict[str, list[float]], network_attempts: list[Any]
) -> None:
    addons_before = set(bpy.context.preferences.addons.keys())

    result = rig_core.rig_humanoid("Hero", "humanoid", hero)

    assert result["status"] == "ok", result
    armature = bpy.data.objects["SK_Hero"]
    assert armature.type == "ARMATURE"
    assert [coll.name for coll in armature.users_collection] == ["Hero"]
    assert {bone.name for bone in armature.data.bones} == set(EXPECTED_PARENTS)
    for bone in armature.data.bones:
        parent = bone.parent.name if bone.parent is not None else None
        assert parent == EXPECTED_PARENTS[bone.name], bone.name

    mesh = bpy.data.objects["SM_Hero"]
    assert mesh.parent is armature
    armature_modifiers = [mod for mod in mesh.modifiers if mod.type == "ARMATURE"]
    assert len(armature_modifiers) == 1
    assert armature_modifiers[0].object is armature

    bone_names = set(EXPECTED_PARENTS)
    unweighted = 0
    for vertex in mesh.data.vertices:
        groups = {mesh.vertex_groups[entry.group].name: entry.weight for entry in vertex.groups}
        if not any(groups.get(name, 0.0) > 0.0 for name in bone_names):
            unweighted += 1
    assert unweighted == 0
    assert network_attempts == []
    assert set(bpy.context.preferences.addons.keys()) == addons_before


def test_ac1_rerun_replaces_rig(
    rig_core: Any, hero: dict[str, list[float]], network_attempts: list[Any]
) -> None:
    assert rig_core.rig_humanoid("Hero", "humanoid", hero)["status"] == "ok"
    second = rig_core.rig_humanoid("Hero", "humanoid", hero)

    assert second["status"] == "ok", second
    armatures = [obj.name for obj in bpy.data.objects if obj.type == "ARMATURE"]
    assert armatures == ["SK_Hero"]
    assert len(bpy.data.armatures) == 1
    assert {bone.name for bone in bpy.data.objects["SK_Hero"].data.bones} == set(EXPECTED_PARENTS)
    assert bpy.data.objects["SM_Hero"].parent is bpy.data.objects["SK_Hero"]
    assert network_attempts == []


def _asymmetric(landmarks: dict[str, list[float]]) -> dict[str, list[float]]:
    changed = copy.deepcopy(landmarks)
    changed["shoulder_r"] = [-0.1, 0.0, 1.45]
    return changed


def _arms_raised(landmarks: dict[str, list[float]]) -> dict[str, list[float]]:
    changed = copy.deepcopy(landmarks)
    changed["wrist_l"] = [0.8, 0.0, 1.75]
    changed["wrist_r"] = [-0.8, 0.0, 1.75]
    return changed


def _missing_key(landmarks: dict[str, list[float]]) -> dict[str, list[float]]:
    changed = copy.deepcopy(landmarks)
    del changed["toe_r"]
    return changed


@pytest.mark.parametrize(
    ("body_type", "make_landmarks", "status", "code"),
    [
        (
            "quadruped",
            lambda landmarks: landmarks,
            "follow-up spike required",
            "rig.unsupported_body",
        ),
        ("humanoid", _asymmetric, "fallback required", "rig.unclear_humanoid"),
        ("humanoid", _arms_raised, "fallback required", "rig.pose_not_neutral"),
        ("humanoid", _missing_key, "fallback required", "rig.landmarks_missing"),
    ],
    ids=["quadruped", "asymmetric", "arms-raised", "missing-key"],
)
def test_ac3_unsupported_rigs_report_status_and_leave_scene_unchanged(
    rig_core: Any,
    hero: dict[str, list[float]],
    network_attempts: list[Any],
    body_type: str,
    make_landmarks: Callable[[dict[str, list[float]]], dict[str, list[float]]],
    status: str,
    code: str,
) -> None:
    before = _scene_signature()

    result = rig_core.rig_humanoid("Hero", body_type, make_landmarks(hero))

    assert result["status"] == status, result
    assert result["code"] == code
    assert result["message"]
    assert result["remediation"]
    assert _scene_signature() == before
    assert network_attempts == []
    if status == "fallback required":
        assert "Mixamo" in result["remediation"]
        assert result["remediation"].rstrip().endswith("Nothing in nmg-game-dev contacts Mixamo.")


def test_ac3_missing_root_mesh_reports_asset_not_found(
    rig_core: Any, hero: dict[str, list[float]], network_attempts: list[Any]
) -> None:
    result = rig_core.rig_humanoid("Missing", "humanoid", hero)

    assert result["status"] == "fallback required"
    assert result["code"] == "rig.asset_not_found"
    assert network_attempts == []
