"""Unique-bake contract under Blender headless: AC1, AC3, AC4, AC5 (#67).

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
import json
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

bpy = pytest.importorskip("bpy")

from .bake_fixtures import (  # noqa: E402
    budgets_file,
    build_asset,
    checker_image,
    clear_scene,
    image_material,
    plain_material,
    procedural_material,
    triplanar_material,
)

_ALLOWED_NODES = {"BSDF_PRINCIPLED", "TEX_IMAGE", "NORMAL_MAP", "SEPARATE_COLOR", "OUTPUT_MATERIAL"}
_KINDS = ("procedural", "triplanar", "image-texture")


@pytest.fixture(autouse=True)
def _isolated_scene() -> Iterator[None]:
    # The default startup scene's Cube encloses the asset and would occlude its AO bake.
    clear_scene()
    yield
    clear_scene()


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.bake_core")


@pytest.fixture()
def budgets(tmp_path: Path) -> str:
    return budgets_file(tmp_path)


def _material_for(kind: str, name: str) -> Any:
    if kind == "procedural":
        return procedural_material(name)
    if kind == "triplanar":
        return triplanar_material(name)
    return image_material(name, checker_image(f"{name}_src"))


def _images_in(material: Any) -> dict[str, Any]:
    return {
        node.image.name: node.image
        for node in material.node_tree.nodes
        if node.type == "TEX_IMAGE" and node.image is not None
    }


def _single_collection_bake(core: Any, tmp_path: Path, budgets: str, kind: str) -> dict[str, Any]:
    build_asset("Crate", [_material_for(kind, "Authored")])
    return core.bake_asset("Crate", "standard_prop", tmp_path / "out", budgets, "CPU", 4)


@pytest.mark.parametrize("kind", _KINDS)
def test_ac1_authored_material_bakes_to_contract_set(
    core: Any, tmp_path: Path, budgets: str, kind: str
) -> None:
    """AC1: the bake writes BC/N/ORM for each kind, rewires to allowed nodes, and passes proof."""
    result = _single_collection_bake(core, tmp_path, budgets, kind)

    assert result["kind"] == "bake"
    assert result["merged"] is False
    assert result["cache_hit"] is False
    assert len(result["materials"]) == 1
    assert result["materials"][0]["name"] == "M_Crate_Body"

    for variant in ("desktop", "mobile"):
        for kind_name in ("BC", "N", "ORM"):
            assert Path(result["materials"][0][variant][kind_name]).is_file()

    material = bpy.data.materials["M_Crate_Body"]
    node_types = {node.type for node in material.node_tree.nodes}
    assert node_types <= _ALLOWED_NODES, f"unexpected nodes: {node_types - _ALLOWED_NODES}"
    images = _images_in(material)
    colorspaces = {
        name.rsplit("_", 1)[-1]: image.colorspace_settings.name for name, image in images.items()
    }
    assert colorspaces == {"BC": "sRGB", "N": "Non-Color", "ORM": "Non-Color"}

    proof = result["proof"]
    assert proof["mean_abs_diff"] <= 0.03, proof
    assert proof["outlier_ratio"] <= 0.02, proof


def test_ac1_every_mesh_has_one_uvmap(core: Any, tmp_path: Path, budgets: str) -> None:
    """AC1: after the bake each mesh has exactly one UV map, named UVMap."""
    collection = build_asset("Crate", [_material_for("procedural", "Authored")], packed=False)
    core.bake_asset("Crate", "standard_prop", tmp_path / "out", budgets, "CPU", 4)
    for obj in collection.objects:
        assert [layer.name for layer in obj.data.uv_layers] == ["UVMap"]


def test_ac1_valid_existing_layout_is_kept(core: Any, tmp_path: Path, budgets: str) -> None:
    """AC1: a valid non-overlapping UVMap is kept unchanged."""
    collection = build_asset("Crate", [_material_for("procedural", "Authored")], packed=True)
    obj = collection.objects[0]
    before = [tuple(item.uv) for item in obj.data.uv_layers["UVMap"].data]
    core.bake_asset("Crate", "standard_prop", tmp_path / "out", budgets, "CPU", 4)
    after = [tuple(item.uv) for item in obj.data.uv_layers["UVMap"].data]
    assert before == after


def test_ac1_overlapping_layout_is_unwrapped(core: Any, tmp_path: Path, budgets: str) -> None:
    """AC1: an overlapping layout is replaced by one joint non-overlapping unwrap."""
    collection = build_asset("Crate", [_material_for("procedural", "Authored")], packed=False)
    obj = collection.objects[0]
    before = [tuple(item.uv) for item in obj.data.uv_layers["UVMap"].data]
    core.bake_asset("Crate", "standard_prop", tmp_path / "out", budgets, "CPU", 4)
    after = [tuple(item.uv) for item in obj.data.uv_layers["UVMap"].data]
    assert before != after
    assert [layer.name for layer in obj.data.uv_layers] == ["UVMap"]


def test_ac3_desktop_and_mobile_sizes_and_bytes(core: Any, tmp_path: Path, budgets: str) -> None:
    """AC3: Desktop PNGs are 256 px and Mobile PNGs 128 px, with identical names and byte totals."""
    result = _single_collection_bake(core, tmp_path, budgets, "procedural")
    assert result["desktop_px"] == 256
    assert result["mobile_px"] == 128
    desktop = sorted(Path(path).name for path in result["desktop_textures"])
    mobile = sorted(Path(path).name for path in result["mobile_textures"])
    assert desktop == mobile
    for path in result["desktop_textures"]:
        image = bpy.data.images.load(path, check_existing=False)
        assert tuple(image.size) == (256, 256)
        bpy.data.images.remove(image)
    for path in result["mobile_textures"]:
        image = bpy.data.images.load(path, check_existing=False)
        assert tuple(image.size) == (128, 128)
        bpy.data.images.remove(image)
    assert result["texture_bytes_desktop"] == sum(
        Path(path).stat().st_size for path in result["desktop_textures"]
    )
    assert result["texture_bytes_mobile"] == sum(
        Path(path).stat().st_size for path in result["mobile_textures"]
    )


def test_ac4_materials_over_mobile_limit_merge_into_body(
    core: Any, tmp_path: Path, budgets: str
) -> None:
    """AC4: three materials on a standard_prop (Mobile limit 1) merge into one Body set."""
    materials = [
        procedural_material("M_Crate_Wood"),
        triplanar_material("M_Crate_Metal"),
        plain_material("M_Crate_Trim", (0.2, 0.2, 0.8)),
    ]
    collection = build_asset("Crate", materials, cuts=2)
    result = core.bake_asset("Crate", "standard_prop", tmp_path / "out", budgets, "CPU", 4)
    assert result["merged"] is True
    assert [item["name"] for item in result["materials"]] == ["M_Crate_Body"]
    textures = sorted(Path(path).name for path in result["desktop_textures"])
    assert textures == [
        "T_Crate_Body_BC.png",
        "T_Crate_Body_N.png",
        "T_Crate_Body_ORM.png",
    ]
    for obj in collection.objects:
        assert {slot.material.name for slot in obj.material_slots} == {"M_Crate_Body"}
        assert all(polygon.material_index == 0 for polygon in obj.data.polygons)
        assert [layer.name for layer in obj.data.uv_layers] == ["UVMap"]


def test_ac4_materials_at_or_under_limit_keep_one_set_each(
    core: Any, tmp_path: Path, budgets: str
) -> None:
    """AC4: a hero_prop with two materials (Mobile limit 2) keeps one baked material each."""
    materials = [procedural_material("M_Crate_Wood"), plain_material("M_Crate_Trim")]
    build_asset("Crate", materials, cuts=2)
    budgets_path = Path(budgets)
    overrides = json.loads(budgets_path.read_text(encoding="utf-8"))
    overrides["hero_prop"] = {"max_texture_px": 128, "desktop": {"max_texture_px": 256}}
    budgets_path.write_text(json.dumps(overrides), encoding="utf-8")
    result = core.bake_asset("Crate", "hero_prop", tmp_path / "out", budgets, "CPU", 4)
    assert result["merged"] is False
    assert [item["name"] for item in result["materials"]] == [
        "M_Crate_Wood",
        "M_Crate_Trim",
    ]


def test_ac5_operator_and_direct_call_share_one_result(
    enabled_addon: str, tmp_path: Path, budgets: str
) -> None:
    """AC5: nmggamedev.bake_materials and bake_asset return the same paths and summary."""
    core = importlib.import_module(f"{enabled_addon}.bake_core")
    build_asset("Crate", [_material_for("procedural", "Authored")])
    direct = core.bake_asset("Crate", "standard_prop", tmp_path / "direct", budgets, "CPU", 4)

    clear_scene()
    build_asset("Crate", [_material_for("procedural", "Authored")])
    bpy.ops.nmggamedev.bake_materials(
        "EXEC_DEFAULT",
        collection_name="Crate",
        asset_class="standard_prop",
        out_dir=str(tmp_path / "operator"),
        budgets_path=budgets,
        device="CPU",
        samples=4,
    )
    operator = json.loads(bpy.context.scene.nmg_game_dev.last_result)

    assert operator["summary"] == direct["summary"]
    assert [Path(p).name for p in operator["desktop_textures"]] == [
        Path(p).name for p in direct["desktop_textures"]
    ]
    assert [Path(p).name for p in operator["mobile_textures"]] == [
        Path(p).name for p in direct["mobile_textures"]
    ]


def test_ac4_per_material_sets_keep_faces_and_their_own_channels(
    core: Any, tmp_path: Path, budgets: str
) -> None:
    """AC4: each material's faces stay on its own set, and its ORM carries its own AO.

    Regression: restoring material slots by popping them clamped face indices to 0, and a later
    channel pass then baked the second material's faces into the first material's images.
    """
    materials = [procedural_material("M_Crate_Wood"), plain_material("M_Crate_Trim")]
    collection = build_asset("Crate", materials, cuts=2)
    obj = collection.objects[0]
    before = Counter(obj.material_slots[p.material_index].material.name for p in obj.data.polygons)
    budgets_path = Path(budgets)
    overrides = json.loads(budgets_path.read_text(encoding="utf-8"))
    overrides["hero_prop"] = {"max_texture_px": 128, "desktop": {"max_texture_px": 256}}
    budgets_path.write_text(json.dumps(overrides), encoding="utf-8")

    core.bake_asset("Crate", "hero_prop", tmp_path / "out", budgets, "CPU", 4)

    after = Counter(obj.material_slots[p.material_index].material.name for p in obj.data.polygons)
    assert after == before
    trim_orm = next(
        node.image
        for node in bpy.data.materials["M_Crate_Trim"].node_tree.nodes
        if node.type == "TEX_IMAGE" and node.image is not None and "_ORM" in node.image.name
    )
    pixels = np.empty(trim_orm.size[0] * trim_orm.size[1] * 4, dtype=np.float32)
    trim_orm.pixels.foreach_get(pixels)
    covered = pixels.reshape(-1, 4)[:, 0] > 0.5
    assert covered.mean() > 0.05, "the second material's AO was not baked"
