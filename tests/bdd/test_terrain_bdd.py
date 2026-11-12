# ruff: noqa: E501  -- step decorators repeat the Gherkin text verbatim, so they run long.
"""pytest-bdd bindings for terrain.feature: SCN001-SCN008 of #154.

The bindings run in plain CPython. They use the pure-Python heightfield core (loaded by path), the
fake Unreal editor and scaffold fakes, the Unreal import code, and the contract rule catalogue
(loaded by path). Three behaviours need the live Blender validator and exporter: the validator
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

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.unreal.terrain import (
    build_terrain_code,
    import_terrain_variant,
    landscape_transform,
)
from tests.unit.design.terrain_fakes import PLANE
from tests.unit.design.test_scaffold import (
    HARBOR,
    HILLS,
    HILLS_LEVEL,
    REGION,
    SYSTEM,
    FakeUnrealClient,
    _project,
    _run,
    _run_region,
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
REGION_LEVEL = "/Game/Levels/OldTown/L_OldTown"
GROUND_DESKTOP = "/Game/Terrain/Ground/Desktop"


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


def _sidecar(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "heightmap_px": 127,
        "spacing_m": 1.0,
        "height_min_m": 0.0,
        "height_max_m": 5.0,
        "uv_tile_m": 3.0,
        "layers": ["Grass", "Rock"],
        "samples": [[0.0, 0.0, 0.0], [10.0, 10.0, 5.0]],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# SCN001: a valid grid passes the terrain contract (headless Blender)
# ---------------------------------------------------------------------------


@scenario(FEATURE, "A valid terrain grid passes the terrain contract")
def test_scn001_valid_terrain_passes() -> None:
    pass


@given("a collection with one centered 1 m grid mesh at a valid Landscape resolution")
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
    "each variant folder holds T_<Name>_Height.png, one weightmap per layer, and each layer's BC, N, and ORM textures"
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
# SCN004: Unreal import builds a Landscape level per variant
# ---------------------------------------------------------------------------


@scenario(FEATURE, "Unreal import builds a Landscape level per variant")
def test_scn004_unreal_import_builds_the_landscape() -> None:
    pass


class _HeightMismatchClient:
    """Returns the NMG_RESULT that the generated code prints when a sample is 6 cm off."""

    def execute_python_code(self, code: str, *, timeout: float | None = None) -> str:
        return 'NMG_RESULT {"ok": false, "error": "terrain_height_mismatch", "height_errors_cm": [6.0]}'


@given("exported Desktop and Mobile terrain variants")
def _scn004_exported(state: dict[str, Any]) -> None:
    state["sidecar"] = _sidecar()


@when("the import_ue step runs")
def _scn004_run(state: dict[str, Any]) -> None:
    state["code"] = build_terrain_code(
        "Terrain/Ground/Desktop", GROUND_DESKTOP, "Ground", state["sidecar"]
    )


@then(
    "each variant gets M_<Name>_Landscape, one layer info per layer, and the level L_<Name> with a Landscape at the derived transform"
)
def _scn004_landscape(state: dict[str, Any]) -> None:
    code = state["code"]
    # The generated code takes its names from an embedded PARAMS object and builds the M_, LI_, and
    # L_ names from them, so the parameters are checked here and the template patterns below.
    match = re.search(r'PARAMS = json\.loads\((".*")\)', code)
    assert match is not None, "the generated code embeds no PARAMS"
    params = json.loads(json.loads(match.group(1)))
    assert params["name"] == "Ground"
    assert params["dest"] == GROUND_DESKTOP
    assert params["layers"] == ["Grass", "Rock"]
    assert '"M_" + NAME + "_Landscape"' in code
    assert '"LI_" + NAME + "_" + layer' in code
    assert "LevelEditorSubsystem" in code or "new_level" in code
    transform = landscape_transform(127, 1.0, 0.0, 5.0)
    assert transform["scale"][2] == pytest.approx(5.0 * 100 * 128 / 65535)


@then(
    "a sampled height more than 5 cm from the Blender height fails with import_ue.terrain_height_mismatch"
)
def _scn004_mismatch(state: dict[str, Any]) -> None:
    with pytest.raises(PipelineError) as info:
        import_terrain_variant(
            _HeightMismatchClient(),
            variant_dir="Terrain/Ground/Desktop",
            dest=GROUND_DESKTOP,
            name="Ground",
            sidecar_variant=state["sidecar"],
        )
    assert info.value.code == "import_ue.terrain_height_mismatch"


# ---------------------------------------------------------------------------
# SCN005 and SCN006: the region scaffold streams a terrain or keeps the plane
# ---------------------------------------------------------------------------


@scenario(FEATURE, "A region with an imported terrain streams it instead of a plane")
def test_scn005_region_streams_the_terrain() -> None:
    pass


@scenario(FEATURE, "A region without an imported terrain keeps the flat plane")
def test_scn006_region_keeps_the_plane() -> None:
    pass


@given("a region entry whose terrain names an imported terrain entry")
def _scn005_given(state: dict[str, Any], tmp_path: Path) -> None:
    state["fake"], state["result"] = _run_region(_terrain_project(tmp_path), existing={HILLS_LEVEL})


@given("a region entry without terrain, or whose terrain level does not exist yet")
def _scn006_given(state: dict[str, Any], tmp_path: Path) -> None:
    state["fake"], state["result"] = _run_region(_terrain_project(tmp_path), existing=())


@when("scaffold creates the region level")
def _scn_scaffold(state: dict[str, Any]) -> None:
    assert state["result"]["ok"] is True


@then("the level streams the terrain's Desktop level and has no ground plane")
def _scn005_streams(state: dict[str, Any]) -> None:
    calls = state["fake"].calls
    assert ("add_level_to_world", REGION_LEVEL, HILLS_LEVEL, "LevelStreamingAlwaysLoaded") in calls
    assert ("load_asset", PLANE) not in calls


@then("the level has the flat ground plane")
def _scn006_plane(state: dict[str, Any]) -> None:
    calls = state["fake"].calls
    assert ("load_asset", PLANE) in calls
    assert not any(call[0] == "add_level_to_world" for call in calls)


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


@then("finalize exports nothing and creates no Unreal asset")
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
    state["report"] = _run(root, FakeUnrealClient())


@when("the design docs are synced or scaffolded")
def _scn008_scaffold(state: dict[str, Any]) -> None:
    assert state["report"] is not None


@then("the run reports design.unknown_reference for the terrain field")
def _scn008_reports(state: dict[str, Any]) -> None:
    assert state["report"].failed is True
    assert UNKNOWN_REFERENCE in _texts(state["report"])
