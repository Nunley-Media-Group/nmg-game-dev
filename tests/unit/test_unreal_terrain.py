"""Terrain UE import: the generated code run against the fake ``unreal``, the host math, and errors.

``build_terrain_code`` output runs here against ``tests/unit/fake_unreal.py``, with a fake
``NmgLandscapeLibrary``. The tests check call order and arguments (including the transform and the
mapping scale), that Height and Layer PNGs are never imported as textures, that an existing level
is replaced, that the previous level is restored after a failure, and that a 6 cm height error is
``import_ue.terrain_height_mismatch`` (AC4, FR6). Host round-trip math is checked against the
heightfield codec loaded by path (AC4). The editor itself never runs.
"""

from __future__ import annotations

import importlib.util
import json
import random
import struct
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.unreal import parse_nmg_result
from nmg_game_dev.unreal.terrain import (
    build_terrain_code,
    import_terrain_variant,
    landscape_transform,
    ue_samples,
)
from tests.unit.fake_unreal import MAIN_MAP, FakeWorld, run_generated_code

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HEIGHTFIELD_PATH = (
    _REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon" / "terrain_core" / "heightfield.py"
)

NAME = "Hills"
CATEGORY = "Environment"
DESKTOP_DEST = f"/Game/{CATEGORY}/{NAME}/Desktop"
MOBILE_DEST = f"/Game/{CATEGORY}/{NAME}/Mobile"
LEVEL = f"{DESKTOP_DEST}/L_{NAME}"
LAYERS = ["Grass", "Rock"]
N = 127
SPACING_M = 2.0
UV_TILE_M = 8.0
ZMIN_M = 10.0
ZMAX_M = 40.0
_HALF_M = (N - 1) * SPACING_M / 2


def _samples() -> list[list[float]]:
    """Eleven Blender-space points: the corners, edge midpoints, centre, and extremes."""
    h = _HALF_M
    return [
        [-h, h, 10.0],
        [h, h, 40.0],
        [-h, -h, 10.0],
        [h, -h, 25.0],
        [0.0, h, 12.5],
        [0.0, -h, 20.0],
        [-h, 0.0, 15.0],
        [h, 0.0, 30.0],
        [0.0, 0.0, 25.0],
        [-40.0, 30.0, 10.0],
        [50.0, -20.0, 40.0],
    ]


def _sidecar(**overrides: Any) -> dict[str, Any]:
    """One variant's entry from nmg-variants.json, as the export writes it."""
    entry: dict[str, Any] = {
        "heightmap": f"Desktop/T_{NAME}_Height.png",
        "heightmap_px": N,
        "spacing_m": SPACING_M,
        "height_min_m": ZMIN_M,
        "height_max_m": ZMAX_M,
        "uv_tile_m": UV_TILE_M,
        "layers": list(LAYERS),
        "max_texture_px": 2048,
        "texture_bytes": 4096,
        "samples": _samples(),
    }
    entry.update(overrides)
    return entry


def _write_variant(folder: Path, layers: list[str] | None = None) -> Path:
    """Write one variant's exported PNG set. The contents are placeholders the fake never reads."""
    folder.mkdir(parents=True, exist_ok=True)
    names = [f"T_{NAME}_Height.png"]
    for layer in layers if layers is not None else LAYERS:
        names.append(f"T_{NAME}_Layer_{layer}.png")
        names.extend(f"T_{NAME}_{layer}_{suffix}.png" for suffix in ("BC", "N", "ORM"))
    for name in names:
        (folder / name).write_bytes(b"png")
    return folder


class EditorClient:
    """An UnrealPythonClient that runs the UE code against the fake editor."""

    def __init__(self, editor: FakeWorld) -> None:
        self.editor = editor
        self.codes: list[str] = []

    def execute_python_code(self, code: str) -> str:
        self.codes.append(code)
        return run_generated_code(code, self.editor)


def _run(
    tmp_path: Path,
    editor: FakeWorld,
    *,
    dest: str = DESKTOP_DEST,
    sidecar: dict[str, Any] | None = None,
    variant_dir: Path | None = None,
) -> dict[str, Any]:
    """Run the generated code directly and return the parsed NMG_RESULT object."""
    folder = variant_dir if variant_dir is not None else _write_variant(tmp_path / "Desktop")
    code = build_terrain_code(str(folder), dest, NAME, sidecar or _sidecar())
    result: dict[str, Any] = parse_nmg_result(run_generated_code(code, editor))
    return result


def _truth_for(sidecar: dict[str, Any]) -> dict[tuple[float, float], float]:
    """The heights the fake editor samples: each sample point's recorded UE height."""
    return {(point[0], point[1]): point[2] for point in ue_samples(sidecar["samples"])}


def _editor(sidecar: dict[str, Any] | None = None) -> FakeWorld:
    editor = FakeWorld()
    editor.sampled_cm = _truth_for(sidecar or _sidecar())
    return editor


def _non_save_calls(editor: FakeWorld) -> list[str]:
    return [call for call in editor.calls if not call.startswith("save_asset:")]


# --- transform and conversion ---------------------------------------------------------------


def test_landscape_transform_follows_the_design_formulas() -> None:
    transform = landscape_transform(127, 2.0, 10.0, 40.0)

    # sx = spacing in cm; x = y = -(n - 1) / 2 * sx.
    assert transform["scale"][0] == pytest.approx(200.0)
    assert transform["scale"][1] == pytest.approx(200.0)
    assert transform["location"][0] == pytest.approx(-12600.0)
    assert transform["location"][1] == pytest.approx(-12600.0)
    # sz = (zmax - zmin) * 100 * 128 / 65535; z = zmin * 100 + 32768 * sz / 128.
    expected_sz = 30.0 * 100.0 * 128.0 / 65535.0
    assert transform["scale"][2] == pytest.approx(expected_sz)
    assert transform["location"][2] == pytest.approx(1000.0 + 32768.0 * expected_sz / 128.0)


def test_flat_terrain_keeps_z_scale_one_and_sits_at_zmin() -> None:
    transform = landscape_transform(9, 1.0, 3.0, 3.0)

    assert transform == {"location": [-400.0, -400.0, 300.0], "scale": [100.0, 100.0, 1.0]}


def test_landscape_transform_rejects_impossible_inputs() -> None:
    with pytest.raises(ValueError):
        landscape_transform(1, 1.0, 0.0, 1.0)
    with pytest.raises(ValueError):
        landscape_transform(127, 0.0, 0.0, 1.0)
    with pytest.raises(ValueError):
        landscape_transform(127, 1.0, 5.0, 4.0)


def test_ue_samples_converts_metres_to_centimetres_and_negates_y() -> None:
    assert ue_samples([[1.0, 2.0, 3.0], [-0.5, 0.0, 0.25]]) == [
        [100.0, -200.0, 300.0],
        [-50.0, 0.0, 25.0],
    ]


# --- round-trip math (AC4) ------------------------------------------------------------------


def _heightfield() -> ModuleType:
    spec = importlib.util.spec_from_file_location("nmg_heightfield_under_test", _HEIGHTFIELD_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _codes(bytes16: bytes, n: int) -> list[int]:
    """The 16-bit codes in a bytes16 grid: two big-endian bytes per sample, row-major."""
    return list(struct.unpack(f">{n * n}H", bytes16))


def _reproduced_height_m(code: int, transform: dict[str, list[float]]) -> float:
    """The height in metres that the Landscape shows for one code, from the derived transform."""
    _, _, location_z = transform["location"]
    scale_z = transform["scale"][2]
    return (location_z + (code - 32768) * scale_z / 128.0) / 100.0


def _assert_grid_reproduced(heights: list[float], n: int, spacing: float) -> None:
    heightfield = _heightfield()
    bytes16, zmin, zmax = heightfield.encode_heights(heights, n)
    transform = landscape_transform(n, spacing, zmin, zmax)
    codes = _codes(bytes16, n)
    half = (n - 1) * spacing / 2
    loc_x, loc_y, _ = transform["location"]
    sx, sy, _ = transform["scale"]
    for row in range(n):
        for col in range(n):
            index = row * n + col
            # The Landscape vertex sits where the Blender grid vertex sits, after the UE mapping.
            blender = [-half + col * spacing, half - row * spacing, heights[index]]
            expected_xy = ue_samples([blender])[0][:2]
            assert loc_x + col * sx == pytest.approx(expected_xy[0], abs=1e-6)
            assert loc_y + row * sy == pytest.approx(expected_xy[1], abs=1e-6)
            reproduced = _reproduced_height_m(codes[index], transform)
            assert abs(reproduced - heights[index]) <= 0.05, (row, col)


def test_flat_terrain_round_trips_within_5cm() -> None:
    _assert_grid_reproduced([3.5] * (N * N), N, SPACING_M)


def test_zero_to_500_metre_terrain_round_trips_within_5cm() -> None:
    rng = random.Random(154)
    heights = [rng.uniform(0.0, 500.0) for _ in range(N * N)]
    heights[0] = 0.0
    heights[-1] = 500.0

    _assert_grid_reproduced(heights, N, 1.0)


# --- build_terrain_code ---------------------------------------------------------------------


def test_generated_code_embeds_parameters_and_prints_one_result_line(tmp_path: Path) -> None:
    code = build_terrain_code(str(_write_variant(tmp_path)), DESKTOP_DEST, NAME, _sidecar())

    assert code.count('print("NMG_RESULT "') == 1
    assert "terrain_height_mismatch" in code
    compile(code, "<ue-terrain>", "exec")


def test_build_rejects_a_destination_that_is_not_a_variant(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Desktop or Mobile"):
        build_terrain_code(str(tmp_path), f"/Game/{CATEGORY}/{NAME}", NAME, _sidecar())


# --- the generated code against the fake unreal ---------------------------------------------


def test_call_order_and_arguments_build_the_landscape_level(tmp_path: Path) -> None:
    editor = _editor()

    result = _run(tmp_path, editor)

    assert result["ok"] is True, result
    assert _non_save_calls(editor) == [
        "import_asset_tasks",
        "build_layered_material",
        "create_layer_info:LI_Hills_Grass",
        "create_layer_info:LI_Hills_Rock",
        f"new_level:{LEVEL}",
        "import_landscape",
        "sample_heights",
        f"save_current_level:{LEVEL}",
        f"load_level:{MAIN_MAP}",
    ]


def test_material_gets_the_layer_textures_and_the_uv_mapping_scale(tmp_path: Path) -> None:
    editor = _editor()

    _run(tmp_path, editor)

    assert editor.material_args == {
        "dest": DESKTOP_DEST,
        "name": f"M_{NAME}_Landscape",
        "layers": LAYERS,
        "bc": [f"{DESKTOP_DEST}/T_{NAME}_{layer}_BC" for layer in LAYERS],
        "n": [f"{DESKTOP_DEST}/T_{NAME}_{layer}_N" for layer in LAYERS],
        "orm": [f"{DESKTOP_DEST}/T_{NAME}_{layer}_ORM" for layer in LAYERS],
        # uv_tile_m / spacing_m: 8 m tiles over 2 m quads.
        "mapping_scale": 4.0,
    }
    assert editor.layer_info_args == [
        {"dest": DESKTOP_DEST, "name": f"LI_{NAME}_{layer}", "layer": layer} for layer in LAYERS
    ]


def test_landscape_is_imported_at_the_derived_transform(tmp_path: Path) -> None:
    sidecar = _sidecar()
    editor = _editor(sidecar)
    folder = _write_variant(tmp_path / "Desktop")

    _run(tmp_path, editor, sidecar=sidecar, variant_dir=folder)

    transform = landscape_transform(N, SPACING_M, ZMIN_M, ZMAX_M)
    landscape = editor.landscape_args
    assert landscape["level"] == LEVEL
    assert landscape["heightmap"] == str(folder / f"T_{NAME}_Height.png")
    assert landscape["weightmaps"] == [
        str(folder / f"T_{NAME}_Layer_{layer}.png") for layer in LAYERS
    ]
    assert landscape["layer_infos"] == [f"{DESKTOP_DEST}/LI_{NAME}_{layer}" for layer in LAYERS]
    assert landscape["material"] == f"{DESKTOP_DEST}/M_{NAME}_Landscape"
    assert landscape["n"] == N
    assert landscape["location"] == pytest.approx(tuple(transform["location"]))
    assert landscape["scale"] == pytest.approx(tuple(transform["scale"]))


def test_height_and_layer_pngs_are_never_imported_as_textures(tmp_path: Path) -> None:
    editor = _editor()

    _run(tmp_path, editor)

    imported = sorted(Path(path).name for path in editor.import_files)
    assert imported == sorted(
        f"T_{NAME}_{layer}_{suffix}.png" for layer in LAYERS for suffix in ("BC", "N", "ORM")
    )
    assert not any("_Height" in name or "_Layer_" in name for name in imported)
    assert all(
        task["automated"] and task["replace_existing"] and task["save"]
        for task in editor.import_tasks
    )


def test_textures_get_the_same_settings_as_the_mesh_import(tmp_path: Path) -> None:
    editor = _editor()

    _run(tmp_path, editor)

    bc = editor.assets[f"{DESKTOP_DEST}/T_{NAME}_Grass_BC"].properties
    normal = editor.assets[f"{DESKTOP_DEST}/T_{NAME}_Grass_N"].properties
    orm = editor.assets[f"{DESKTOP_DEST}/T_{NAME}_Grass_ORM"].properties
    assert bc == {"srgb": True}
    assert normal == {
        "flip_green_channel": True,
        "compression_settings": "TC_NORMALMAP",
        "srgb": False,
    }
    assert orm == {"srgb": False, "compression_settings": "TC_MASKS"}


def test_an_existing_level_is_replaced(tmp_path: Path) -> None:
    editor = _editor()
    editor.levels.add(LEVEL)

    result = _run(tmp_path, editor)

    assert result["ok"] is True, result
    calls = _non_save_calls(editor)
    assert calls.index(f"delete_asset:{LEVEL}") < calls.index(f"new_level:{LEVEL}")
    assert editor.saved_levels == [LEVEL]
    assert editor.open_level == MAIN_MAP


def test_the_previous_level_is_restored_after_a_failure(tmp_path: Path) -> None:
    editor = _editor()
    editor.fail_on.add("import_landscape")

    result = _run(tmp_path, editor)

    assert result["ok"] is False
    assert result["error"] == "RuntimeError: fake failure in import_landscape"
    assert editor.saved_levels == [LEVEL]
    assert editor.loaded[-1] == MAIN_MAP
    assert editor.open_level == MAIN_MAP


def test_a_sample_error_over_5cm_is_a_height_mismatch(tmp_path: Path) -> None:
    editor = _editor()
    editor.sample_offset_cm = 6.0

    result = _run(tmp_path, editor)

    assert result["ok"] is False
    assert result["error"] == "terrain_height_mismatch"
    assert result["height_errors_cm"] == pytest.approx([6.0] * len(_samples()))
    assert editor.open_level == MAIN_MAP


def test_a_sample_error_within_5cm_passes(tmp_path: Path) -> None:
    editor = _editor()
    editor.sample_offset_cm = 4.0

    result = _run(tmp_path, editor)

    assert result["ok"] is True, result
    assert max(result["height_errors_cm"]) == pytest.approx(4.0)


def test_a_sample_outside_the_landscape_is_a_height_mismatch_not_a_pass(tmp_path: Path) -> None:
    editor = _editor()
    editor.sample_offset_cm = float("nan")

    result = _run(tmp_path, editor)

    assert result["ok"] is False
    assert result["error"] == "terrain_height_mismatch"
    assert editor.open_level == MAIN_MAP


def test_missing_layer_texture_stops_before_any_unreal_mutation(tmp_path: Path) -> None:
    folder = _write_variant(tmp_path / "Desktop")
    (folder / f"T_{NAME}_Rock_N.png").unlink()
    editor = _editor()

    result = _run(tmp_path, editor, variant_dir=folder)

    assert result["ok"] is False
    assert "T_Hills_Rock_N.png" in str(result["error"])
    assert editor.calls == []


# --- host: import_terrain_variant -----------------------------------------------------------


def test_host_returns_the_result_when_the_landscape_matches(tmp_path: Path) -> None:
    editor = _editor()
    client = EditorClient(editor)

    result = import_terrain_variant(
        client,
        variant_dir=str(_write_variant(tmp_path / "Desktop")),
        dest=DESKTOP_DEST,
        name=NAME,
        sidecar_variant=_sidecar(),
    )

    assert result["ok"] is True
    assert result["level"] == LEVEL
    assert len(client.codes) == 1


def test_host_raises_terrain_height_mismatch_for_a_6cm_error(tmp_path: Path) -> None:
    editor = _editor()
    editor.sample_offset_cm = 6.0

    with pytest.raises(PipelineError) as raised:
        import_terrain_variant(
            EditorClient(editor),
            variant_dir=str(_write_variant(tmp_path / "Desktop")),
            dest=DESKTOP_DEST,
            name=NAME,
            sidecar_variant=_sidecar(),
        )

    assert raised.value.code == "import_ue.terrain_height_mismatch"
    assert raised.value.stage == "import_ue"
    assert "6.00 cm" in raised.value.message
    assert editor.open_level == MAIN_MAP


def test_host_raises_import_ue_failed_for_any_other_failure(tmp_path: Path) -> None:
    editor = _editor()
    editor.fail_on.add("build_layered_material")

    with pytest.raises(PipelineError) as raised:
        import_terrain_variant(
            EditorClient(editor),
            variant_dir=str(_write_variant(tmp_path / "Desktop")),
            dest=DESKTOP_DEST,
            name=NAME,
            sidecar_variant=_sidecar(),
        )

    assert raised.value.code == "import_ue.failed"
    assert "build_layered_material" in raised.value.message


def test_host_does_not_call_unreal_for_an_unusable_sidecar(tmp_path: Path) -> None:
    client = EditorClient(_editor())
    sidecar = _sidecar()
    del sidecar["layers"]

    with pytest.raises(PipelineError) as raised:
        import_terrain_variant(
            client,
            variant_dir=str(_write_variant(tmp_path / "Desktop")),
            dest=DESKTOP_DEST,
            name=NAME,
            sidecar_variant=sidecar,
        )

    assert raised.value.code == "import_ue.failed"
    assert client.codes == []


def test_host_has_no_pivot_check_so_a_result_without_meshes_passes(tmp_path: Path) -> None:
    client = _StaticClient({"ok": True, "variant": "desktop", "name": NAME, "error": None})

    result = import_terrain_variant(
        client,
        variant_dir=str(tmp_path),
        dest=DESKTOP_DEST,
        name=NAME,
        sidecar_variant=_sidecar(),
    )

    assert result["ok"] is True
    assert len(client.codes) == 1


class _StaticClient:
    """An UnrealPythonClient that replies with one canned NMG_RESULT line."""

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.codes: list[str] = []

    def execute_python_code(self, code: str) -> str:
        self.codes.append(code)
        return "NMG_RESULT " + json.dumps(self.result, sort_keys=True)
