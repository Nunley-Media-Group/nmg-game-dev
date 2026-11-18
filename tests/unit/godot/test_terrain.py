"""Unit tests for ``godot.terrain``: heightmap decoding, the scene text, and the probe checks.

#249 FR4, AC4.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from nmg_game_dev.godot.terrain import (
    SHADER_PATH,
    TerrainVariant,
    check_probe,
    chunk_names,
    decode_heights,
    import_terrain,
    parse_variant,
    read_png_gray16,
    render_scene,
)
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.request import FinalizeRequest
from tests.finalize_fakes import (
    FinalizeGodot,
    TerrainStepRunner,
    terrain_entry,
    write_height_png,
)

TERRAIN = TerrainVariant(
    heightmap_px=127,
    spacing_m=1.0,
    height_min_m=10.0,
    height_max_m=40.0,
    uv_tile_m=8.0,
    layers=("Grass", "Rock"),
)


def test_chunk_names_cover_the_grid_in_63_quad_chunks() -> None:
    assert chunk_names("Hills", TERRAIN) == [
        "Hills_Chunk_0_0.glb",
        "Hills_Chunk_0_1.glb",
        "Hills_Chunk_1_0.glb",
        "Hills_Chunk_1_1.glb",
    ]
    big = TerrainVariant(1009, 1.0, 0.0, 1.0, 8.0, ("A",))
    assert len(chunk_names("Hills", big)) == 16 * 16


def test_a_16_bit_png_round_trips(tmp_path: Path) -> None:
    codes = [0, 1, 65535, 300, 40000, 7, 8, 9, 65534]
    write_height_png(tmp_path / "h.png", codes, 3)
    assert read_png_gray16(tmp_path / "h.png") == (3, 3, codes)


def test_every_png_filter_type_decodes(tmp_path: Path) -> None:
    import struct
    import zlib

    size = 3
    codes = [100, 2000, 30000, 65535, 0, 12345, 5, 6, 7]
    raw = b"".join(struct.pack(f">{size}H", *codes[r * size : (r + 1) * size]) for r in range(size))
    rows = [raw[r * 6 : (r + 1) * 6] for r in range(size)]

    def paeth(a: int, b: int, c: int) -> int:
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        return a if pa <= pb and pa <= pc else b if pb <= pc else c

    encoded = b""
    previous = bytes(6)
    for kind, row in zip((1, 3, 4), rows, strict=True):
        out = bytearray()
        for i, value in enumerate(row):
            left = row[i - 2] if i >= 2 else 0
            up = previous[i]
            upper_left = previous[i - 2] if i >= 2 else 0
            predictor = {1: left, 3: (left + up) // 2, 4: paeth(left, up, upper_left)}[kind]
            out.append((value - predictor) & 0xFF)
        encoded += bytes([kind]) + bytes(out)
        previous = row

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
        )

    header = struct.pack(">IIBBBBB", size, size, 16, 0, 0, 0, 0)
    path = tmp_path / "filtered.png"
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(encoded))
        + chunk(b"IEND", b"")
    )
    assert read_png_gray16(path) == (3, 3, codes)


def test_heights_decode_into_the_sidecar_range(tmp_path: Path) -> None:
    terrain = TerrainVariant(2, 1.0, 10.0, 40.0, 8.0, ("A",))
    write_height_png(tmp_path / "h.png", [0, 65535, 32768, 0], 2)
    heights = decode_heights(tmp_path / "h.png", terrain)
    assert heights[0] == pytest.approx(10.0)
    assert heights[1] == pytest.approx(40.0)
    assert heights[2] == pytest.approx(10.0 + 32768 / 65535 * 30.0)


def test_a_heightmap_of_the_wrong_size_is_a_mismatch(tmp_path: Path) -> None:
    write_height_png(tmp_path / "h.png", [0, 1, 2, 3], 2)
    with pytest.raises(PipelineError) as info:
        decode_heights(tmp_path / "h.png", TERRAIN)
    assert info.value.code == "import_godot.mismatch"


def test_parse_variant_refuses_more_than_four_layers() -> None:
    entry = terrain_entry("Desktop", layers=("A", "B", "C", "D", "E"))
    with pytest.raises(PipelineError) as info:
        parse_variant({"desktop": entry}, "Desktop")
    assert info.value.code == "import_godot.mismatch"


def test_the_scene_text_holds_chunks_material_and_heightmap(tmp_path: Path) -> None:
    folder = tmp_path / "assets" / "Environment" / "Hills" / "Desktop"
    terrain = TerrainVariant(127, 0.5, 0.0, 1.0, 8.0, ("Grass",))
    heights = [0.0] * (127 * 127 - 1) + [1.0]
    meshes = {name: ["Hills_Chunk/Mesh"] for name in chunk_names("Hills", terrain)}

    text = render_scene(tmp_path, folder, "Hills", terrain, heights, meshes)

    assert text.splitlines()[0] == "[gd_scene load_steps=12 format=3]"
    assert f'[ext_resource type="Shader" path="{SHADER_PATH}" id="shader"]' in text
    assert 'path="res://assets/Environment/Hills/Desktop/T_Hills_Splat.png" id="splat"' in text
    assert 'shader_parameter/layer0_bc = ExtResource("layer0_bc")' in text
    assert 'shader_parameter/layer0_n = ExtResource("layer0_n")' in text
    assert 'shader_parameter/layer0_orm = ExtResource("layer0_orm")' in text
    assert 'shader_parameter/splat = ExtResource("splat")' in text
    # 126 quads of 0.5 m over an 8 m tile: 7.875 repeats across the terrain.
    assert "shader_parameter/uv_scale = 7.875" in text
    assert '[node name="Mesh" parent="Hills_Chunk_0_0/Hills_Chunk"]' in text
    assert text.count('material_override = SubResource("ShaderMaterial_terrain")') == 4
    data = re.search(r"map_data = PackedFloat32Array\(([^)]*)\)", text)
    assert data is not None
    values = data.group(1).split(", ")
    assert len(values) == 127 * 127
    assert values[-1] == "1"
    assert "transform = Transform3D(0.5, 0, 0, 0, 1, 0, 0, 0, 0.5, 0, 0, 0)" in text


@pytest.mark.parametrize(
    ("probe", "code"),
    [
        (
            {
                "chunks": 3,
                "height_min": 10,
                "height_max": 40,
                "mesh_height_min": 10,
                "mesh_height_max": 40,
            },
            "import_godot.mismatch",
        ),
        (
            {
                "chunks": 4,
                "height_min": 9.9,
                "height_max": 40,
                "mesh_height_min": 10,
                "mesh_height_max": 40,
            },
            "import_godot.terrain_height_mismatch",
        ),
        (
            {
                "chunks": 4,
                "height_min": 10,
                "height_max": 40,
                "mesh_height_min": 10,
                "mesh_height_max": 40.06,
            },
            "import_godot.terrain_height_mismatch",
        ),
        ({"chunks": 4}, "import_godot.import_failed"),
    ],
)
def test_check_probe_codes(probe: dict[str, float], code: str) -> None:
    with pytest.raises(PipelineError) as info:
        check_probe("Desktop", TERRAIN, probe)
    assert info.value.code == code
    assert info.value.remediation


def test_check_probe_accepts_ranges_within_five_centimetres() -> None:
    check_probe(
        "Desktop",
        TERRAIN,
        {
            "chunks": 4,
            "height_min": 10.04,
            "height_max": 39.96,
            "mesh_height_min": 9.96,
            "mesh_height_max": 40.04,
        },
    )


def test_a_chunk_that_imported_without_a_mesh_is_a_mismatch(tmp_path: Path) -> None:
    request = FinalizeRequest(
        collection="Hills",
        category="Environment",
        asset_class="terrain",
        export_root=tmp_path / "assets",
    )
    runner = TerrainStepRunner(request)
    outputs = runner._export_outputs(tmp_path / "job")
    sidecar = json.loads(Path(outputs["sidecar"]).read_text(encoding="utf-8"))
    godot = FinalizeGodot(tmp_path, responses={"probe_terrain.gd": {"meshes": {}}})
    folders = {v: Path(outputs["variants"][v]["dir"]) for v in ("Desktop", "Mobile")}

    with pytest.raises(PipelineError) as info:
        import_terrain(godot, tmp_path, name="Hills", variant_dirs=folders, sidecar=sidecar)

    assert info.value.code == "import_godot.mismatch"
    assert "no mesh" in info.value.message
    assert not (folders["Desktop"] / "Hills.tscn").exists()
