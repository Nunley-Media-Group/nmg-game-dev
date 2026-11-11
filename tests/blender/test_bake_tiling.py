"""Tiling-mode contract under Blender headless: AC2 (#67, SCN002).

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

bpy = pytest.importorskip("bpy")

from .bake_fixtures import (  # noqa: E402
    budgets_file,
    build_tiling_plane,
    checker_image,
    clear_scene,
    image_material,
)
from .texel_fixtures import Strip, build_piece, slot_material  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_scene() -> Iterator[None]:
    clear_scene()
    yield
    clear_scene()


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.bake_core")


@pytest.fixture()
def budgets(tmp_path: Path) -> str:
    return budgets_file(tmp_path)


def _periodic_material(name: str) -> Any:
    return image_material(name, checker_image(f"{name}_src", periodic=True))


def _uv_values(obj: Any, layer_name: str) -> np.ndarray:
    layer = obj.data.uv_layers[layer_name]
    return np.array([[item.uv.x, item.uv.y] for item in layer.data], dtype=np.float64)


def test_ac2_tiling_keeps_uvs_and_names_the_map_uvmap(
    core: Any, tmp_path: Path, budgets: str
) -> None:
    """AC2: the UVs spanning 0 to 10 are unchanged and the map is named UVMap (SCN002)."""
    collection = build_tiling_plane("Road", _periodic_material("M_Road_Src"), uv_span=10.0)
    obj = collection.objects[0]
    before = _uv_values(obj, "UVMap")

    result = core.bake_asset("Road", "environment_piece", tmp_path / "out", budgets, "CPU", 4)

    assert result["mode"] == "tiling"
    assert [layer.name for layer in obj.data.uv_layers] == ["UVMap"]
    np.testing.assert_allclose(_uv_values(obj, "UVMap"), before)
    assert before.max() > 9.0


def test_ac2_each_baked_texture_is_seamless_and_density_passes(
    core: Any, tmp_path: Path, budgets: str
) -> None:
    """AC2: the periodic material bakes seamless sets; the density check passes (SCN002)."""
    build_tiling_plane("Road", _periodic_material("M_Road_Src"), uv_span=10.0)
    result = core.bake_asset("Road", "environment_piece", tmp_path / "out", budgets, "CPU", 4)
    assert result["desktop_px"] == 256
    assert result["mobile_px"] == 128
    for path in result["desktop_textures"]:
        image = bpy.data.images.load(path, check_existing=False)
        width, height = image.size
        pixels = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(pixels)
        bpy.data.images.remove(image)
        rgb = pixels.reshape(height, width, 4)[..., :3]
        assert float(np.mean(np.abs(rgb[:, 0] - rgb[:, -1]))) <= 0.04 + 1e-3
        assert float(np.mean(np.abs(rgb[0] - rgb[-1]))) <= 0.04 + 1e-3


def test_ac2_non_periodic_material_fails_not_seamless(
    core: Any, tmp_path: Path, budgets: str
) -> None:
    """AC2: a material whose opposite edges differ raises not_seamless and restores the file."""
    ramp = image_material("M_Road_Src", checker_image("M_Road_ramp", periodic=False))
    collection = build_tiling_plane("Road", ramp, uv_span=10.0)
    obj = collection.objects[0]
    with pytest.raises(core.BakeError) as info:
        core.bake_asset("Road", "environment_piece", tmp_path / "out", budgets, "CPU", 4)
    assert info.value.reason == "not_seamless"
    assert info.value.target == "M_Road_Src"
    assert obj.material_slots[0].material.name == "M_Road_Src"
    assert [layer.name for layer in obj.data.uv_layers] == ["UVMap"]
    assert "M_Road_Src_Authoring" not in bpy.data.materials


def test_ac2_low_texel_density_fails(core: Any, tmp_path: Path, budgets: str) -> None:
    """AC2: a mesh whose UVs cover too little of the texture fails texel_density."""
    build_tiling_plane("Road", _periodic_material("M_Road_Src"), uv_span=0.01)
    with pytest.raises(core.BakeError) as info:
        core.bake_asset("Road", "environment_piece", tmp_path / "out", budgets, "CPU", 4)
    assert info.value.reason == "texel_density"
    assert info.value.target == "SM_Road"


# ---------------------------------------------------------------------------
# #151: the bake measures each material slot with validation's rules (SCN002-SCN005, SCN007)
# ---------------------------------------------------------------------------


@pytest.fixture()
def tiling(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.bake_core.tiling")


def _piece_meshes(name: str, strips: list[Strip]) -> list[Any]:
    collection = build_piece(name, strips)
    meshes = [obj for obj in collection.all_objects if obj.type == "MESH"]
    return sorted(meshes, key=lambda obj: obj.name)


def test_scn002_bake_density_passes_a_dense_slot_beside_exempt_slots(tiling: Any) -> None:
    """SCN002 (AC2): the bake's density check passes the mesh validation passes."""
    meshes = _piece_meshes(
        "Road",
        [
            (slot_material("M_Road_Tile", 256), 1.2, 0.1),
            (slot_material("M_Road_Atlas", 256, trim=True), 0.1, 0.45),
            (slot_material("M_Road_Paint", 256), None, 0.45),
        ],
    )

    report = tiling.check_density(meshes, 256, 128)

    assert [entry["exempt"] for entry in report["SM_Road"][1:]] == ["trim_atlas", "flat_colour"]
    assert report["SM_Road"][0]["desktop"] == pytest.approx(307.2, abs=0.05)


def test_scn003_bake_names_the_failing_slot(core: Any, tmp_path: Path, budgets: str) -> None:
    """SCN003 (AC3): texel_density names the mesh, the failing material, px/m, and the minimum."""
    build_piece(
        "Road",
        [
            (slot_material("M_Road_Good", 256), 1.2, 0.5),
            (slot_material("M_Road_Low", 256), 0.5, 0.5),
        ],
    )

    with pytest.raises(core.BakeError) as info:
        core.bake_asset("Road", "environment_piece", tmp_path / "out", budgets, "CPU", 4)

    assert info.value.reason == "texel_density"
    assert info.value.target == "SM_Road"
    for fragment in ("SM_Road", "M_Road_Low", "128.0 px/m", "at Desktop size", "minimum is 256"):
        assert fragment in info.value.message
    assert "M_Road_Good" not in info.value.message


def test_scn004_bake_exempts_a_flat_colour_slot(tiling: Any) -> None:
    """SCN004 (AC4): a collapsed slot is flat_colour and exempt, with no marker."""
    meshes = _piece_meshes(
        "Road",
        [
            (slot_material("M_Road_Tile", 256), 1.2, 0.5),
            (slot_material("M_Road_Flat", 128), None, 0.5),
        ],
    )

    report = tiling.check_density(meshes, 256, 128)

    assert report["SM_Road"][1] == {"slot": 1, "material": "M_Road_Flat", "exempt": "flat_colour"}


def test_scn005_bake_exempts_a_marked_low_density_slot(tiling: Any) -> None:
    """SCN005 (AC5): a declared trim atlas is exempt; the check does not raise for it."""
    meshes = _piece_meshes(
        "Road",
        [
            (slot_material("M_Road_Tile", 256), 1.2, 0.5),
            (slot_material("M_Road_Atlas", 256, trim=True), 0.5, 0.5),
        ],
    )

    report = tiling.check_density(meshes, 256, 128)

    assert report["SM_Road"][1] == {"slot": 1, "material": "M_Road_Atlas", "exempt": "trim_atlas"}


def test_scn007_bake_report_lists_each_slot_with_its_densities(
    core: Any, tmp_path: Path, budgets: str
) -> None:
    """SCN007 (AC7): the bake report stores each mesh's slot densities as texel_density."""
    build_tiling_plane("Road", _periodic_material("M_Road_Src"), uv_span=10.0)

    result = core.bake_asset("Road", "environment_piece", tmp_path / "out", budgets, "CPU", 4)

    (entry,) = result["texel_density"]["SM_Road"]
    assert entry["slot"] == 0
    assert entry["material"] == "M_Road_Src"
    assert entry["desktop"] == pytest.approx(2560.0, abs=0.05)
    assert entry["mobile"] == pytest.approx(1280.0, abs=0.05)
