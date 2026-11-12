"""estimate_landmarks: SCN001-SCN009 (AC1-AC9), plus the 100,000-vertex timing check.

Every test runs headless in background Blender through scripts/run-blender-tests.sh. Each builds
its own fixture in a clean scene, so the results do not depend on test order.
"""

from __future__ import annotations

import importlib
import math
import time
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from mathutils import Euler, Matrix, Vector  # noqa: E402

from .landmark_fixtures import build_a_pose  # noqa: E402
from .rig_fixtures import HERO_LANDMARKS, build_hero, reset_scene  # noqa: E402

Landmarks = dict[str, list[float]]
_MIRROR_BASES = ("shoulder", "elbow", "wrist", "hand_tip", "hip", "knee", "ankle", "toe")
_TOLERANCE = 0.05


@pytest.fixture()
def rig_core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.rig_core")


@pytest.fixture()
def landmark_keys(enabled_addon: str) -> tuple[str, ...]:
    return importlib.import_module(f"{enabled_addon}.rig_core.skeleton").LANDMARK_KEYS


@pytest.fixture()
def clean_scene() -> None:
    reset_scene()


def _height(known: Landmarks) -> float:
    return known["head_top"][2] - min(known["ankle_l"][2], known["ankle_r"][2])


def _mirror_gap(landmarks: Landmarks, base: str) -> float:
    left = landmarks[f"{base}_l"]
    right = landmarks[f"{base}_r"]
    return math.dist(left, (-right[0], right[1], right[2]))


def _assert_a_pose(result: dict[str, Any], known: Landmarks, keys: tuple[str, ...]) -> None:
    """AC1: ok, high, no warnings, 19 keys within 5% of the height, and the sides are right."""
    assert result["status"] == "ok", result
    assert result["confidence"] == "high", result
    assert result["warnings"] == [], result
    height = _height(known)
    assert set(result["landmarks"]) == set(keys)
    for key in keys:
        point = result["landmarks"][key]
        assert len(point) == 3 and all(isinstance(c, float) for c in point), key
        assert math.dist(point, known[key]) <= _TOLERANCE * height, (key, point, known[key])
        if key.endswith("_l"):
            assert point[0] > 0.0, key
        if key.endswith("_r"):
            assert point[0] < 0.0, key


def test_scn001_a_pose_is_proposed_with_high_confidence(
    rig_core: Any, landmark_keys: tuple[str, ...], clean_scene: None
) -> None:
    known = build_a_pose("Hero")

    result = rig_core.estimate_landmarks("Hero")

    _assert_a_pose(result, known, landmark_keys)


def test_scn002_a_high_confidence_proposal_rigs_without_edits(
    rig_core: Any, clean_scene: None
) -> None:
    build_a_pose("Hero")
    proposal = rig_core.estimate_landmarks("Hero")
    assert proposal["confidence"] == "high", proposal

    result = rig_core.rig_humanoid("Hero", "humanoid", proposal["landmarks"])

    assert result["status"] == "ok", result


@pytest.mark.parametrize("accessory", ["hat_brim", "earrings", "glasses"])
def test_scn003_stylized_proportions_and_accessories_do_not_mislead(
    rig_core: Any, landmark_keys: tuple[str, ...], clean_scene: None, accessory: str
) -> None:
    known = build_a_pose("Hero", stylized=True, accessory=accessory)

    result = rig_core.estimate_landmarks("Hero")

    assert result["status"] == "ok", result
    height = _height(known)
    for side in ("l", "r"):
        shoulder = result["landmarks"][f"shoulder_{side}"]
        assert math.dist(shoulder, known[f"shoulder_{side}"]) <= _TOLERANCE * height, side
    _assert_a_pose(result, known, landmark_keys)


@pytest.mark.parametrize("asymmetric", ["arm", "leg"])
def test_scn004_an_asymmetric_stance_is_low_confidence_and_measured_per_side(
    rig_core: Any, landmark_keys: tuple[str, ...], clean_scene: None, asymmetric: str
) -> None:
    known = build_a_pose("Hero", asymmetric=asymmetric)

    result = rig_core.estimate_landmarks("Hero")

    assert result["status"] == "ok", result
    assert result["confidence"] == "low", result
    height = _height(known)
    asymmetric_bases = [b for b in _MIRROR_BASES if _mirror_gap(known, b) > _TOLERANCE * height]
    assert asymmetric_bases, "the fixture must offset one side by more than 5% of the height"
    for base in asymmetric_bases:
        assert any(f"{base}_l/{base}_r" in text for text in result["warnings"]), base
    assert len(result["warnings"]) == len(asymmetric_bases), result["warnings"]
    for key in landmark_keys:
        assert math.dist(result["landmarks"][key], known[key]) <= _TOLERANCE * height, key
    for base in asymmetric_bases:
        measured = result["landmarks"][f"{base}_r"]
        averaged = [
            (known[f"{base}_r"][0] - known[f"{base}_l"][0]) / 2.0,
            (known[f"{base}_r"][1] + known[f"{base}_l"][1]) / 2.0,
            known[f"{base}_r"][2],
        ]
        assert math.dist(measured, known[f"{base}_r"]) < math.dist(measured, averaged), base


@pytest.mark.parametrize(
    ("make_figure", "expected_code"),
    [
        (lambda: build_hero(voxel_size=0.005), "rig.arms_not_found"),
        (lambda: build_a_pose("Hero", fused_arms=True), "rig.arms_not_found"),
        (lambda: build_a_pose("Hero", no_crotch=True), "rig.crotch_not_found"),
    ],
    ids=["t-pose", "fused-arms", "no-crotch"],
)
def test_scn005_no_a_pose_arms_or_no_crotch_is_a_failure_not_a_guess(
    rig_core: Any, clean_scene: None, make_figure: Any, expected_code: str
) -> None:
    make_figure()

    result = rig_core.estimate_landmarks("Hero")

    assert result["status"] == "fallback required", result
    assert result["code"] == expected_code, result
    assert result["message"], result
    assert result["remediation"], result
    assert "landmarks" not in result


def test_scn006_a_missing_mesh_is_reported_with_the_expected_name(
    rig_core: Any, clean_scene: None
) -> None:
    missing = rig_core.estimate_landmarks("Ghost")
    assert missing["status"] == "fallback required", missing
    assert missing["code"] == "rig.asset_not_found", missing
    assert "SM_Ghost" in missing["message"], missing
    assert "landmarks" not in missing

    hollow = bpy.data.collections.new("Hollow")
    bpy.context.scene.collection.children.link(hollow)
    cube = bpy.data.objects.new("Cube", bpy.data.meshes.new("Cube"))
    hollow.objects.link(cube)

    result = rig_core.estimate_landmarks("Hollow")

    assert result["code"] == "rig.asset_not_found", result
    assert "SM_Hollow" in result["message"], result


def _scene_state() -> dict[str, Any]:
    """Everything AC7 names: objects, mesh data, transforms, selection, active object, and mode."""
    objects: dict[str, Any] = {}
    for obj in bpy.data.objects:
        entry: dict[str, Any] = {
            "type": obj.type,
            "data": obj.data.name if obj.data is not None else None,
            "matrix_basis": tuple(tuple(row) for row in obj.matrix_basis),
            "matrix_world": tuple(tuple(row) for row in obj.matrix_world),
            "selected": obj.select_get(),
            "mode": obj.mode,
            "collections": sorted(c.name for c in obj.users_collection),
            "parent": obj.parent.name if obj.parent is not None else None,
            "modifiers": [modifier.name for modifier in obj.modifiers],
        }
        if obj.type == "MESH":
            entry["vertices"] = tuple(tuple(v.co) for v in obj.data.vertices)
        objects[obj.name] = entry
    active = bpy.context.view_layer.objects.active
    return {
        "objects": objects,
        "meshes": sorted(mesh.name for mesh in bpy.data.meshes),
        "active": active.name if active is not None else None,
    }


@pytest.mark.parametrize(
    "make_figure",
    [
        lambda: build_a_pose("Hero"),
        lambda: build_hero(),
        lambda: build_a_pose("Hero", no_crotch=True),
        lambda: None,
    ],
    ids=["a-pose", "t-pose", "no-crotch", "missing-collection"],
)
def test_scn007_estimating_changes_nothing(
    rig_core: Any, clean_scene: None, make_figure: Any
) -> None:
    make_figure()
    before = _scene_state()

    result = rig_core.estimate_landmarks("Hero")

    assert result["status"] in ("ok", "fallback required"), result
    assert _scene_state() == before


def test_scn008_rig_humanoid_uses_the_meshs_current_position(
    rig_core: Any, landmark_keys: tuple[str, ...], clean_scene: None
) -> None:
    known = build_a_pose("Hero")
    mesh = bpy.data.objects["SM_Hero"]
    mesh.location = (0.0, 0.25, 0.1)
    mesh.rotation_euler = (math.radians(6.0), 0.0, 0.0)
    mesh.scale = (1.05, 1.05, 1.05)
    # No view-layer update here: the script moves the mesh and calls the tooling straight away.
    transform = (
        Matrix.Translation(mesh.location)
        @ Euler(mesh.rotation_euler).to_matrix().to_4x4()
        @ Matrix.Diagonal((1.05, 1.05, 1.05, 1.0))
    )
    moved: Landmarks = {
        key: [float(c) for c in transform @ Vector(point)] for key, point in known.items()
    }

    result = rig_core.rig_humanoid("Hero", "humanoid", moved)
    assert result["status"] == "ok", result

    proposal = rig_core.estimate_landmarks("Hero")
    assert proposal["status"] == "ok", proposal
    height = _height(moved)
    for key in landmark_keys:
        assert math.dist(proposal["landmarks"][key], moved[key]) <= _TOLERANCE * height, key


def test_scn009_rig_humanoid_messages_name_the_real_mesh(
    rig_core: Any, clean_scene: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    hollow = bpy.data.collections.new("Hero")
    bpy.context.scene.collection.children.link(hollow)
    missing = rig_core.rig_humanoid("Hero", "humanoid", HERO_LANDMARKS)
    bpy.data.collections.remove(hollow)

    build_hero()
    outside = {key: list(value) for key, value in HERO_LANDMARKS.items()}
    outside["pelvis"] = [5.0, 0.0, 1.0]
    outside_result = rig_core.rig_humanoid("Hero", "humanoid", outside)

    rig_module = importlib.import_module(f"{rig_core.__name__}.rig")
    monkeypatch.setattr(rig_module, "_unweighted_vertices", lambda armature, roots: 7)
    weights = rig_core.rig_humanoid("Hero", "humanoid", HERO_LANDMARKS)

    expected = {
        "rig.asset_not_found": missing,
        "rig.landmarks_outside_mesh": outside_result,
        "rig.weights_failed": weights,
    }
    for code, result in expected.items():
        assert result["code"] == code, result
        for text in (result["message"], result["remediation"]):
            assert "SM_Hero" in text and "Hero" in text, (code, text)
            assert "SM_<Name>" not in text and "<Name>" not in text, (code, text)


def test_propose_on_a_mesh_of_100000_vertices_finishes_within_60_seconds(
    rig_core: Any, clean_scene: None
) -> None:
    # The fixture's remesh already gives at least 100,000 vertices. Adding a subdivision level on
    # top would only make the run longer without testing anything new.
    build_a_pose("Hero")
    mesh = bpy.data.objects["SM_Hero"]
    bpy.context.view_layer.update()
    evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    dense = evaluated.to_mesh()
    try:
        vertex_count = len(dense.vertices)
    finally:
        evaluated.to_mesh_clear()
    assert vertex_count >= 100_000, vertex_count

    started = time.perf_counter()
    result = rig_core.estimate_landmarks("Hero")
    elapsed = time.perf_counter() - started

    assert result["status"] == "ok", result
    assert elapsed < 60.0, elapsed
