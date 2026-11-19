"""Rest-pose evaluation of rigged assets under Blender headless: SCN001-SCN005 of #236.

Each test here is the proof for one scenario, on real Blender data. A rigged hero is posed with
no action assigned (rig_fixtures.pose_hero). tests/bdd/test_rest_pose_finalize_bdd.py binds the
scenarios with pytest-bdd and runs these node ids through scripts/run-blender-tests.sh, the
arrangement tests/bdd/test_shared_clip_names_bdd.py uses.

SCN003 covers the export clause only. Its reduce_asset clause is not proven here, because reduce
refuses any collection with an armature (reduce.rigged, #139 AC13), so the posed rig never reaches
the reduce copy. test_fr3_make_copy_evaluates_the_rest_pose covers the copy step on its own.

Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
import json
import struct
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from mathutils import Matrix  # noqa: E402

from .rig_fixtures import (  # noqa: E402
    add_baked_hero_material,
    build_hero,
    pose_hero,
    reset_scene,
)

_COLLECTION = "Hero"
_CATEGORY = "Characters"
_RIG = "SK_Hero"
#: Metres of pose: moves the skin's bounds about 10 mm, well over the 1 mm pivot tolerance.
_POSE = 0.02
_TOLERANCE = 1e-3
_LIFT_PER_FRAME = 0.1


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core")


@pytest.fixture()
def variants(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.variants_core")


@pytest.fixture()
def rig_core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.rig_core")


@pytest.fixture()
def reduce_core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.reduce_core")


@pytest.fixture()
def cleanup(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.variants_core.cleanup")


@pytest.fixture()
def hero(rig_core: Any, cleanup: Any) -> Any:
    """Collection Hero: SM_Hero skinned to SK_Hero at rest, origin at the bottom center."""
    _build_hero(rig_core, cleanup)
    yield rig_core
    reset_scene()


def _build_hero(rig_core: Any, cleanup: Any) -> None:
    """Build the rigged hero at rest, seated the way finalize's variants step seats it (#244).

    rig_humanoid leaves the bottom center a few millimetres off the origin. The scenarios assume an
    asset whose rest pose has its origin at the bottom center, so the Desktop is re-seated.
    """
    reset_scene()
    assert rig_core.rig_humanoid(_COLLECTION, "humanoid", build_hero())["status"] == "ok"
    add_baked_hero_material()
    cleanup.reseat_desktop(_COLLECTION)


def _mesh() -> Any:
    return bpy.data.objects["SM_Hero"]


def _world_bounds(obj: Any) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """The world-space low and high corners of obj's vertices, modifiers applied, at the pose."""
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), depsgraph=depsgraph)
    try:
        points = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
    finally:
        bpy.data.meshes.remove(mesh)
    lows = tuple(min(point[axis] for point in points) for axis in range(3))
    highs = tuple(max(point[axis] for point in points) for axis in range(3))
    return lows, highs


def _largest_gap(first: tuple[tuple[float, ...], ...], second: tuple[Any, ...]) -> float:
    """The largest per-coordinate difference between two boxes, or between two sets of points."""
    gaps = [
        abs(a - b)
        for part_a, part_b in zip(first, second, strict=True)
        for a, b in zip(part_a, part_b, strict=True)
    ]
    return max(gaps)


def _pose_state() -> dict[str, Any]:
    """Everything the scene-unchanged scenario compares: pose_position, the action, every bone."""
    rig = bpy.data.objects[_RIG]
    action = rig.animation_data.action if rig.animation_data is not None else None
    return {
        "pose_position": rig.data.pose_position,
        "action": None if action is None else action.name,
        "bones": {
            bone.name: (
                bone.rotation_mode,
                tuple(bone.location),
                tuple(bone.rotation_quaternion),
                tuple(bone.rotation_euler),
                tuple(bone.rotation_axis_angle),
                tuple(bone.scale),
            )
            for bone in rig.pose.bones
        },
    }


def _every_bone_at_identity() -> bool:
    rig = bpy.data.objects[_RIG]
    return all(
        tuple(bone.location) == (0.0, 0.0, 0.0)
        and tuple(bone.rotation_quaternion) == (1.0, 0.0, 0.0, 0.0)
        and tuple(bone.scale) == (1.0, 1.0, 1.0)
        for bone in rig.pose.bones
    )


def _rest_heads_in_engine_axes() -> dict[str, tuple[float, float, float]]:
    """Each bone's rest head in glTF axes (x, z, -y), the axes the GLB stores them in."""
    rig = bpy.data.objects[_RIG]
    heads: dict[str, tuple[float, float, float]] = {}
    for bone in rig.data.bones:
        head = rig.matrix_world @ bone.head_local
        heads[bone.name] = (head.x, head.z, -head.y)
    return heads


def _glb_joint_heads(path: Path) -> dict[str, tuple[float, float, float]]:
    """Each joint's rest head in glTF axes, read from its skin's inverse bind matrix."""
    data = path.read_bytes()
    (json_length,) = struct.unpack_from("<I", data, 12)
    document = json.loads(data[20 : 20 + json_length])
    bin_start = 20 + json_length + 8
    skin = document["skins"][0]
    accessor = document["accessors"][skin["inverseBindMatrices"]]
    view = document["bufferViews"][accessor["bufferView"]]
    start = bin_start + view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    values = struct.unpack_from(f"<{16 * accessor['count']}f", data, start)
    heads: dict[str, tuple[float, float, float]] = {}
    for index, joint in enumerate(skin["joints"]):
        column_major = values[16 * index : 16 * index + 16]
        rows = [column_major[row::4] for row in range(4)]
        inverse = Matrix(rows).inverted()
        heads[document["nodes"][joint]["name"]] = tuple(inverse.translation)
    return heads


def _import_glb(path: Path) -> None:
    reset_scene()
    bpy.ops.import_scene.gltf(filepath=str(path), disable_bone_shape=True)


def _imported_mesh_bounds(path: Path) -> tuple[tuple[float, ...], tuple[float, ...]]:
    _import_glb(path)
    (mesh,) = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    return _world_bounds(mesh)


def _pivot_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [finding for finding in report["findings"] if finding["rule"] == "pivot.bottom_center"]


def _hold_provenance_clip(rig: Any, name: str, frames: tuple[int, int], lift: float) -> None:
    """Key the root bone as a fake-user action named name, listed as provenance and not assigned.

    No NLA track or assignment is left behind, so the rig's pose is only what the export writes.
    """
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = action
    bone = rig.pose.bones["root"]
    for frame in frames:
        bone.location = (0.0, 0.0, lift * frame)
        bone.keyframe_insert(data_path="location", frame=frame)
    rig.animation_data.action = None
    entry = {
        "name": name,
        "frame_start": frames[0],
        "frame_end": frames[1],
        "frame_count": frames[1] - frames[0] + 1,
        "fps": 24,
        "source": {"library": "lib", "file": "idle.fbx", "sha256": "abc", "skeleton": "manny"},
    }
    rig["nmg_animations"] = json.dumps({name: entry}, sort_keys=True)


def test_scn001_a_posed_rig_does_not_fail_the_pivot_check(hero: Any, core: Any) -> None:
    # The premise: at rest the origin sits at the bottom center, so the pivot passes.
    pose_hero(0.0)
    assert _pivot_findings(core.validate_asset(_COLLECTION, "character")) == []

    pose_hero(_POSE)
    assert _pivot_findings(core.validate_asset(_COLLECTION, "character")) == []


def test_scn002_the_mesh_checks_measure_the_rest_pose(hero: Any, core: Any) -> None:
    pose_hero(_POSE)
    posed = core.validate_asset(_COLLECTION, "character")
    pose_hero(0.0)
    rest = core.validate_asset(_COLLECTION, "character")

    assert posed["findings"] == rest["findings"]
    assert posed["snapshot"] == rest["snapshot"]


def test_scn003_export_variants_does_not_bake_the_pose(
    hero: Any, rig_core: Any, cleanup: Any, variants: Any, tmp_path: Path
) -> None:
    """The export clause of SCN003 only; the reduce_asset clause is not proven here (see module)."""
    rest_root = tmp_path / "rest"
    posed_root = tmp_path / "posed"
    pose_hero(0.0)
    variants.generate_variants(_COLLECTION, _CATEGORY, "character", str(rest_root))

    _build_hero(rig_core, cleanup)
    pose_hero(_POSE)
    variants.generate_variants(_COLLECTION, _CATEGORY, "character", str(posed_root))
    heads = _rest_heads_in_engine_axes()

    for variant in ("Desktop", "Mobile"):
        rest_glb = rest_root / _CATEGORY / _COLLECTION / variant / f"{_COLLECTION}.glb"
        posed_glb = posed_root / _CATEGORY / _COLLECTION / variant / f"{_COLLECTION}.glb"
        rest_bounds = _imported_mesh_bounds(rest_glb)
        posed_bounds = _imported_mesh_bounds(posed_glb)
        assert _largest_gap(posed_bounds, rest_bounds) <= _TOLERANCE, variant

        joints = _glb_joint_heads(posed_glb)
        assert joints, variant
        assert set(joints) <= set(heads), variant
        assert (
            _largest_gap(tuple(joints.values()), tuple(heads[name] for name in joints))
            <= _TOLERANCE
        ), variant


def test_scn004_the_scene_is_left_unchanged(
    hero: Any,
    core: Any,
    variants: Any,
    reduce_core: Any,
    enabled_addon: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pose_hero(_POSE)
    before = _pose_state()

    core.validate_asset(_COLLECTION, "character")
    assert _pose_state() == before

    def forced(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("forced failure")

    validate_module = importlib.import_module(f"{enabled_addon}.contract_core.validate")
    monkeypatch.setattr(validate_module, "geometry_findings", forced)
    with pytest.raises(RuntimeError, match="forced failure"):
        core.validate_asset(_COLLECTION, "character")
    monkeypatch.undo()
    assert _pose_state() == before

    refused = reduce_core.run_for_mcp(
        collection=_COLLECTION,
        asset_class="character",
        device="CPU",
        out_dir=str(tmp_path / "reduce"),
    )
    assert refused["error"]["code"] == "reduce.rigged"
    assert _pose_state() == before

    variants.generate_variants(_COLLECTION, _CATEGORY, "character", str(tmp_path / "export"))
    before = _pose_state()
    export_module = importlib.import_module(f"{enabled_addon}.variants_core.export")
    export_module.export_variants(_COLLECTION, _CATEGORY, str(tmp_path / "export"))
    assert _pose_state() == before

    monkeypatch.setattr(export_module, "mesh_records", forced)
    with pytest.raises(RuntimeError, match="forced failure"):
        export_module.export_variants(_COLLECTION, _CATEGORY, str(tmp_path / "export"))
    monkeypatch.undo()
    assert _pose_state() == before


def test_scn005_exporting_clips_leaves_every_pose_bone_at_identity(
    hero: Any, enabled_addon: str, tmp_path: Path
) -> None:
    rig = bpy.data.objects[_RIG]
    _hold_provenance_clip(rig, "Idle", (1, 10), _LIFT_PER_FRAME)
    pose_hero(0.0)
    assert rig.animation_data is None or rig.animation_data.action is None

    anims = importlib.import_module(f"{enabled_addon}.finalize_core.anims")
    (record,) = anims.export_clips(_COLLECTION, ["Idle"], tmp_path / "Animations")

    assert record["name"] == "Idle"
    assert rig.animation_data is None or rig.animation_data.action is None
    assert _every_bone_at_identity()


def test_fr3_make_copy_evaluates_the_rest_pose(hero: Any, enabled_addon: str) -> None:
    """FR3 on the copy step: make_copy stores the rest geometry even while the rig is posed."""
    decimate = importlib.import_module(f"{enabled_addon}.reduce_core.decimate")
    pose_hero(0.0)
    rest = _world_bounds(_mesh())
    pose_hero(_POSE)
    assert _largest_gap(_world_bounds(_mesh()), rest) > 5 * _TOLERANCE

    copy = decimate.make_copy(_mesh(), bpy.data.collections[_COLLECTION], "SM_Hero_Copy")

    assert _largest_gap(_world_bounds(copy), rest) <= _TOLERANCE
    assert not _every_bone_at_identity()
