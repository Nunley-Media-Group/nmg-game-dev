# ruff: noqa: E501  -- step decorators repeat the Gherkin text verbatim, so they run long.
"""pytest-bdd bindings for terrain.feature: SCN001-SCN008 of #154, on Godot (#249).

The bindings run in plain CPython. They use the pure-Python heightfield core (loaded by path), the
finalize fakes (``TerrainStepRunner`` and ``FinalizeGodot``) with the real terrain import, the
scaffold helpers, and the contract rule catalogue (loaded by path). Three behaviours need the live Blender validator and exporter: the validator
report (SCN001), the export files and sidecars (SCN002), and the per-rule findings (SCN007). The
headless suite tests/blender/test_terrain.py, run by gate-blender-headless, owns those. Their
bindings check that the owning test exists rather than running Blender here.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.godot.terrain import SHADER_PATH, decode_heights, parse_variant
from nmg_game_dev.pipeline import FinalizeClients, FinalizeRequest, finalize
from nmg_game_dev.pipeline.errors import PipelineError
from tests.finalize_fakes import FinalizeGodot, TerrainStepRunner
from tests.unit.design.test_scaffold import (
    HARBOR,
    HILLS,
    HILLS_SCENE,
    REGION,
    SYSTEM,
    _project,
    _run,
    _set_terrain,
    _terrain_project,
    _texts,
)

FEATURE = "terrain.feature"
REPO_ROOT = Path(__file__).resolve().parents[2]
ADDON = REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon"
BLENDER_SUITE = (REPO_ROOT / "tests" / "blender" / "test_terrain.py").read_text(encoding="utf-8")
ALL_RULES = (
    "terrain.resolution_invalid",
    "terrain.spacing",
    "terrain.not_centered",
    "terrain.structure",
    "terrain.layer_missing",
    "terrain.layer_range",
    "terrain.over_budget",
    "terrain.layer_texture_missing",
)
UNKNOWN_REFERENCE = (
    "error design.unknown_reference OldTown: "
    "terrain 'Ghost' names no environment entry with asset_class terrain"
)
REGION_SCENE = "game/levels/OldTown/OldTown.tscn"


def _load_by_path(name: str, path: Path) -> ModuleType:
    """Load a file of the add-on as a standalone module, as the unit suite does."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def heightfield() -> ModuleType:
    return _load_by_path("nmg_terrain_heightfield_bdd", ADDON / "terrain_core" / "heightfield.py")


@pytest.fixture(scope="module")
def rule_catalogue() -> dict[str, str]:
    report = _load_by_path("nmg_contract_report_bdd", ADDON / "contract_core" / "report.py")
    return dict(report.RULES)


@pytest.fixture()
def state() -> dict[str, Any]:
    return {}


def _owned_by_blender_suite(test_name: str) -> None:
    assert f"def {test_name}(" in BLENDER_SUITE, f"the headless suite lacks {test_name}"


def _terrain_request(root: Path) -> FinalizeRequest:
    blend = root / "ground.blend"
    blend.write_bytes(b"authored")
    return FinalizeRequest(
        collection="Ground",
        category="Terrain",
        asset_class="terrain",
        export_root=root / "export",
        blend=blend,
    )


def _import_terrain(root: Path, godot: FinalizeGodot) -> Any:
    request = _terrain_request(root)
    return finalize(
        request,
        steps=("import_godot",),
        cache_dir=root / "cache",
        runner=TerrainStepRunner(request),
        job_dir=root / "job",
        clients=FinalizeClients(godot=godot),
    )


# ---------------------------------------------------------------------------
# SCN001: a valid grid passes the terrain contract (headless Blender)
# ---------------------------------------------------------------------------


@scenario(FEATURE, "A valid terrain grid passes the terrain contract")
def test_scn001_valid_terrain_passes() -> None:
    pass


@given("a collection with one centered 1 m grid mesh at a valid terrain resolution")
def _scn001_grid(state: dict[str, Any]) -> None:
    state["resolution"] = 127


@given("two Layer attributes, each with a matching tiling material")
def _scn001_layers(state: dict[str, Any]) -> None:
    state["layers"] = ("Grass", "Rock")


@when("the contract validator runs with class terrain")
def _scn001_validate(state: dict[str, Any]) -> None:
    state["owner"] = "test_ac1_valid_terrain_passes_and_reports_the_terrain_object"


@then("the report passes")
def _scn001_passes(state: dict[str, Any]) -> None:
    _owned_by_blender_suite(state["owner"])


@then("it records resolution, height range, layers, and texel density for Desktop and Mobile")
def _scn001_records(state: dict[str, Any]) -> None:
    _owned_by_blender_suite("test_ac1_texel_density_is_per_layer_and_meets_both_minimums")


# ---------------------------------------------------------------------------
# SCN002: finalize exports heightmaps, weightmaps, and layer textures
# ---------------------------------------------------------------------------


@scenario(FEATURE, "Finalize exports heightmaps, weightmaps, and layer textures")
def test_scn002_finalize_exports_the_variant_files() -> None:
    pass


@given("a terrain collection that passes validation")
def _scn002_valid(state: dict[str, Any]) -> None:
    state["grid"] = 4


@when("finalize exports it")
def _scn002_export(state: dict[str, Any], heightfield: ModuleType, tmp_path: Path) -> None:
    """Run the pure export core: encode the heights, quantize two weight layers, write and read PNGs."""
    n = state["grid"]
    cells = range(n * n)
    heights = [0.5 * (cell // n + cell % n) for cell in cells]
    height_bytes, zmin, zmax = heightfield.encode_heights(heights, n)
    heightfield.write_png_gray16(height_bytes, n, n, tmp_path / "T_Ground_Height.png")
    grass = [1.0 if (cell // n + cell % n) % 2 == 0 else 0.25 for cell in cells]
    rock = [1.0 - value for value in grass]
    codes = heightfield.quantize_weights(heightfield.normalize_weights([grass, rock]))
    for layer, data in zip(("Grass", "Rock"), codes, strict=True):
        heightfield.write_png_gray8(data, n, n, tmp_path / f"T_Ground_Layer_{layer}.png")
    state.update(zmin=zmin, zmax=zmax, heights=heights, tmp=tmp_path, codes=codes)


@then(
    "each variant folder holds T_<Name>_Height.png, <Name>_Chunk_<r>_<c>.glb chunks, T_<Name>_Splat.png, and each layer's BC, N, and ORM textures"
)
def _scn002_files(state: dict[str, Any], heightfield: ModuleType) -> None:
    _owned_by_blender_suite("test_ac2_export_writes_every_variant_file_and_the_sidecars")
    height = heightfield.read_png_gray(state["tmp"] / "T_Ground_Height.png")
    assert (height.bit_depth, height.width, height.height) == (16, state["grid"], state["grid"])


@then("every weightmap pixel set sums to 255")
def _scn002_sums(state: dict[str, Any]) -> None:
    assert all(sum(pixel) == 255 for pixel in zip(*state["codes"], strict=True))


@then(
    "nmg-variants.json records terrain true with each variant's resolution, height range, and layers"
)
def _scn002_sidecar(state: dict[str, Any], heightfield: ModuleType) -> None:
    _owned_by_blender_suite("test_ac2_export_writes_every_variant_file_and_the_sidecars")
    decoded = heightfield.decode_heights(
        heightfield.read_png_gray(state["tmp"] / "T_Ground_Height.png").samples,
        state["grid"],
        state["zmin"],
        state["zmax"],
    )
    assert max(abs(a - b) for a, b in zip(decoded, state["heights"], strict=True)) <= 0.05


# ---------------------------------------------------------------------------
# SCN003: the Mobile terrain fits the Mobile budget
# ---------------------------------------------------------------------------


@scenario(FEATURE, "The Mobile terrain fits the Mobile budget")
def test_scn003_mobile_fits_the_budget() -> None:
    pass


@given("a Desktop terrain at 2017 with 4 layers")
def _scn003_desktop(state: dict[str, Any]) -> None:
    state["desktop"] = 2017


@when("the Mobile variant is built")
def _scn003_build(state: dict[str, Any], heightfield: ModuleType) -> None:
    size, stride = heightfield.mobile_size(state["desktop"], 1009)
    state["size"], state["stride"] = size, stride
    # Two weight pixels across four layers. The layer totals are 1.0, 0.6, 0.3, and 0.1.
    weights = [[0.5, 0.5], [0.3, 0.3], [0.15, 0.15], [0.05, 0.05]]
    state["kept"], state["reduced"] = heightfield.reduce_layers(weights, 3)


@then("its heightmap is 1009 at 2 m spacing over the same extent")
def _scn003_size(state: dict[str, Any]) -> None:
    assert (state["size"], state["stride"]) == (1009, 2)
    spacing = 1.0 * state["stride"]
    assert (state["size"] - 1) * spacing == (state["desktop"] - 1) * 1.0
    assert spacing == 2.0


@then("it keeps 3 layers, with the lowest-weight layer renormalized into the rest")
def _scn003_layers(state: dict[str, Any]) -> None:
    assert state["kept"] == (0, 1, 2)
    for pixel in zip(*state["reduced"], strict=True):
        assert sum(pixel) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# SCN004: Godot import builds a terrain scene per variant
# ---------------------------------------------------------------------------


@scenario(FEATURE, "Godot import builds a terrain scene per variant")
def test_scn004_godot_import_builds_the_terrain_scene() -> None:
    pass


@given("exported Desktop and Mobile terrain variants")
def _scn004_exported(state: dict[str, Any], tmp_path: Path) -> None:
    state["root"] = tmp_path


@when("the import_godot step runs")
def _scn004_run(state: dict[str, Any]) -> None:
    godot = FinalizeGodot(state["root"])
    state["result"] = _import_terrain(state["root"], godot)
    state["godot"] = godot


@then(
    "each variant gets <Name>.tscn instancing every chunk with the terrain shader and a HeightMapShape3D built from the heightfield"
)
def _scn004_scene(state: dict[str, Any]) -> None:
    root: Path = state["root"]
    folder_root = root / "export" / "Terrain" / "Ground"
    sidecar = json.loads((folder_root / "nmg-variants.json").read_text(encoding="utf-8"))
    for variant in ("Desktop", "Mobile"):
        folder = folder_root / variant
        text = (folder / "Ground.tscn").read_text(encoding="utf-8")
        terrain = parse_variant(sidecar, variant)
        side = terrain.chunks_per_side
        assert text.startswith("[gd_scene ")
        assert '[node name="Ground" type="Node3D"]' in text
        for row in range(side):
            for col in range(side):
                assert f'instance=ExtResource("chunk_Ground_Chunk_{row}_{col}")' in text
        assert f'path="{SHADER_PATH}"' in text
        assert "T_Ground_Splat.png" in text
        assert f"map_width = {terrain.heightmap_px}" in text
        assert f"map_depth = {terrain.heightmap_px}" in text
        match = re.search(r"map_data = PackedFloat32Array\(([^)]*)\)", text)
        assert match is not None
        values = [float(item) for item in match.group(1).split(",")]
        heights = decode_heights(folder / "T_Ground_Height.png", terrain)
        assert max(abs(a - b) for a, b in zip(values, heights, strict=True)) < 1e-3
        assert '[node name="HeightMap" type="CollisionShape3D" parent="Collision"]' in text
    resources = state["result"]
    assert resources.desktop_resource_path == "res://export/Terrain/Ground/Desktop/Ground.tscn"
    assert state["godot"].count("--import") == 1


@then(
    "a probed height range more than 5 cm from the heightfield fails with import_godot.terrain_height_mismatch"
)
def _scn004_mismatch(state: dict[str, Any], tmp_path: Path) -> None:
    root = tmp_path / "mismatch"
    with pytest.raises(PipelineError) as info:
        _import_terrain(root, FinalizeGodot(root, mesh_range=(10.0, 40.06)))
    assert info.value.code == "import_godot.terrain_height_mismatch"
    assert info.value.remediation


# ---------------------------------------------------------------------------
# SCN005 and SCN006: the region scaffold instances a terrain or keeps the plane
# ---------------------------------------------------------------------------


@scenario(FEATURE, "A region with an imported terrain instances it instead of a plane")
def test_scn005_region_instances_the_terrain() -> None:
    pass


@scenario(FEATURE, "A region without an imported terrain keeps the flat plane")
def test_scn006_region_keeps_the_plane() -> None:
    pass


@given("a region entry whose terrain names an imported terrain entry")
def _scn005_given(state: dict[str, Any], tmp_path: Path) -> None:
    root = _terrain_project(tmp_path)
    scene = root / HILLS_SCENE
    scene.parent.mkdir(parents=True)
    scene.write_text("[gd_scene format=3]\n", encoding="utf-8")
    state["root"] = root


@given("a region entry without terrain, or whose terrain scene does not exist yet")
def _scn006_given(state: dict[str, Any], tmp_path: Path) -> None:
    state["root"] = _terrain_project(tmp_path)


@when("scaffold creates the region level")
def _scn_scaffold(state: dict[str, Any]) -> None:
    report = _run(state["root"])
    assert report.failed is False
    state["text"] = (state["root"] / REGION_SCENE).read_text(encoding="utf-8")


@then("the level loads the terrain's platform variant and has no ground plane")
def _scn005_instances(state: dict[str, Any]) -> None:
    text = state["text"]
    # Variant-free: NmgVariantScene resolves Desktop/ or Mobile/ at run time (#249 review F2).
    assert 'path="res://addons/nmg_game_dev/nmg_variant_scene.gd"' in text
    assert '[node name="Hills" type="Node3D" parent="."]' in text
    assert 'scene_path = "res://assets/Terrain/Hills/Hills.tscn"' in text
    assert "/Desktop/" not in text and "/Mobile/" not in text
    assert "PlaneMesh" not in text


@then("the level has the flat ground plane")
def _scn006_plane(state: dict[str, Any]) -> None:
    text = state["text"]
    assert "PlaneMesh" in text
    assert "ext_resource" not in text


# ---------------------------------------------------------------------------
# SCN007: out-of-contract terrain fails with a named finding
# ---------------------------------------------------------------------------


@scenario(FEATURE, "Out-of-contract terrain fails with a named finding")
def test_scn007_out_of_contract_terrain() -> None:
    pass


@given(parsers.parse("a terrain collection that breaks the {rule} rule"))
def _scn007_breaks(state: dict[str, Any], rule: str) -> None:
    state["rule"] = rule


@when("validation runs")
def _scn007_validate(state: dict[str, Any]) -> None:
    state["owner"] = f'"{state["rule"]}"'


@then(parsers.parse("the report fails with {rule} and a remediation"))
def _scn007_fails(state: dict[str, Any], rule: str, rule_catalogue: dict[str, str]) -> None:
    assert rule in ALL_RULES
    assert rule_catalogue[rule].strip(), f"{rule} has no remediation"
    assert state["owner"] in BLENDER_SUITE, f"the headless suite does not cover {rule}"


@then("finalize exports nothing and imports nothing into Godot")
def _scn007_exports_nothing() -> None:
    _owned_by_blender_suite("test_ac6_a_failing_contract_exports_nothing")


# ---------------------------------------------------------------------------
# SCN008: a region naming no terrain entry is an unknown reference
# ---------------------------------------------------------------------------


@scenario(FEATURE, "A region naming no terrain entry is an unknown reference")
def test_scn008_unknown_reference() -> None:
    pass


@given("a region entry whose terrain names no environment entry with asset_class terrain")
def _scn008_given(state: dict[str, Any], tmp_path: Path) -> None:
    root = _project(
        tmp_path,
        {
            "regions/old-town.md": REGION,
            "regions/harbor.md": HARBOR,
            "environment/hills.md": HILLS,
            "systems/inventory.md": SYSTEM,
        },
    )
    _set_terrain(root, "OldTown", "Ghost")
    state["report"] = _run(root)


@when("the design docs are synced or scaffolded")
def _scn008_scaffold(state: dict[str, Any]) -> None:
    assert state["report"] is not None


@then("the run reports design.unknown_reference for the terrain field")
def _scn008_reports(state: dict[str, Any]) -> None:
    assert state["report"].failed is True
    assert UNKNOWN_REFERENCE in _texts(state["report"])
