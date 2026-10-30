"""Review renders and the texture proof under Blender headless: AC4, AC5, AC7 (SCN004, SCN005).

Renders use a test resolution of 128 px. Each test checks that the user's scene is unchanged.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .contract_fixtures import build_crate, clear_scene, export_crate  # noqa: E402

RESOLUTION = 128
GAP = 16
LABEL_BAND = 40
VIEWS = ("front", "back", "side", "three_quarter")


@pytest.fixture(autouse=True)
def _isolated_scene() -> Iterator[None]:
    yield
    clear_scene()


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core")


def _scene_state() -> dict[str, Any]:
    scene = bpy.context.scene
    return {
        "scene": scene.name,
        "scenes": sorted(item.name for item in bpy.data.scenes),
        "objects": sorted(obj.name for obj in scene.objects),
        "collections": sorted(collection.name for collection in bpy.data.collections),
        "world": scene.world.name if scene.world is not None else None,
        "camera": scene.camera.name if scene.camera is not None else None,
    }


def _image_size(path: Path) -> tuple[int, int]:
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        return int(image.size[0]), int(image.size[1])
    finally:
        bpy.data.images.remove(image)


def _write_pre_bake_stand_in(path: Path) -> None:
    image = bpy.data.images.new("__test_pre_bake", RESOLUTION, RESOLUTION)
    try:
        image.filepath_raw = str(path)
        image.file_format = "PNG"
        image.save()
    finally:
        bpy.data.images.remove(image)


# ---------------------------------------------------------------------------
# AC4 / SCN004: review renders in a known folder
# ---------------------------------------------------------------------------


def test_ac4_review_renders_write_eight_files_and_keep_the_scene(core: Any, tmp_path: Path) -> None:
    build_crate()
    before = _scene_state()

    result = core.render_review("Crate", tmp_path, resolution=RESOLUTION)

    expected = {
        tmp_path / variant / f"Crate_{view}.png"
        for variant in ("desktop", "mobile")
        for view in VIEWS
    }
    assert {Path(path) for path in result["files"]} == expected
    assert all(path.is_file() for path in expected)
    assert all(_image_size(path) == (RESOLUTION, RESOLUTION) for path in expected)
    assert _scene_state() == before


def test_ac4_review_renders_skip_mobile_when_it_is_absent(core: Any, tmp_path: Path) -> None:
    build_crate()
    bpy.data.collections.remove(bpy.data.collections["Crate_Mobile"], do_unlink=True)

    result = core.render_review("Crate", tmp_path, resolution=RESOLUTION)

    assert len(result["files"]) == len(VIEWS)
    assert not (tmp_path / "mobile").exists()


# ---------------------------------------------------------------------------
# AC5 / SCN005: the texture proof sheet
# ---------------------------------------------------------------------------


def test_ac5_proof_sheet_with_pre_bake_has_three_labeled_panels(core: Any, tmp_path: Path) -> None:
    build_crate()
    variant_root = export_crate(tmp_path / "export")
    pre_bake = tmp_path / "pre_bake.png"
    _write_pre_bake_stand_in(pre_bake)
    before = _scene_state()

    result = core.render_texture_proof(
        variant_root / "Desktop",
        tmp_path / "proof",
        pre_bake=pre_bake,
        resolution=RESOLUTION,
    )

    proof = Path(result["proof"])
    assert proof == tmp_path / "proof" / "desktop" / "Crate_proof.png"
    assert proof.is_file()
    width, height = _image_size(proof)
    assert width == 3 * RESOLUTION + 2 * GAP
    assert height == LABEL_BAND + RESOLUTION
    assert _scene_state() == before


def test_ac5_proof_sheet_without_pre_bake_has_two_panels(core: Any, tmp_path: Path) -> None:
    build_crate()
    variant_root = export_crate(tmp_path / "export")

    result = core.render_texture_proof(
        variant_root / "Desktop",
        tmp_path / "proof",
        resolution=RESOLUTION,
    )

    width, _height = _image_size(Path(result["proof"]))
    assert width == 2 * RESOLUTION + GAP


def test_ac5_proof_leaves_no_reimported_datablocks(core: Any, tmp_path: Path) -> None:
    build_crate()
    variant_root = export_crate(tmp_path / "export")
    before_objects = {obj.name for obj in bpy.data.objects}
    before_materials = {material.name for material in bpy.data.materials}

    core.render_texture_proof(variant_root / "Desktop", tmp_path / "proof", resolution=RESOLUTION)

    assert {obj.name for obj in bpy.data.objects} == before_objects
    assert {material.name for material in bpy.data.materials} == before_materials


# ---------------------------------------------------------------------------
# AC7: the operator writes the same files as the direct call
# ---------------------------------------------------------------------------


def test_ac7_render_operator_writes_the_review_files(enabled_addon: str, tmp_path: Path) -> None:
    build_crate()

    result = bpy.ops.nmggamedev.render_review(
        collection_name="Crate",
        out_dir=str(tmp_path),
        resolution=RESOLUTION,
    )

    assert result == {"FINISHED"}
    stored = json.loads(bpy.context.scene.nmg_game_dev.last_result)
    assert len(stored["files"]) == 2 * len(VIEWS)
    assert all(Path(path).is_file() for path in stored["files"])
