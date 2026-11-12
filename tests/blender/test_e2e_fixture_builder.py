"""The Gantry fixture builder, run in headless Blender (#145, T005).

``build_gantry()`` must give the opt-in finalize e2e test what it needs: a non-rigged root larger
than a metre, two child parts with origins away from the asset origin, and a child whose mesh
datablock differs from its object name. The test loads the builder by path and never contacts a
live Blender session. Run it with scripts/run-blender-tests.sh.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

bpy = pytest.importorskip("bpy")

_BUILDER = Path(__file__).resolve().parents[1] / "e2e" / "fixtures" / "build_multipart_fixture.py"


def _load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_multipart_fixture", _BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_gantry_makes_a_non_rigged_multi_part_static_asset() -> None:
    collection = _load_builder().build_gantry()

    meshes = [obj for obj in collection.objects if obj.type == "MESH"]
    assert len(meshes) == 3
    assert not any(obj.type == "ARMATURE" for obj in collection.objects)


def test_the_root_is_larger_than_a_metre_and_sits_on_the_origin() -> None:
    collection = _load_builder().build_gantry()

    root = collection.objects["SM_Gantry"]
    assert max(root.dimensions) > 1.0
    assert tuple(root.location) == (0.0, 0.0, 0.0)


def test_the_child_parts_have_origins_away_from_the_asset_origin() -> None:
    collection = _load_builder().build_gantry()

    root = collection.objects["SM_Gantry"]
    children = [obj for obj in collection.objects if obj is not root and obj.type == "MESH"]
    assert len(children) >= 2
    assert all(child.parent is root for child in children)
    assert all(child.location.length > 0.0 for child in children)


def test_one_child_datablock_differs_from_its_object_name() -> None:
    collection = _load_builder().build_gantry()

    trim = collection.objects["SM_Gantry_Trim"]
    assert trim.data.name == "SM_Gantry_Trim.001"


def test_each_mesh_has_its_own_material_slot_named_after_its_part() -> None:
    collection = _load_builder().build_gantry()

    slots = {
        obj.name: [slot.material.name for slot in obj.material_slots]
        for obj in collection.objects
        if obj.type == "MESH"
    }
    assert slots == {
        "SM_Gantry": ["M_Gantry_Body"],
        "SM_Gantry_Trim": ["M_Gantry_Trim"],
        "SM_Gantry_Hinge": ["M_Gantry_Hinge"],
    }
