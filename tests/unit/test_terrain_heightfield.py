"""Heightfield core for the terrain asset class (#154, T001): encoding, weights, and the PNG codec.

heightfield.py is a Blender add-on module that cannot be imported under plain CPython, so the
suite loads it by file path, as test_blender_budgets.py does for utils/budgets.py.
"""

from __future__ import annotations

import ast
import importlib.util
import random
import struct
import zlib
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADDON_ROOT = _REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon"
_HEIGHTFIELD_PATH = _ADDON_ROOT / "terrain_core" / "heightfield.py"
_TERRAIN_INIT_PATH = _ADDON_ROOT / "terrain_core" / "__init__.py"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _load_heightfield() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "nmg_terrain_heightfield_under_test", _HEIGHTFIELD_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def hf() -> ModuleType:
    return _load_heightfield()


def _height_codes(data: bytes) -> list[int]:
    return list(struct.unpack(f">{len(data) // 2}H", data))


def _paeth_predictor(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    d_left, d_up, d_up_left = abs(estimate - left), abs(estimate - up), abs(estimate - up_left)
    if d_left <= d_up and d_left <= d_up_left:
        return left
    if d_up <= d_up_left:
        return up
    return up_left


def _filter_line(kind: int, line: bytes, previous: bytes, bpp: int) -> bytes:
    """Forward PNG filter, written independently of the module under test."""
    out = bytearray(len(line))
    for index, value in enumerate(line):
        left = line[index - bpp] if index >= bpp else 0
        up = previous[index]
        up_left = previous[index - bpp] if index >= bpp else 0
        if kind == 0:
            predictor = 0
        elif kind == 1:
            predictor = left
        elif kind == 2:
            predictor = up
        elif kind == 3:
            predictor = (left + up) // 2
        else:
            predictor = _paeth_predictor(left, up, up_left)
        out[index] = (value - predictor) & 0xFF
    return bytes(out)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))


def _write_png(
    path: Path,
    width: int,
    height: int,
    bit_depth: int,
    samples: bytes,
    row_filters: list[int],
    color_type: int = 0,
) -> None:
    """Write a PNG whose rows use row_filters in turn, with IDAT split into two chunks."""
    bpp = bit_depth // 8
    stride = width * bpp
    raw = bytearray()
    previous = bytes(stride)
    for row in range(height):
        line = samples[row * stride : (row + 1) * stride]
        kind = row_filters[row % len(row_filters)]
        raw.append(kind)
        raw += _filter_line(kind, line, previous, bpp)
        previous = line
    compressed = zlib.compress(bytes(raw))
    middle = len(compressed) // 2
    header = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0)
    path.write_bytes(
        _PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", compressed[:middle])
        + _chunk(b"IDAT", compressed[middle:])
        + _chunk(b"IEND", b"")
    )


def _read_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    assert data.startswith(_PNG_SIGNATURE)
    chunks: list[tuple[bytes, bytes]] = []
    position = len(_PNG_SIGNATURE)
    while position < len(data):
        (length,) = struct.unpack_from(">I", data, position)
        kind = data[position + 4 : position + 8]
        chunks.append((kind, data[position + 8 : position + 8 + length]))
        position += 12 + length
    return chunks


def test_heightfield_has_no_bpy_or_relative_imports() -> None:
    for path in (_HEIGHTFIELD_PATH, _TERRAIN_INIT_PATH):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name.split(".")[0] != "bpy" for alias in node.names), path
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, f"relative import in {path}"
                assert (node.module or "").split(".")[0] != "bpy", path


def test_valid_sizes_are_the_contract_ladder(hf: ModuleType) -> None:
    assert hf.VALID_SIZES == (127, 253, 505, 1009, 2017, 4033)


@pytest.mark.parametrize(
    ("desktop", "budget", "expected"),
    [
        (2017, 1009, (1009, 2)),
        (2017, 2017, (2017, 1)),
        (2017, 1000, (505, 4)),
        (2017, 127, (127, 16)),
        (4033, 1009, (1009, 4)),
        (505, 1009, (505, 1)),
    ],
)
def test_mobile_size_halves_until_within_budget(
    hf: ModuleType, desktop: int, budget: int, expected: tuple[int, int]
) -> None:
    assert hf.mobile_size(desktop, budget) == expected


def test_mobile_size_rejects_unfittable_budget_and_unknown_desktop(hf: ModuleType) -> None:
    with pytest.raises(ValueError):
        hf.mobile_size(2017, 100)
    with pytest.raises(ValueError):
        hf.mobile_size(2000, 1009)


def test_encode_decode_round_trip_within_one_code_step(hf: ModuleType) -> None:
    rng = random.Random(154)
    n = 9
    heights = [rng.uniform(-3.0, 97.5) for _ in range(n * n)]

    data, zmin, zmax = hf.encode_heights(heights, n)
    decoded = hf.decode_heights(data, n, zmin, zmax)

    assert zmin == min(heights)
    assert zmax == max(heights)
    tolerance = (zmax - zmin) / 65535 / 2 + 1e-9
    assert all(abs(got - want) <= tolerance for got, want in zip(decoded, heights, strict=True))
    codes = _height_codes(data)
    assert codes[heights.index(zmin)] == 0
    assert codes[heights.index(zmax)] == 65535


def test_round_trip_over_a_zero_to_500_metre_range_stays_within_5_cm(hf: ModuleType) -> None:
    n = 17
    heights = [500.0 * index / (n * n - 1) for index in range(n * n)]

    data, zmin, zmax = hf.encode_heights(heights, n)
    decoded = hf.decode_heights(data, n, zmin, zmax)

    assert max(abs(got - want) for got, want in zip(decoded, heights, strict=True)) < 0.05


def test_encode_is_big_endian_and_row_major(hf: ModuleType) -> None:
    data, zmin, zmax = hf.encode_heights([0.0, 1.0, 2.0, 3.0], 2)

    assert (zmin, zmax) == (0.0, 3.0)
    assert struct.unpack(">4H", data) == (0, 21845, 43690, 65535)


def test_flat_grid_encodes_32768(hf: ModuleType) -> None:
    data, zmin, zmax = hf.encode_heights([12.5] * 16, 4)

    assert _height_codes(data) == [32768] * 16
    assert (zmin, zmax) == (12.5, 12.5)
    assert hf.decode_heights(data, 4, zmin, zmax) == [12.5] * 16


def test_encode_and_decode_reject_mismatched_sample_counts(hf: ModuleType) -> None:
    with pytest.raises(ValueError):
        hf.encode_heights([0.0, 1.0, 2.0], 2)
    with pytest.raises(ValueError):
        hf.decode_heights(bytes(6), 2, 0.0, 1.0)


def test_normalize_weights_divides_by_sum_and_fills_zero_vertices(hf: ModuleType) -> None:
    layers = [[1.0, 0.0, 0.0], [3.0, 0.0, 0.0]]

    normalized = hf.normalize_weights(layers)

    assert normalized[0][0] == pytest.approx(0.25)
    assert normalized[1][0] == pytest.approx(0.75)
    # All-zero vertices go wholly to layer 1, the layer with the highest total (3.0 > 1.0).
    assert [normalized[0][1], normalized[1][1]] == [0.0, 1.0]
    assert [normalized[0][2], normalized[1][2]] == [0.0, 1.0]


def test_weight_sums_are_exactly_255_on_random_weights(hf: ModuleType) -> None:
    rng = random.Random(154)
    count = 50 * 50
    layer_count = 4
    layers = [
        [rng.random() * (rng.random() < 0.7) for _ in range(count)] for _ in range(layer_count)
    ]

    quantized = hf.quantize_weights(hf.normalize_weights(layers))

    assert len(quantized) == layer_count
    assert all(len(layer) == count for layer in quantized)
    assert [sum(pixel) for pixel in zip(*quantized, strict=True)] == [255] * count


def test_quantize_rounds_by_largest_remainder(hf: ModuleType) -> None:
    # 0.5 / 0.5 gives 127.5 each. The leftover unit goes to layer 0, the lower index on a tie.
    assert hf.quantize_weights([[0.5], [0.5]]) == [bytes([128]), bytes([127])]
    thirds = hf.quantize_weights([[1 / 3], [1 / 3], [1 / 3]])
    assert [layer[0] for layer in thirds] == [85, 85, 85]


def test_quantize_rejects_a_pixel_with_no_weight(hf: ModuleType) -> None:
    with pytest.raises(ValueError):
        hf.quantize_weights([[0.0], [0.0]])


def test_downsample_2017_to_1009_at_stride_2_keeps_the_corners(hf: ModuleType) -> None:
    n = 2017
    grid = list(range(n * n))

    out = hf.downsample(grid, n, 2)

    assert len(out) == 1009 * 1009
    assert out[0] == grid[0]
    assert out[1008] == grid[2016]
    assert out[1008 * 1009] == grid[2016 * n]
    assert out[-1] == grid[2016 * n + 2016]
    assert out[1] == grid[2]
    assert out[1009] == grid[2 * n]


def test_downsample_rejects_a_stride_that_drops_the_last_sample(hf: ModuleType) -> None:
    with pytest.raises(ValueError):
        hf.downsample(list(range(25)), 5, 3)


def test_reduce_layers_drops_lowest_total_and_renormalizes(hf: ModuleType) -> None:
    # Totals: A 0.9 (lowest), B 1.0, C 1.3. Limit 2 drops A.
    layer_a = [0.6, 0.0, 0.1, 0.2]
    layer_b = [0.4, 0.5, 0.1, 0.0]
    layer_c = [0.0, 0.5, 0.8, 0.0]

    kept, reduced = hf.reduce_layers([layer_a, layer_b, layer_c], 2)

    assert kept == (1, 2)
    # Pixel 0: A's 0.6 redistributes into B and C in proportion, so B takes all of 0.4 / 0.4.
    # Pixel 1: B and C already split 0.5 / 0.5. Pixel 2: B 0.1 and C 0.8 renormalize to 0.9.
    assert reduced[0] == pytest.approx([1.0, 0.5, 1 / 9, 0.0])
    assert reduced[1] == pytest.approx([0.0, 0.5, 8 / 9, 1.0])
    for pixel in range(4):
        assert reduced[0][pixel] + reduced[1][pixel] == pytest.approx(1.0)


def test_reduce_layers_sends_an_all_zero_pixel_to_the_highest_total_remaining_layer(
    hf: ModuleType,
) -> None:
    # Totals: A 0.2 (dropped), B 0.5, C 0.8. Pixel 0 has weight only in the dropped layer A,
    # so it goes wholly to C, the highest-total kept layer, not to B. Pixel 1 renormalizes.
    kept, reduced = hf.reduce_layers([[0.2, 0.0], [0.0, 0.5], [0.0, 0.8]], 2)

    assert kept == (1, 2)
    assert [reduced[0][0], reduced[1][0]] == [0.0, 1.0]
    assert reduced[0][1] == pytest.approx(0.5 / 1.3)
    assert reduced[1][1] == pytest.approx(0.8 / 1.3)


def test_reduce_layers_keeps_every_layer_when_the_limit_allows(hf: ModuleType) -> None:
    kept, reduced = hf.reduce_layers([[0.5, 0.0], [0.5, 1.0]], 4)

    assert kept == (0, 1)
    assert reduced == [[0.5, 0.0], [0.5, 1.0]]


def test_sample_points_on_a_five_by_five_grid_at_two_metres(hf: ModuleType) -> None:
    n = 5
    heights = [float(row * 10 + col) for row in range(n) for col in range(n)]

    points = hf.sample_points(heights, n, 2.0)

    assert len(points) == len(hf.SAMPLE_POINT_NAMES) == 11
    expected = [
        [-4.0, 4.0, 0.0],  # nw (row 0, col 0)
        [4.0, 4.0, 4.0],  # ne
        [-4.0, -4.0, 40.0],  # sw
        [4.0, -4.0, 44.0],  # se
        [0.0, 4.0, 2.0],  # n
        [0.0, -4.0, 42.0],  # s
        [-4.0, 0.0, 20.0],  # w
        [4.0, 0.0, 24.0],  # e
        [0.0, 0.0, 22.0],  # center
        [-4.0, 4.0, 0.0],  # min (the first vertex)
        [4.0, -4.0, 44.0],  # max (the last vertex)
    ]
    assert points == expected


def test_sample_points_span_the_desktop_grid_in_blender_space(hf: ModuleType) -> None:
    n = 2017
    heights = [0.0] * (n * n)
    heights[5 * n + 7] = 9.0

    points = hf.sample_points(heights, n, 1.0)

    assert points[hf.SAMPLE_POINT_NAMES.index("nw")] == [-1008.0, 1008.0, 0.0]
    assert points[hf.SAMPLE_POINT_NAMES.index("se")] == [1008.0, -1008.0, 0.0]
    assert points[hf.SAMPLE_POINT_NAMES.index("max")] == [-1001.0, 1003.0, 9.0]


def test_png_gray8_round_trips(hf: ModuleType, tmp_path: Path) -> None:
    rng = random.Random(8)
    data = bytes(rng.randrange(256) for _ in range(5 * 3))
    path = tmp_path / "gray8.png"

    hf.write_png_gray8(data, 5, 3, path)
    image = hf.read_png_gray(path)

    assert (image.width, image.height, image.bit_depth) == (5, 3, 8)
    assert image.samples == data


def test_png_gray16_round_trips(hf: ModuleType, tmp_path: Path) -> None:
    rng = random.Random(16)
    data = bytes(rng.randrange(256) for _ in range(5 * 3 * 2))
    path = tmp_path / "gray16.png"

    hf.write_png_gray16(data, 5, 3, path)
    image = hf.read_png_gray(path)

    assert (image.width, image.height, image.bit_depth) == (5, 3, 16)
    assert image.samples == data


def test_heights_survive_a_16_bit_png(hf: ModuleType, tmp_path: Path) -> None:
    rng = random.Random(154)
    n = 7
    heights = [rng.uniform(0.0, 250.0) for _ in range(n * n)]
    data, zmin, zmax = hf.encode_heights(heights, n)
    path = tmp_path / "T_Height.png"

    hf.write_png_gray16(data, n, n, path)
    image = hf.read_png_gray(path)

    assert hf.decode_heights(image.samples, n, zmin, zmax) == hf.decode_heights(data, n, zmin, zmax)


def test_writer_uses_filter_type_zero_on_every_row(hf: ModuleType, tmp_path: Path) -> None:
    width, height = 4, 6
    data = bytes(range(width * height))
    path = tmp_path / "filter0.png"

    hf.write_png_gray8(data, width, height, path)
    idat = b"".join(body for kind, body in _read_chunks(path.read_bytes()) if kind == b"IDAT")
    raw = zlib.decompress(idat)

    assert len(raw) == height * (width + 1)
    assert all(raw[row * (width + 1)] == 0 for row in range(height))


@pytest.mark.parametrize("bit_depth", [8, 16])
def test_reader_handles_all_five_filter_types(
    hf: ModuleType, tmp_path: Path, bit_depth: int
) -> None:
    rng = random.Random(bit_depth)
    width, height = 7, 10
    samples = bytes(rng.randrange(256) for _ in range(width * height * bit_depth // 8))
    path = tmp_path / f"filtered{bit_depth}.png"
    _write_png(path, width, height, bit_depth, samples, row_filters=[0, 1, 2, 3, 4])

    image = hf.read_png_gray(path)

    assert (image.width, image.height, image.bit_depth) == (width, height, bit_depth)
    assert image.samples == samples


def test_reader_rejects_an_unknown_filter_type(hf: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "bad_filter.png"
    _write_png(path, 2, 2, 8, bytes(4), row_filters=[5])

    with pytest.raises(ValueError, match="filter type 5"):
        hf.read_png_gray(path)


def test_reader_rejects_colour_pngs(hf: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "rgb.png"
    _write_png(path, 2, 2, 8, bytes(12), row_filters=[0], color_type=2)

    with pytest.raises(ValueError, match="not grayscale"):
        hf.read_png_gray(path)
