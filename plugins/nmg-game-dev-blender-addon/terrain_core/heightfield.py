"""Heightfield math and a minimal PNG codec for the terrain asset class (#154).

Pure Python: no bpy import and no relative imports, so the unit suite loads this file by path.

Grid convention, shared by every function here:

- A grid is a flat, row-major sequence of ``n * n`` samples, index ``row * n + col``.
- Row 0 is the Blender +Y edge and column 0 is the Blender -X edge. The grid is centred on the
  origin: vertex ``(row, col)`` sits at ``x = -half + col * spacing`` and
  ``y = half - row * spacing``, where ``half = (n - 1) * spacing / 2``. Unreal's +Y is Blender's
  -Y, so the Unreal side reads row 0 as its minimum Y edge.
- Heights are metres in Blender Z. Height codes are 16-bit, 0 at the minimum and 65535 at the
  maximum, stored as ``bytes16``: two big-endian bytes per sample (PNG byte order).
- Layer weights are layer-major: ``layers[k]`` is the flat grid of layer ``k``.
"""

from __future__ import annotations

import struct
import sys
import zlib
from array import array
from collections.abc import Sequence
from pathlib import Path
from typing import Final, NamedTuple, TypeVar

VALID_SIZES: Final[tuple[int, ...]] = (127, 253, 505, 1009, 2017, 4033)
HEIGHT_CODE_MAX: Final = 65535
HEIGHT_CODE_FLAT: Final = 32768
WEIGHT_TOTAL: Final = 255
# Order of the points sample_points returns: nw is row 0, col 0 (Blender -X, +Y).
SAMPLE_POINT_NAMES: Final[tuple[str, ...]] = (
    "nw",
    "ne",
    "sw",
    "se",
    "n",
    "s",
    "w",
    "e",
    "center",
    "min",
    "max",
)

_PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
_T = TypeVar("_T")


class GrayImage(NamedTuple):
    """A decoded grayscale PNG.

    ``samples`` is the raw row-major sample data: one byte per 8-bit sample, or two big-endian
    bytes per 16-bit sample (the bytes16 layout that encode_heights returns).
    """

    width: int
    height: int
    bit_depth: int
    samples: bytes


def mobile_size(desktop: int, budget_px: int) -> tuple[int, int]:
    """Return ``(size, stride)`` for the largest valid size, halving from desktop, within budget_px.

    Halving runs along VALID_SIZES (2017 -> 1009 -> 505 ...). The stride is the sample step that
    maps the Desktop grid onto the returned size. Raises ValueError when desktop is not a valid
    size or when even the smallest valid size exceeds budget_px.
    """
    if desktop not in VALID_SIZES:
        raise ValueError(f"desktop size must be one of {VALID_SIZES}, got {desktop}")
    index = VALID_SIZES.index(desktop)
    size = desktop
    while size > budget_px and index > 0:
        index -= 1
        size = VALID_SIZES[index]
    if size > budget_px:
        raise ValueError(f"no valid heightmap size fits a budget of {budget_px} px")
    return size, (desktop - 1) // (size - 1)


def encode_heights(heights: Sequence[float], n: int) -> tuple[bytes, float, float]:
    """Encode an n x n height grid as 16-bit codes. Returns ``(bytes16, zmin, zmax)``.

    ``v = round((z - zmin) / (zmax - zmin) * 65535)``. A flat grid (zmin == zmax) encodes
    32768 everywhere.
    """
    _check_size(n)
    _check_samples(len(heights), n)
    zmin = min(heights)
    zmax = max(heights)
    span = zmax - zmin
    if span == 0:
        codes = array("H", [HEIGHT_CODE_FLAT]) * len(heights)
    else:
        codes = array("H", [round((z - zmin) / span * HEIGHT_CODE_MAX) for z in heights])
    if sys.byteorder == "little":
        codes.byteswap()
    return codes.tobytes(), zmin, zmax


def decode_heights(bytes16: bytes, n: int, zmin: float, zmax: float) -> list[float]:
    """Inverse of encode_heights: ``z = zmin + v / 65535 * (zmax - zmin)`` for each sample."""
    _check_size(n)
    if len(bytes16) != 2 * n * n:
        raise ValueError(f"expected {2 * n * n} bytes for a {n}x{n} grid, got {len(bytes16)}")
    codes = array("H")
    codes.frombytes(bytes16)
    if sys.byteorder == "little":
        codes.byteswap()
    span = zmax - zmin
    return [zmin + code / HEIGHT_CODE_MAX * span for code in codes]


def normalize_weights(layers: Sequence[Sequence[float]]) -> list[list[float]]:
    """Divide each vertex's layer weights by their sum, so every vertex sums to 1.

    A vertex whose weights are all zero goes wholly to the layer with the highest total weight
    (the lowest index on a tie). Negative weights raise ValueError.
    """
    count = _check_layers(layers)
    if any(weight < 0 for layer in layers for weight in layer):
        raise ValueError("layer weights must be non-negative")
    totals = [sum(layer) for layer in layers]
    fallback = totals.index(max(totals))
    out = [[0.0] * count for _ in layers]
    for index in range(count):
        column_total = sum(layer[index] for layer in layers)
        if column_total > 0:
            for slot, layer in enumerate(layers):
                out[slot][index] = layer[index] / column_total
        else:
            out[fallback][index] = 1.0
    return out


def quantize_weights(normalized: Sequence[Sequence[float]]) -> list[bytes]:
    """Return one 8-bit weightmap (bytes, one byte per pixel) per layer. Every pixel sums to 255.

    Each pixel is first scaled to sum to 1, so normalized weights and raw non-negative weights
    both work. Largest-remainder rounding: floor each share of 255, then hand the leftover units
    to the largest fractional parts (the lower layer index first on a tie). A pixel with no
    weight in any layer raises ValueError.
    """
    layer_count = len(normalized)
    count = _check_layers(normalized)
    columns = [bytearray(count) for _ in range(layer_count)]
    for index in range(count):
        shares = [layer[index] for layer in normalized]
        total = sum(shares)
        if total <= 0:
            raise ValueError(f"pixel {index} has no weight in any layer")
        exact = [share / total * WEIGHT_TOTAL for share in shares]
        floors = [int(value) for value in exact]
        leftover = WEIGHT_TOTAL - sum(floors)
        by_remainder = sorted(
            range(layer_count), key=lambda slot: (-(exact[slot] - floors[slot]), slot)
        )
        for slot in by_remainder[:leftover]:
            floors[slot] += 1
        for slot, value in enumerate(floors):
            columns[slot][index] = value
    return [bytes(column) for column in columns]


def downsample(grid: Sequence[_T], n: int, stride: int) -> list[_T]:
    """Keep every ``stride``-th sample of an n x n grid, so row 0 and column 0 are kept.

    ``(n - 1)`` must be a multiple of ``stride`` so the last row and column are kept too:
    2017 at stride 2 gives 1009. Works on any sample sequence, including weights and codes.
    """
    _check_size(n)
    _check_samples(len(grid), n)
    if stride < 1 or (n - 1) % stride != 0:
        raise ValueError(f"stride {stride} must divide n - 1 = {n - 1}")
    keep = range(0, n, stride)
    out: list[_T] = []
    for row in keep:
        base = row * n
        out.extend(grid[base : base + n : stride])
    return out


def reduce_layers(
    weights: Sequence[Sequence[float]], limit: int
) -> tuple[tuple[int, ...], list[list[float]]]:
    """Keep the ``limit`` layers with the highest total weight. Returns ``(kept, layers)``.

    ``kept`` lists the original indices of the kept layers, in their original order. ``layers``
    holds their weights, renormalized per vertex so each vertex sums to 1. The dropped layers'
    weight is redistributed proportionally into the kept layers. A vertex whose kept weights are
    all zero goes wholly to the kept layer with the highest total (the lowest index on a tie).
    A total tie at the cut keeps the lower index.
    """
    if limit < 1:
        raise ValueError(f"layer limit must be at least 1, got {limit}")
    count = _check_layers(weights)
    totals = [sum(layer) for layer in weights]
    ranked = sorted(range(len(weights)), key=lambda slot: (-totals[slot], slot))
    kept = tuple(sorted(ranked[: min(limit, len(weights))]))
    fallback_slot = kept.index(min(kept, key=lambda slot: (-totals[slot], slot)))
    reduced = [[0.0] * count for _ in kept]
    for index in range(count):
        kept_sum = sum(weights[layer][index] for layer in kept)
        if kept_sum > 0:
            for slot, layer in enumerate(kept):
                reduced[slot][index] = weights[layer][index] / kept_sum
        else:
            reduced[fallback_slot][index] = 1.0
    return kept, reduced


def sample_points(heights: Sequence[float], n: int, spacing: float) -> list[list[float]]:
    """Return 11 points in Blender space, each ``[x_m, y_m, z_m]``, in SAMPLE_POINT_NAMES order.

    The first nine are the corners (nw, ne, sw, se), the edge midpoints (n, s, w, e), and the
    centre. Then come the minimum and maximum vertex (the first occurrence of each).
    """
    _check_size(n)
    _check_samples(len(heights), n)
    if spacing <= 0:
        raise ValueError(f"spacing must be positive, got {spacing}")
    half = (n - 1) * spacing / 2
    last = n - 1
    mid = last // 2

    def point(row: int, col: int) -> list[float]:
        return [-half + col * spacing, half - row * spacing, float(heights[row * n + col])]

    lowest = heights.index(min(heights))
    highest = heights.index(max(heights))
    grid_positions = [
        (0, 0),
        (0, last),
        (last, 0),
        (last, last),
        (0, mid),
        (last, mid),
        (mid, 0),
        (mid, last),
        (mid, mid),
    ]
    positions = [*grid_positions, divmod(lowest, n), divmod(highest, n)]
    return [point(row, col) for row, col in positions]


def write_png_gray16(data: bytes, width: int, height: int, path: Path) -> None:
    """Write a 16-bit grayscale PNG. ``data`` is bytes16: two big-endian bytes per sample."""
    _write_gray_png(data, width, height, 16, path)


def write_png_gray8(data: bytes, width: int, height: int, path: Path) -> None:
    """Write an 8-bit grayscale PNG. ``data`` holds one byte per sample."""
    _write_gray_png(data, width, height, 8, path)


def read_png_gray(path: Path) -> GrayImage:
    """Read a non-interlaced 8- or 16-bit grayscale PNG with any of the five filter types.

    Colour, palette, alpha, and interlaced PNGs raise ValueError. Chunk CRCs are checked.
    """
    data = path.read_bytes()
    if not data.startswith(_PNG_SIGNATURE):
        raise ValueError(f"{path} is not a PNG file")
    header: bytes | None = None
    compressed = bytearray()
    position = len(_PNG_SIGNATURE)
    while True:
        if position + 12 > len(data):
            raise ValueError(f"{path} ends before its IEND chunk")
        (length,) = struct.unpack_from(">I", data, position)
        kind = data[position + 4 : position + 8]
        body_end = position + 8 + length
        if body_end + 4 > len(data):
            raise ValueError(f"{path} has a truncated {kind!r} chunk")
        body = data[position + 8 : body_end]
        (crc,) = struct.unpack_from(">I", data, body_end)
        if zlib.crc32(kind + body) != crc:
            raise ValueError(f"{path} has a bad CRC in its {kind!r} chunk")
        position = body_end + 4
        if kind == b"IHDR":
            header = body
        elif kind == b"IDAT":
            compressed += body
        elif kind == b"IEND":
            break
    if header is None or len(header) != 13:
        raise ValueError(f"{path} has no valid IHDR chunk")
    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
        ">IIBBBBB", header
    )
    if color_type != 0:
        raise ValueError(f"{path} is not grayscale (colour type {color_type})")
    if bit_depth not in (8, 16):
        raise ValueError(f"{path} has bit depth {bit_depth}; only 8 and 16 are supported")
    if compression != 0 or filter_method != 0:
        raise ValueError(f"{path} uses an unknown compression or filter method")
    if interlace != 0:
        raise ValueError(f"{path} is interlaced; only non-interlaced PNGs are supported")
    if width < 1 or height < 1 or not compressed:
        raise ValueError(f"{path} has no image data")
    samples = _unfilter(zlib.decompress(bytes(compressed)), width, height, bit_depth // 8)
    return GrayImage(width, height, bit_depth, samples)


def _check_size(n: int) -> None:
    if n < 1:
        raise ValueError(f"grid size must be at least 1, got {n}")


def _check_samples(length: int, n: int) -> None:
    if length != n * n:
        raise ValueError(f"expected {n * n} samples for a {n}x{n} grid, got {length}")


def _check_layers(layers: Sequence[Sequence[float]]) -> int:
    """Validate a layer-major set of equal-length grids and return the per-layer sample count."""
    if not layers:
        raise ValueError("at least one layer is required")
    count = len(layers[0])
    if any(len(layer) != count for layer in layers):
        raise ValueError("every layer must have the same number of samples")
    return count


def _write_gray_png(data: bytes, width: int, height: int, bit_depth: int, path: Path) -> None:
    if width < 1 or height < 1:
        raise ValueError(f"PNG dimensions must be positive, got {width}x{height}")
    row_bytes = width * (bit_depth // 8)
    if len(data) != row_bytes * height:
        raise ValueError(
            f"expected {row_bytes * height} bytes for a {width}x{height} image, got {len(data)}"
        )
    raw = bytearray()
    for row in range(height):
        raw.append(0)  # filter type 0 (None) on every row
        raw += data[row * row_bytes : (row + 1) * row_bytes]
    header = struct.pack(">IIBBBBB", width, height, bit_depth, 0, 0, 0, 0)
    path.write_bytes(
        _PNG_SIGNATURE
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw)))
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))


def _unfilter(raw: bytes, width: int, height: int, bytes_per_pixel: int) -> bytes:
    stride = width * bytes_per_pixel
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise ValueError(f"PNG image data is {len(raw)} bytes; expected {expected}")
    out = bytearray(height * stride)
    previous = bytearray(stride)
    for row in range(height):
        start = row * (stride + 1)
        line = bytearray(raw[start + 1 : start + 1 + stride])
        _unfilter_row(raw[start], line, previous, bytes_per_pixel)
        out[row * stride : (row + 1) * stride] = line
        previous = line
    return bytes(out)


def _unfilter_row(kind: int, line: bytearray, previous: bytearray, bpp: int) -> None:
    """Undo one PNG filter in place. ``line`` holds filtered bytes on entry, raw bytes on exit."""
    if kind == 0:
        return
    if kind not in (1, 2, 3, 4):
        raise ValueError(f"unknown PNG filter type {kind}")
    for index in range(len(line)):
        left = line[index - bpp] if index >= bpp else 0
        up = previous[index]
        if kind == 1:
            predictor = left
        elif kind == 2:
            predictor = up
        elif kind == 3:
            predictor = (left + up) >> 1
        else:
            up_left = previous[index - bpp] if index >= bpp else 0
            predictor = _paeth(left, up, up_left)
        line[index] = (line[index] + predictor) & 0xFF


def _paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    d_left = abs(estimate - left)
    d_up = abs(estimate - up)
    d_up_left = abs(estimate - up_left)
    if d_left <= d_up and d_left <= d_up_left:
        return left
    if d_up <= d_up_left:
        return up
    return up_left
