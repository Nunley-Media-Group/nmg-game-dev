"""Rigged finalize under Blender headless: SCN001-SCN004 of #102, plus the armature-name guard.

A character rigged with rig_humanoid keeps its skin through cleanup, exports skinned FBX, and
writes one skinned FBX per Mobile LOD. Each test exports through variants_core, then re-imports
the written FBX into a fresh scene. The BDD scenarios in tests/bdd/test_rigged_finalize_bdd.py
run these tests by node ID.

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .rig_fixtures import (  # noqa: E402
    MANNY_BONE_NAMES,
    add_baked_hero_material,
    build_hero,
    reset_scene,
)

_CATEGORY = "Characters"
_ARMATURE_BONES = len(MANNY_BONE_NAMES)
_MOBILE_TRIS = 15000
_LOD_FILES = ("SM_Hero.fbx", "SM_Hero_LOD1.fbx", "SM_Hero_LOD2.fbx")


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.variants_core")


@pytest.fixture()
def rigged_hero(enabled_addon: str) -> Any:
    """Collection Hero: SM_Hero skinned to SK_Hero, with a baked surface."""
    reset_scene()
    rig_core = importlib.import_module(f"{enabled_addon}.rig_core")
    assert rig_core.rig_humanoid("Hero", "humanoid", build_hero())["status"] == "ok"
    add_baked_hero_material()
    yield rig_core
    reset_scene()


def _export(core: Any, export_root: Path) -> Path:
    """Export Hero through the finalize path, returning <export_root>/Characters/Hero."""
    result = core.generate_variants("Hero", _CATEGORY, "character", str(export_root))
    assert result["rigged"] is True
    return export_root / _CATEGORY / "Hero"


def _import_fresh(fbx: Path) -> None:
    reset_scene()
    bpy.ops.import_scene.fbx(filepath=str(fbx))


def _skinned_to(mesh: Any, armature_name: str) -> bool:
    """True when mesh deforms through an Armature modifier that targets the named armature."""
    return any(
        modifier.type == "ARMATURE"
        and modifier.object is not None
        and modifier.object.name == armature_name
        for modifier in mesh.modifiers
    )


def _assert_imported_groups(mesh: Any) -> None:
    """FBX import keeps only the bones that carry weight (the Manny root carries none)."""
    names = {group.name for group in mesh.vertex_groups}
    assert names
    assert names <= set(MANNY_BONE_NAMES)


def _triangles(mesh: Any) -> int:
    return sum(max(len(polygon.vertices) - 2, 0) for polygon in mesh.polygons)


def _with_array(hero: Any) -> None:
    """Add a non-Armature modifier that doubles the mesh along X without overlapping copies."""
    array = hero.modifiers.new("Array", "ARRAY")
    array.count = 2
    array.relative_offset_displace = (1.1, 0.0, 0.0)


# ---------------------------------------------------------------------------
# SCN001: the Desktop FBX holds the skinned armature
# ---------------------------------------------------------------------------


def test_scn001_desktop_fbx_holds_the_skinned_armature(
    rigged_hero: Any, core: Any, tmp_path: Path
) -> None:
    root = _export(core, tmp_path)

    _import_fresh(root / "Desktop" / "SM_Hero.fbx")

    armature = bpy.data.objects["Armature"]
    assert armature.type == "ARMATURE"
    assert {bone.name for bone in armature.data.bones} == set(MANNY_BONE_NAMES)
    assert len(armature.data.bones) == _ARMATURE_BONES
    mesh = bpy.data.objects["SM_Hero"]
    assert _skinned_to(mesh, "Armature")
    _assert_imported_groups(mesh)


# ---------------------------------------------------------------------------
# SCN002: Mobile exports one skinned FBX per LOD, each within its budget
# ---------------------------------------------------------------------------


def test_scn002_mobile_fbx_per_lod_each_holds_the_armature_and_a_skinned_mesh(
    rigged_hero: Any, core: Any, tmp_path: Path
) -> None:
    root = _export(core, tmp_path)

    assert sorted(path.name for path in (root / "Mobile").glob("*.fbx")) == sorted(_LOD_FILES)
    for name in _LOD_FILES:
        _import_fresh(root / "Mobile" / name)
        armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
        meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
        assert [armature.name for armature in armatures] == ["Armature"], name
        assert len(meshes) == 1, name
        assert _skinned_to(meshes[0], "Armature"), name
        _assert_imported_groups(meshes[0])


def test_scn002_lod_ratios_stay_within_the_mobile_budget(
    rigged_hero: Any, core: Any, tmp_path: Path
) -> None:
    root = _export(core, tmp_path)

    counts: dict[str, int] = {}
    for name in _LOD_FILES:
        _import_fresh(root / "Mobile" / name)
        counts[name] = _triangles(bpy.data.objects[name.removesuffix(".fbx")].data)

    lod0 = counts["SM_Hero.fbx"]
    assert lod0 <= _MOBILE_TRIS
    assert counts["SM_Hero_LOD1.fbx"] <= lod0 * 0.5
    assert counts["SM_Hero_LOD2.fbx"] <= lod0 * 0.25


def test_scn002_mobile_is_skinned_meshes_with_no_lod_group(
    rigged_hero: Any, core: Any, tmp_path: Path
) -> None:
    core.generate_variants("Hero", _CATEGORY, "character", str(tmp_path))

    mobile = bpy.data.collections["Hero_Mobile"]
    assert not [obj for obj in mobile.all_objects if obj.get("fbx_type") == "LodGroup"]
    root = bpy.data.objects["SM_Hero_Mobile"]
    for level in (1, 2):
        lod = bpy.data.objects[f"SM_Hero_Mobile_LOD{level}"]
        assert lod.parent == bpy.data.objects["SK_Hero"]
        assert _skinned_to(lod, "SK_Hero")
        assert len(lod.vertex_groups) == _ARMATURE_BONES
    assert _skinned_to(root, "SK_Hero")
    assert root.parent == bpy.data.objects["SK_Hero"]


# ---------------------------------------------------------------------------
# SCN003: cleanup applies the other modifiers and keeps the skin
# ---------------------------------------------------------------------------


def test_scn003_cleanup_applies_the_non_armature_modifier(rigged_hero: Any, core: Any) -> None:
    hero = bpy.data.objects["SM_Hero"]
    _with_array(hero)
    before = _triangles(hero.data)

    core.cleanup_desktop("Hero")

    assert [modifier.type for modifier in hero.modifiers] == ["ARMATURE"]
    assert _triangles(hero.data) >= before * 1.9


def test_scn003_cleanup_keeps_the_armature_modifier_and_vertex_groups(
    rigged_hero: Any, core: Any
) -> None:
    hero = bpy.data.objects["SM_Hero"]
    _with_array(hero)

    core.cleanup_desktop("Hero")

    (skin,) = [modifier for modifier in hero.modifiers if modifier.type == "ARMATURE"]
    assert skin.object == bpy.data.objects["SK_Hero"]
    assert skin.show_viewport
    assert len(hero.vertex_groups) == _ARMATURE_BONES
    assert any(len(vertex.groups) for vertex in hero.data.vertices)


# ---------------------------------------------------------------------------
# SCN004: an unrigged asset keeps the static path
# ---------------------------------------------------------------------------


def test_scn004_unrigged_asset_keeps_the_static_layout(
    build_crate: Any, core: Any, tmp_path: Path
) -> None:
    build_crate()

    result = core.generate_variants("Crate", "Props", "standard_prop", str(tmp_path))

    root = tmp_path / "Props" / "Crate"
    assert result["rigged"] is False
    assert sorted(path.name for path in (root / "Mobile").glob("*.fbx")) == ["SM_Crate.fbx"]
    sidecar = json.loads((root / "nmg-variants.json").read_text(encoding="utf-8"))
    assert sidecar["rigged"] is False
    assert "lod_files" not in sidecar["mobile"]
    assert sidecar["mobile"]["lod_levels"] == 3
    group = bpy.data.objects["SM_Crate_Mobile"]
    assert group.type == "EMPTY"
    assert group.get("fbx_type") == "LodGroup"
    _import_fresh(root / "Desktop" / "SM_Crate.fbx")
    assert not [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]


# ---------------------------------------------------------------------------
# Export contract details
# ---------------------------------------------------------------------------


def test_export_restores_the_rig_name_and_writes_the_sidecar(
    rigged_hero: Any, core: Any, tmp_path: Path
) -> None:
    root = _export(core, tmp_path)

    assert bpy.data.objects.get("SK_Hero") is not None
    assert bpy.data.objects["SK_Hero"].name == "SK_Hero"
    sidecar = json.loads((root / "nmg-variants.json").read_text(encoding="utf-8"))
    assert sidecar["rigged"] is True
    assert sidecar["mobile"]["lod_files"] == [f"Mobile/{name}" for name in _LOD_FILES]


def test_armature_name_taken_fails_before_any_file_is_written(
    rigged_hero: Any, core: Any, tmp_path: Path
) -> None:
    clash = bpy.data.objects.new("Armature", None)
    bpy.context.scene.collection.objects.link(clash)

    with pytest.raises(core.VariantError) as failure:
        core.generate_variants("Hero", _CATEGORY, "character", str(tmp_path))

    assert failure.value.code == "variants.armature_name_taken"
    assert not (tmp_path / _CATEGORY).exists()
    assert bpy.data.objects["SK_Hero"].name == "SK_Hero"


def test_child_parts_keep_lod0_only_and_are_skinned_with_the_root(
    rigged_hero: Any, core: Any, tmp_path: Path
) -> None:
    import bmesh  # noqa: PLC0415

    root_obj = bpy.data.objects["SM_Hero"]
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.2)
    mesh = bpy.data.meshes.new("SM_Hero_Hat")
    bm.to_mesh(mesh)
    bm.free()
    part = bpy.data.objects.new("SM_Hero_Hat", mesh)
    part.location = (0.0, 0.0, 1.9)
    bpy.data.collections["Hero"].objects.link(part)
    part.parent = root_obj

    result = core.generate_variants("Hero", _CATEGORY, "character", str(tmp_path))

    assert result["mobile"]["lod_levels"] == 1
    assert result["mobile"]["lod_files"] == ["Mobile/SM_Hero.fbx"]
    assert sorted(
        path.name for path in (tmp_path / _CATEGORY / "Hero" / "Mobile").glob("*.fbx")
    ) == ["SM_Hero.fbx"]
    mobile_root = bpy.data.objects["SM_Hero_Mobile"]
    mobile_part = bpy.data.objects["SM_Hero_Hat_Mobile"]
    assert _skinned_to(mobile_root, "SK_Hero")
    assert mobile_part.parent == mobile_root
    assert not _skinned_to(mobile_part, "SK_Hero")
