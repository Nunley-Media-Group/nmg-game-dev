"""Tiling-mode contract under Blender headless: AC2 (#67, SCN002) and the #147 seam measure.

#147 AC1 (exactly periodic fine noise bakes), AC2 (a non-periodic ramp still raises not_seamless),
and AC5 (texture-gen make_seamless output bakes unedited) judge each baked texture with the
add-on's bpy-free seam_metric, loaded by file path.

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
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
    noise_image,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADDON_CORE = _REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon" / "bake_core"
_TEXTURE_SEAMLESS = _REPO_ROOT / "src" / "nmg_game_dev" / "texture" / "seamless.py"


def _load_by_path(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # A dataclass resolves its module through sys.modules while the module executes.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


seam_metric = _load_by_path("nmg_seam_metric_blender_test", _ADDON_CORE / "seam_metric.py")
texture_seamless = _load_by_path("nmg_texture_seamless_blender_test", _TEXTURE_SEAMLESS)


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


def _rgb(image: Any) -> np.ndarray:
    width, height = image.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    return pixels.reshape(height, width, 4)[..., :3]


def _baked_rgb(path: str) -> np.ndarray:
    image = bpy.data.images.load(path, check_existing=False)
    rgb = _rgb(image)
    bpy.data.images.remove(image)
    return rgb


def _assert_textures_pass(paths: list[str]) -> None:
    for path in paths:
        assert seam_metric.passes(_baked_rgb(path)), path


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
    _assert_textures_pass(result["desktop_textures"])


def test_ac1_periodic_fine_noise_tiling_material_bakes_seamless(
    core: Any, tmp_path: Path, budgets: str
) -> None:
    """#147 AC1: an exactly periodic busy texture bakes with no error and every texture passes."""
    source = noise_image("M_Road_noise", periodic=True)
    assert min(seam.interior for seam in seam_metric.measure(_rgb(source))) > 0.04
    build_tiling_plane("Road", image_material("M_Road_Src", source), uv_span=10.0)

    result = core.bake_asset("Road", "environment_piece", tmp_path / "out", budgets, "CPU", 4)

    assert result["mode"] == "tiling"
    _assert_textures_pass(result["desktop_textures"] + result["mobile_textures"])


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


def test_ac5_make_seamless_output_bakes_without_edits(
    core: Any, tmp_path: Path, budgets: str
) -> None:
    """#147 AC5: uint8 white noise through texture-gen's make_seamless bakes with no error."""
    white = np.random.default_rng(0).integers(0, 256, size=(256, 256, 3), dtype=np.uint8)
    tiled = texture_seamless.make_seamless(white)
    tiled_image = noise_image("M_Road_tiled", array=tiled)
    build_tiling_plane("Road", image_material("M_Road_Src", tiled_image))

    result = core.bake_asset("Road", "environment_piece", tmp_path / "out", budgets, "CPU", 4)

    assert result["mode"] == "tiling"
    _assert_textures_pass(result["desktop_textures"] + result["mobile_textures"])


def test_ac2_low_texel_density_fails(core: Any, tmp_path: Path, budgets: str) -> None:
    """AC2: a mesh whose UVs cover too little of the texture fails texel_density."""
    build_tiling_plane("Road", _periodic_material("M_Road_Src"), uv_span=0.01)
    with pytest.raises(core.BakeError) as info:
        core.bake_asset("Road", "environment_piece", tmp_path / "out", budgets, "CPU", 4)
    assert info.value.reason == "texel_density"
    assert info.value.target == "SM_Road"
