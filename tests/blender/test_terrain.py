"""Terrain contract validation under Blender headless: AC1, AC6, SCN001, SCN007 (#154).

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped. Each fixture
is a grid built in code, so no .blend file is needed.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .contract_fixtures import clear_scene  # noqa: E402
from .terrain_fixtures import build_terrain, bump_at  # noqa: E402

AC6_RULES: dict[str, dict[str, Any]] = {
    "terrain.structure": {"extra_object": True},
    "terrain.resolution_invalid": {"n": 100},
    "terrain.spacing": {"spacing": 2.0},
    "terrain.not_centered": {"offset_x": 1.0},
    "terrain.layer_missing": {"layers": {}},
    "terrain.layer_range": {"spike": ("Rock", 1.5)},
    "terrain.over_budget": {
        "layers": {"Grass": 0.2, "Rock": 0.2, "Sand": 0.2, "Snow": 0.2, "Mud": 0.2},
        "texture_px": 512,
        "tile_m": 1.5,
    },
    "terrain.layer_texture_missing": {"textures": False},
}


@pytest.fixture(autouse=True)
def _isolated_scene() -> Iterator[None]:
    yield
    clear_scene()


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core")


def _rules(report: dict[str, Any]) -> set[str]:
    return {item["rule"] for item in report["findings"]}


def _assert_fails_with(report: dict[str, Any], rule: str) -> None:
    assert not report["passed"], f"expected {rule} to fail the terrain"
    assert rule in _rules(report), f"expected {rule}, got {sorted(_rules(report))}"
    matches = [item for item in report["findings"] if item["rule"] == rule]
    assert all(item["target"] and item["message"] and item["remediation"] for item in matches)
    assert "terrain" not in report, "a failing terrain carries no terrain object"


# ---------------------------------------------------------------------------
# AC1 / SCN001: a valid 127 grid with two layers and tiling materials passes
# ---------------------------------------------------------------------------


def test_ac1_valid_terrain_passes_and_reports_the_terrain_object(core: Any) -> None:
    build_terrain()
    report = core.validate_asset("Ground", "terrain")

    assert report["kind"] == "contract"
    assert report["class"] == "terrain"
    assert report["passed"], report["findings"]
    assert report["findings"] == []
    assert "SM_Ground" in report["snapshot"]

    terrain = report["terrain"]
    desktop, mobile = terrain["desktop"], terrain["mobile"]
    assert desktop["heightmap_px"] == 127
    assert desktop["spacing_m"] == pytest.approx(1.0)
    assert desktop["height_min_m"] == pytest.approx(0.0)
    assert desktop["height_max_m"] == pytest.approx(0.0)
    assert desktop["layers"] == ["Grass", "Rock"]
    assert mobile["heightmap_px"] == 127
    assert mobile["spacing_m"] == pytest.approx(1.0)
    assert mobile["layers"] == ["Grass", "Rock"]


def test_ac1_texel_density_is_per_layer_and_meets_both_minimums(core: Any) -> None:
    """1024 px textures tiled every 3 m give 1024 / 3 = 341.3 px/m, above 256 and 128."""
    build_terrain()
    terrain = core.validate_asset("Ground", "terrain")["terrain"]
    for variant in ("desktop", "mobile"):
        density = terrain[variant]["texel_density"]
        assert set(density) == {"Grass", "Rock"}
        assert density["Grass"] == pytest.approx(1024 / 3, rel=1e-3)
        assert density["Rock"] == pytest.approx(1024 / 3, rel=1e-3)
    assert terrain["desktop"]["texel_density"]["Grass"] >= 256
    assert terrain["mobile"]["texel_density"]["Grass"] >= 128


def test_ac1_mobile_values_come_from_the_planned_downsample(core: Any, tmp_path: Path) -> None:
    """A 253 grid with four layers and a Mobile override of 127 px and 3 layers.

    The stride-2 Mobile heightmap is 127 at 2 m spacing, keeps the three heaviest layers (the
    lightest, Snow, is dropped), and its height range comes from the samples it keeps. The
    single raised sample sits at an odd column and row, so the Desktop maximum is 5 m but the
    Mobile maximum is 0 m.
    """
    build_terrain(
        "Ground",
        253,
        layers={"Grass": 1.0, "Rock": 0.5, "Sand": 0.25, "Snow": 0.1},
        tile_m=1.5,
        texture_px=512,
        height_at=lambda x, y: bump_at(x, y, at_x=-125.0, at_y=125.0, height=5.0),
    )
    budgets = tmp_path / "nmg-budgets.json"
    budgets.write_text(
        json.dumps({"terrain": {"heightmap_px": 127, "layers": 3}}), encoding="utf-8"
    )

    report = core.validate_asset("Ground", "terrain", str(budgets))

    assert report["passed"], report["findings"]
    desktop, mobile = report["terrain"]["desktop"], report["terrain"]["mobile"]
    assert desktop["heightmap_px"] == 253
    assert desktop["spacing_m"] == pytest.approx(1.0)
    assert desktop["height_max_m"] == pytest.approx(5.0)
    assert desktop["layers"] == ["Grass", "Rock", "Sand", "Snow"]
    assert mobile["heightmap_px"] == 127
    assert mobile["spacing_m"] == pytest.approx(2.0)
    assert mobile["height_max_m"] == pytest.approx(0.0)
    assert mobile["layers"] == ["Grass", "Rock", "Sand"]
    assert set(mobile["texel_density"]) == {"Grass", "Rock", "Sand"}


def test_ac1_authored_terrain_checks_only_the_material_mapping(core: Any) -> None:
    """Before the bake the layer materials have no texture images; that is allowed when authored."""
    build_terrain(textures=False)
    report = core.validate_asset("Ground", "terrain", authored=True)
    assert report["passed"], report["findings"]
    assert report["terrain"]["desktop"]["texel_density"] == {}


def test_ac1_authored_terrain_still_requires_the_material_mapping(core: Any) -> None:
    build_terrain(materials=False)
    report = core.validate_asset("Ground", "terrain", authored=True)
    _assert_fails_with(report, "terrain.layer_texture_missing")


def test_post_bake_terrain_needs_the_texture_set(core: Any) -> None:
    build_terrain(textures=False)
    report = core.validate_asset("Ground", "terrain")
    _assert_fails_with(report, "terrain.layer_texture_missing")
    assert any("T_Ground_Grass_BC" in item["message"] for item in report["findings"])


# ---------------------------------------------------------------------------
# AC6 / SCN007: one fixture per terrain rule fails with that rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule", list(AC6_RULES))
def test_ac6_each_terrain_rule_fails_with_its_rule(core: Any, rule: str) -> None:
    options = dict(AC6_RULES[rule])
    if "n" in options:
        n = options.pop("n")
        build_terrain("Ground", n, **options)
    elif "layers" in options:
        build_terrain("Ground", layers=options.pop("layers"), **options)
    else:
        build_terrain("Ground", **options)
    report = core.validate_asset("Ground", "terrain")
    _assert_fails_with(report, rule)


def test_ac6_layer_material_missing_names_the_layer(core: Any) -> None:
    build_terrain()
    bpy.data.materials["M_Ground_Rock"].name = "M_Ground_Stone"
    report = core.validate_asset("Ground", "terrain")
    _assert_fails_with(report, "terrain.layer_texture_missing")
    assert any(item["target"] == "Layer_Rock" for item in report["findings"])


def test_ac6_desktop_heightmap_override_is_honoured(core: Any, tmp_path: Path) -> None:
    """A Desktop override below the grid size is over budget, which the desktop object applies."""
    build_terrain("Ground", 253, layers={"Grass": 0.6, "Rock": 0.4}, tile_m=1.5, texture_px=512)
    budgets = tmp_path / "nmg-budgets.json"
    budgets.write_text(
        json.dumps({"terrain": {"desktop": {"heightmap_px": 127}}}), encoding="utf-8"
    )
    report = core.validate_asset("Ground", "terrain", str(budgets))
    _assert_fails_with(report, "terrain.over_budget")


def test_terrain_texel_density_below_the_desktop_minimum_fails(core: Any) -> None:
    build_terrain(texture_px=256)
    report = core.validate_asset("Ground", "terrain")
    _assert_fails_with(report, "texel.density")
    assert any(item["target"] == "Layer_Grass" for item in report["findings"])


def test_terrain_texture_over_the_desktop_maximum_is_over_budget(core: Any) -> None:
    build_terrain(texture_px=2100)
    report = core.validate_asset("Ground", "terrain")
    _assert_fails_with(report, "terrain.over_budget")
    assert any(item["target"] == "T_Ground_Grass_BC" for item in report["findings"])


# ---------------------------------------------------------------------------
# Scene unchanged and scene units still checked
# ---------------------------------------------------------------------------


def test_terrain_validation_leaves_the_scene_unchanged(core: Any) -> None:
    build_terrain()
    before = (
        sorted(obj.name for obj in bpy.data.objects),
        sorted(collection.name for collection in bpy.data.collections),
        sorted(attribute.name for attribute in bpy.data.meshes["SM_Ground"].attributes),
        len(bpy.data.meshes),
    )
    core.validate_asset("Ground", "terrain")
    after = (
        sorted(obj.name for obj in bpy.data.objects),
        sorted(collection.name for collection in bpy.data.collections),
        sorted(attribute.name for attribute in bpy.data.meshes["SM_Ground"].attributes),
        len(bpy.data.meshes),
    )
    assert after == before


def test_terrain_still_checks_scene_units(core: Any) -> None:
    build_terrain()
    units = bpy.context.scene.unit_settings
    original = units.scale_length
    try:
        units.scale_length = 2.0
        report = core.validate_asset("Ground", "terrain")
    finally:
        units.scale_length = original
    assert "scene.units" in _rules(report)


# ---------------------------------------------------------------------------
# T004: bake, variants, export, and re-import (AC2, AC3, AC6, FR10)
# ---------------------------------------------------------------------------


@pytest.fixture()
def steps(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.finalize_core.steps")


@pytest.fixture()
def heightfield(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.terrain_core.heightfield")


def _request(tmp_path: Path, budgets: Path | None = None) -> dict[str, Any]:
    return {
        "collection": "Ground",
        "category": "Terrain",
        "asset_class": "terrain",
        "export_root": str(tmp_path / "export"),
        "budgets_path": str(budgets) if budgets else None,
        "device": "CPU",
    }


def _variant_root(tmp_path: Path) -> Path:
    return tmp_path / "export" / "Terrain" / "Ground"


def test_ac2_export_writes_every_variant_file_and_the_sidecars(
    steps: Any, heightfield: Any, tmp_path: Path
) -> None:
    build_terrain("Ground", 127, layers={"Grass": 0.6, "Rock": 0.4}, tile_m=3.0, texture_px=1024)
    request = _request(tmp_path)
    job = tmp_path / "job"

    variants = steps.run_step("variants", request, job)
    assert variants["ok"], variants["error"]
    exported = steps.run_step("export", request, job)
    assert exported["ok"], exported["error"]
    assert exported["outputs"]["exported"] is True

    root = _variant_root(tmp_path)
    for variant in ("Desktop", "Mobile"):
        folder = root / variant
        assert (folder / "T_Ground_Height.png").is_file()
        for layer in ("Grass", "Rock"):
            assert (folder / f"T_Ground_Layer_{layer}.png").is_file()
            for suffix in ("BC", "N", "ORM"):
                assert (folder / f"T_Ground_{layer}_{suffix}.png").is_file()

    height = heightfield.read_png_gray(root / "Desktop" / "T_Ground_Height.png")
    assert (height.bit_depth, height.width, height.height) == (16, 127, 127)
    weights = [
        heightfield.read_png_gray(root / "Desktop" / f"T_Ground_Layer_{layer}.png").samples
        for layer in ("Grass", "Rock")
    ]
    assert all(sum(pixel) == 255 for pixel in zip(*weights, strict=True))

    sidecar = json.loads((root / "nmg-variants.json").read_text(encoding="utf-8"))
    assert sidecar["terrain"] is True
    assert sidecar["class"] == "terrain"
    assert sidecar["desktop"]["heightmap_px"] == 127
    assert sidecar["desktop"]["layers"] == ["Grass", "Rock"]
    assert len(sidecar["desktop"]["samples"]) == 11
    asset = json.loads((root / "Mobile" / "nmg-asset.json").read_text(encoding="utf-8"))
    assert asset == {"class": "terrain", "heightmap_px": 127, "layers": 2, "max_texture_px": 1024}


def test_ac3_mobile_takes_every_second_sample_and_drops_the_lightest_layer(
    steps: Any, heightfield: Any, tmp_path: Path
) -> None:
    build_terrain(
        "Ground",
        253,
        layers={"Grass": 1.0, "Rock": 0.5, "Sand": 0.25, "Snow": 0.1},
        tile_m=1.5,
        texture_px=512,
        height_at=lambda x, y: bump_at(x, y, at_x=-125.0, at_y=125.0, height=5.0),
    )
    budgets = tmp_path / "nmg-budgets.json"
    budgets.write_text(
        json.dumps({"terrain": {"heightmap_px": 127, "layers": 3}}), encoding="utf-8"
    )
    request = _request(tmp_path, budgets)
    job = tmp_path / "job"

    assert steps.run_step("variants", request, job)["ok"]
    exported = steps.run_step("export", request, job)
    assert exported["ok"], exported["error"]

    root = _variant_root(tmp_path)
    sidecar = json.loads((root / "nmg-variants.json").read_text(encoding="utf-8"))
    assert sidecar["mobile"]["heightmap_px"] == 127
    assert sidecar["mobile"]["spacing_m"] == pytest.approx(2.0)
    assert sidecar["mobile"]["layers"] == ["Grass", "Rock", "Sand"]
    assert sidecar["mobile"]["height_max_m"] == pytest.approx(0.0)
    assert sidecar["desktop"]["height_max_m"] == pytest.approx(5.0)
    mobile = root / "Mobile"
    assert not (mobile / "T_Ground_Layer_Snow.png").exists()
    assert not (mobile / "T_Ground_Snow_BC.png").exists()
    mobile_height = heightfield.read_png_gray(mobile / "T_Ground_Height.png")
    assert (mobile_height.width, mobile_height.height) == (127, 127)
    weights = [
        heightfield.read_png_gray(mobile / f"T_Ground_Layer_{layer}.png").samples
        for layer in ("Grass", "Rock", "Sand")
    ]
    assert all(sum(pixel) == 255 for pixel in zip(*weights, strict=True))


def test_ac6_a_failing_contract_exports_nothing(steps: Any, tmp_path: Path) -> None:
    build_terrain(extra_object=True)
    request = _request(tmp_path)
    job = tmp_path / "job"

    exported = steps.run_step("export", request, job)

    assert exported["ok"]
    assert exported["outputs"]["exported"] is False
    assert "nothing exported" in exported["summary"]
    assert not (_variant_root(tmp_path) / "nmg-variants.json").exists()
    assert not (_variant_root(tmp_path) / "Desktop" / "T_Ground_Height.png").exists()


def test_fr10_reimport_passes_a_clean_export_and_catches_a_tampered_heightmap(
    steps: Any, heightfield: Any, enabled_addon: str, tmp_path: Path
) -> None:
    reimport = importlib.import_module(f"{enabled_addon}.terrain_core.reimport")
    build_terrain("Ground", 127, height_at=lambda x, y: x * 0.1)
    request = _request(tmp_path)
    job = tmp_path / "job"
    assert steps.run_step("variants", request, job)["ok"]
    exported = steps.run_step("export", request, job)
    assert exported["ok"], exported["error"]
    desktop = exported["outputs"]["variants"]["Desktop"]
    mobile = exported["outputs"]["variants"]["Mobile"]

    for spec in (desktop, mobile):
        clean = reimport.terrain_reimport_check(spec["dir"], spec["pre_report"])
        assert clean["passed"], clean["findings"]
        assert clean["kind"] == "reimport"

    # Zero every Desktop height code: the decoded heightmap is flat at the minimum height.
    height_path = Path(desktop["dir"]) / "T_Ground_Height.png"
    heightfield.write_png_gray16(bytes(2 * 127 * 127), 127, 127, height_path)
    tampered = reimport.terrain_reimport_check(desktop["dir"], desktop["pre_report"])
    assert not tampered["passed"]
    assert {item["rule"] for item in tampered["findings"]} == {"reimport.terrain"}
    assert any("heights" in item["message"] for item in tampered["findings"])
    untouched = reimport.terrain_reimport_check(mobile["dir"], mobile["pre_report"])
    assert untouched["passed"], untouched["findings"]


def test_t004_bake_refuses_more_layers_than_the_desktop_material_limit(
    steps: Any, tmp_path: Path
) -> None:
    """Five layers exceed the Desktop limit of four. The bake stops before any render."""
    build_terrain(
        "Ground",
        127,
        layers={"Grass": 0.2, "Rock": 0.2, "Sand": 0.2, "Snow": 0.2, "Mud": 0.2},
        tile_m=1.5,
        texture_px=512,
    )
    bake = steps.run_step("bake", _request(tmp_path), tmp_path / "job")

    assert not bake["ok"]
    assert bake["error"]["code"] == "bake.texture.bake_failed"
    assert "5 tiling materials" in bake["error"]["message"]
    assert "limit is 4" in bake["error"]["message"]
