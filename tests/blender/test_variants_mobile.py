"""The trim-atlas marker through the bake and the Mobile variant under Blender headless (#151).

FR5 and SCN008 (AC8): the marker survives Material.copy() into the _Mobile material, and a trim
atlas stays exempt on the baked material, on the Mobile variant, and in the Mobile validation.

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")
bmesh = pytest.importorskip("bmesh")

from .bake_fixtures import (  # noqa: E402
    budgets_file,
    build_tiling_plane,
    checker_image,
    clear_scene,
    image_material,
)
from .texel_fixtures import TRIM_PROPERTY  # noqa: E402

# Mobile limits for the environment piece in these tests: 128 px textures, one LOD chain.
MOBILE_BUDGET = {"tris": 40000, "max_texture_px": 128, "materials": 3}


@pytest.fixture(autouse=True)
def _isolated_scene() -> Iterator[None]:
    clear_scene()
    yield
    clear_scene()


@pytest.fixture()
def budgets(tmp_path: Path) -> str:
    return budgets_file(tmp_path)


def _grid(obj: Any) -> None:
    """Cut the one-quad plane into a grid, so the Mobile LOD chain has triangles to remove."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=15, use_grid_fill=True)
    bm.to_mesh(obj.data)
    bm.free()


def test_mobile_material_copy_keeps_the_trim_marker(enabled_addon: str) -> None:
    """FR5 (AC8): Material.copy() carries the marker, and an unmarked material stays unmarked."""
    textures = importlib.import_module(f"{enabled_addon}.variants_core.textures")
    atlas = bpy.data.materials.new("M_Road_Atlas")
    atlas.use_nodes = True
    atlas[TRIM_PROPERTY] = True
    body = bpy.data.materials.new("M_Road_Body")
    body.use_nodes = True

    atlas_copy = textures.mobile_material_copy(atlas, {})
    body_copy = textures.mobile_material_copy(body, {})

    assert atlas_copy.name == "M_Road_Atlas_Mobile"
    assert bool(atlas_copy.get(TRIM_PROPERTY)) is True
    assert body_copy.get(TRIM_PROPERTY) is None


def test_scn008_marker_holds_on_the_baked_and_mobile_materials(
    enabled_addon: str, tmp_path: Path, budgets: str
) -> None:
    """SCN008 (AC8): bake and Mobile keep the marker, and the Mobile validation exempts the slot."""
    core = importlib.import_module(f"{enabled_addon}.bake_core")
    contract = importlib.import_module(f"{enabled_addon}.contract_core")
    mobile = importlib.import_module(f"{enabled_addon}.variants_core.mobile")

    source: Any = image_material("M_Road_Src", checker_image("M_Road_Src_img", periodic=True))
    source[TRIM_PROPERTY] = True
    # A 0.5 span gives 128 px/m at Desktop size, below the minimum: only the exemption passes it.
    collection = build_tiling_plane("Road", source, uv_span=0.5)
    _grid(collection.objects["SM_Road"])

    result = core.bake_asset("Road", "environment_piece", tmp_path / "out", budgets, "CPU", 4)
    assert result["texel_density"]["SM_Road"][0]["exempt"] == "trim_atlas"
    assert bool(bpy.data.materials["M_Road_Src"].get(TRIM_PROPERTY)) is True
    assert bool(bpy.data.materials["M_Road_Src_Authoring"].get(TRIM_PROPERTY)) is True

    mobile.build_mobile("Road", MOBILE_BUDGET)
    assert bool(bpy.data.materials["M_Road_Src_Mobile"].get(TRIM_PROPERTY)) is True

    report = contract.validate_asset("Road", "environment_piece", None)
    assert [item for item in report["findings"] if item["rule"] == "texel.density"] == []
    mobile_entries = [
        entry
        for item in report["snapshot"].values()
        if item["variant"] == "mobile"
        for entry in item.get("texel", [])
    ]
    assert mobile_entries
    assert all(entry.get("exempt") == "trim_atlas" for entry in mobile_entries)
