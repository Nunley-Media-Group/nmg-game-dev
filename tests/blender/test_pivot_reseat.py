"""Rigged pivot tolerance and the Desktop re-seat under Blender headless: AC1-AC6 of #244.

A rigged asset at rest may sit up to 5 mm off the origin at authoring time, and the variants step
moves its Desktop mesh data onto the origin. Static assets keep the 1 mm tolerance. SCN002 and
SCN005 guard behavior that must not change: the re-seat moves only mesh data, and static assets
are not re-seated.

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

import bmesh  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from .contract_fixtures import build_crate, clear_scene  # noqa: E402
from .rig_fixtures import add_baked_hero_material, build_hero, reset_scene  # noqa: E402

#: The bottom center AC1 places the rigged hero at, in metres.
MISALIGNED = (0.0006, 0.0013, -0.0007)
#: The 1 mm tolerance that static assets, the origin, and export-time validation keep.
ONE_MM = 1e-3
_CATEGORY = "Characters"


@pytest.fixture(autouse=True)
def _isolated_scene() -> Iterator[None]:
    yield
    clear_scene()


@pytest.fixture()
def contract(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core")


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.variants_core")


@pytest.fixture()
def cleanup(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.variants_core.cleanup")


@pytest.fixture()
def rigged_hero(enabled_addon: str) -> Iterator[None]:
    """Collection Hero: SM_Hero skinned to SK_Hero, with a baked surface, at the origin."""
    reset_scene()
    rig_core = importlib.import_module(f"{enabled_addon}.rig_core")
    assert rig_core.rig_humanoid("Hero", "humanoid", build_hero())["status"] == "ok"
    add_baked_hero_material()
    yield
    reset_scene()


def _meshes(collection_name: str) -> list[Any]:
    collection = bpy.data.collections[collection_name]
    return sorted(
        (obj for obj in collection.all_objects if obj.type == "MESH"), key=lambda obj: obj.name
    )


def _world_bottom_center(collection_name: str) -> Vector:
    """The bottom center from the world-space vertices, measured independently of the validator."""
    points = [
        obj.matrix_world @ vert.co for obj in _meshes(collection_name) for vert in obj.data.vertices
    ]
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    zs = [point.z for point in points]
    return Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs)))


def _place_bottom_center(collection_name: str, target: tuple[float, float, float]) -> None:
    """Translate every mesh's data so the bottom center lands on target. Object transforms stay."""
    bpy.context.view_layer.update()
    shift = Vector(target) - _world_bottom_center(collection_name)
    for obj in _meshes(collection_name):
        obj.data.transform(Matrix.Translation(obj.matrix_world.inverted().to_3x3() @ shift))
        obj.data.update()
    bpy.context.view_layer.update()


def _pivot_findings(report: dict[str, Any]) -> list[dict[str, str]]:
    return [item for item in report["findings"] if item["rule"] == "pivot.bottom_center"]


def _add_skinned_part() -> Any:
    """A second skinned part, SM_Hero_Part, parented to SM_Hero and weighted to one bone."""
    rig = bpy.data.objects["SK_Hero"]
    root = bpy.data.objects["SM_Hero"]
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.12)
    bmesh.ops.translate(bm, vec=(0.3, 0.0, 1.1), verts=list(bm.verts))
    mesh = bpy.data.meshes.new("SM_Hero_Part")
    bm.to_mesh(mesh)
    bm.free()
    part = bpy.data.objects.new("SM_Hero_Part", mesh)
    bpy.data.collections["Hero"].objects.link(part)
    part.parent = root
    skin = part.modifiers.new("Armature", "ARMATURE")
    skin.object = rig
    group = part.vertex_groups.new(name="spine_01")
    group.add([vert.index for vert in mesh.vertices], 1.0, "REPLACE")
    return part


def _structure() -> dict[str, Any]:
    """Transforms, parents, modifiers, vertex groups with weights, and bones of the rigged Hero."""
    rig = bpy.data.objects["SK_Hero"]
    objects = [obj for obj in bpy.data.objects if obj.name.startswith(("SM_Hero", "SK_Hero"))]
    return {
        "matrix_world": {obj.name: [tuple(row) for row in obj.matrix_world] for obj in objects},
        "parent": {obj.name: obj.parent.name if obj.parent else None for obj in objects},
        "modifiers": {
            obj.name: [
                (
                    modifier.name,
                    modifier.type,
                    getattr(modifier, "object", None) and modifier.object.name,
                )
                for modifier in obj.modifiers
            ]
            for obj in objects
        },
        "groups": {obj.name: [group.name for group in obj.vertex_groups] for obj in objects},
        "weights": {
            obj.name: [
                [(group.group, group.weight) for group in vert.groups] for vert in obj.data.vertices
            ]
            for obj in objects
            if obj.type == "MESH"
        },
        "bones": [
            (bone.name, tuple(bone.head_local), tuple(bone.tail_local)) for bone in rig.data.bones
        ],
    }


def test_scn001_millimetre_offset_on_rigged_mesh_no_longer_blocks_finalize(
    contract: Any, cleanup: Any, rigged_hero: None
) -> None:
    _place_bottom_center("Hero", MISALIGNED)

    report = contract.validate_asset("Hero", "character", authored=True)
    assert _pivot_findings(report) == []

    result = cleanup.cleanup_desktop("Hero")
    assert result["pivot"]["reseated"] is True
    assert all(abs(value) <= ONE_MM for value in _world_bottom_center("Hero"))


def test_scn002_reseat_moves_only_mesh_data(cleanup: Any, rigged_hero: None) -> None:
    _add_skinned_part()
    _place_bottom_center("Hero", MISALIGNED)
    structure_before = _structure()
    points_before = {
        obj.name: [vert.co.copy() for vert in obj.data.vertices] for obj in _meshes("Hero")
    }

    report = cleanup.reseat_desktop("Hero")

    assert report["reseated"] is True
    assert _structure() == structure_before
    for obj in _meshes("Hero"):
        for index, vert in enumerate(obj.data.vertices):
            moved = obj.matrix_world @ vert.co - obj.matrix_world @ points_before[obj.name][index]
            # Root and part move by the same world offset: the negative of the bottom center.
            assert (moved + Vector(MISALIGNED)).length < 1e-5, obj.name


def test_scn003_rigged_asset_on_origin_is_left_alone(cleanup: Any, rigged_hero: None) -> None:
    _place_bottom_center("Hero", (0.0, 0.0, 0.0))

    result = cleanup.cleanup_desktop("Hero")
    assert result["pivot"] == {"reseated": False, "offset": [0.0, 0.0, 0.0]}

    points_before = [vert.co.copy() for vert in bpy.data.objects["SM_Hero"].data.vertices]
    report = cleanup.reseat_desktop("Hero")
    points_after = [vert.co.copy() for vert in bpy.data.objects["SM_Hero"].data.vertices]
    assert report == {"reseated": False, "offset": [0.0, 0.0, 0.0]}
    assert points_after == points_before


def test_scn004_large_rigged_offset_still_fails_and_names_the_limit(
    contract: Any, rigged_hero: None
) -> None:
    _place_bottom_center("Hero", (0.0, 0.0, 0.02))

    report = contract.validate_asset("Hero", "character", authored=True)

    pivots = _pivot_findings(report)
    assert len(pivots) == 1, pivots
    assert "5 mm" in pivots[0]["message"]
    assert "move the mesh data closer" in pivots[0]["message"]


def test_scn005_static_asset_keeps_one_millimetre_tolerance(contract: Any, cleanup: Any) -> None:
    build_crate()
    _place_bottom_center("Crate", (0.0, 0.0, 0.0013))
    failing = contract.validate_asset("Crate", "standard_prop", authored=True)
    assert len(_pivot_findings(failing)) == 1

    result = cleanup.cleanup_desktop("Crate")
    assert result["pivot"]["reseated"] is False
    # The static Desktop mesh is not re-seated, so its bottom center stays where it was.
    assert _world_bottom_center("Crate").z == pytest.approx(0.0013, abs=1e-6)

    build_crate()
    _place_bottom_center("Crate", (0.0, 0.0, 0.0008))
    passing = contract.validate_asset("Crate", "standard_prop", authored=True)
    assert _pivot_findings(passing) == []


def test_scn006_exported_variants_agree(
    contract: Any, cleanup: Any, core: Any, enabled_addon: str, rigged_hero: None, tmp_path: Path
) -> None:
    _place_bottom_center("Hero", MISALIGNED)
    cleanup.cleanup_desktop("Hero")
    core.optimize_mobile("Hero", "character")

    export_report = contract.validate_asset("Hero", "character")
    assert _pivot_findings(export_report) == []

    export = importlib.import_module(f"{enabled_addon}.variants_core.export")
    export.export_variants("Hero", _CATEGORY, str(tmp_path))
    variant_root = tmp_path / _CATEGORY / "Hero"
    for variant in ("Desktop", "Mobile"):
        reimport = contract.run_isolated(variant_root / variant, export_report)
        pivots = [
            item for item in reimport["findings"] if item["rule"].startswith("reimport.pivot")
        ]
        assert pivots == [], (variant, pivots)
