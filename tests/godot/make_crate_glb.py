"""Write ``tests/godot/fixture/Crate.glb``: a deterministic 1 m cube for gate-godot-headless.

    uv run python tests/godot/make_crate_glb.py [--check]

The file is a glTF 2.0 binary with one node and one mesh, both named ``Crate``, and one primitive
with positions, normals, UVs, 16-bit indices, and one material. The cube is centred on the origin,
so Godot's probe reports 12 triangles, 1 material slot, and bounds -0.5..0.5 on every axis (see
``tests/godot/fixture/expected-probe.json``). ``--check`` exits 1 when the committed file differs.
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path
from typing import Final

OUT: Final = Path(__file__).resolve().parent / "fixture" / "Crate.glb"
NAME: Final = "Crate"
HALF: Final = 0.5

_FLOAT: Final = 5126
_USHORT: Final = 5123
_ARRAY_BUFFER: Final = 34962
_ELEMENT_ARRAY_BUFFER: Final = 34963

# Each face: its outward normal and two in-plane axes (u, v) chosen so u x v == normal, which keeps
# the triangle winding counter-clockwise when seen from outside.
_Axis = tuple[int, int, int]
_FACES: Final[tuple[tuple[_Axis, _Axis, _Axis], ...]] = (
    ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
    ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    ((0, 1, 0), (1, 0, 0), (0, 0, -1)),
    ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    ((0, 0, -1), (-1, 0, 0), (0, 1, 0)),
)
_CORNERS: Final = ((-1, -1, 0.0, 1.0), (1, -1, 1.0, 1.0), (1, 1, 1.0, 0.0), (-1, 1, 0.0, 0.0))


def _cube() -> tuple[list[float], list[float], list[float], list[int]]:
    positions: list[float] = []
    normals: list[float] = []
    uvs: list[float] = []
    indices: list[int] = []
    for normal, u_axis, v_axis in _FACES:
        base = len(positions) // 3
        for su, sv, tex_u, tex_v in _CORNERS:
            for axis in range(3):
                positions.append(HALF * (normal[axis] + su * u_axis[axis] + sv * v_axis[axis]))
            normals.extend(float(component) for component in normal)
            uvs.extend((tex_u, tex_v))
        indices.extend((base, base + 1, base + 2, base, base + 2, base + 3))
    return positions, normals, uvs, indices


def _pad(data: bytes, fill: bytes) -> bytes:
    return data + fill * (-len(data) % 4)


def build() -> bytes:
    """Return the GLB bytes."""
    positions, normals, uvs, indices = _cube()
    views = [
        struct.pack(f"<{len(positions)}f", *positions),
        struct.pack(f"<{len(normals)}f", *normals),
        struct.pack(f"<{len(uvs)}f", *uvs),
        _pad(struct.pack(f"<{len(indices)}H", *indices), b"\x00"),
    ]
    offsets = []
    offset = 0
    for view in views:
        offsets.append(offset)
        offset += len(view)
    binary = b"".join(views)
    vertex_count = len(positions) // 3
    doc = {
        "asset": {"version": "2.0", "generator": "nmg-game-dev tests/godot/make_crate_glb.py"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": NAME, "mesh": 0}],
        "meshes": [
            {
                "name": NAME,
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
                        "indices": 3,
                        "material": 0,
                        "mode": 4,
                    }
                ],
            }
        ],
        "materials": [
            {
                "name": f"M_{NAME}",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.6, 0.45, 0.3, 1.0],
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.8,
                },
            }
        ],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {
                "buffer": 0,
                "byteOffset": offsets[0],
                "byteLength": len(views[0]),
                "target": _ARRAY_BUFFER,
            },
            {
                "buffer": 0,
                "byteOffset": offsets[1],
                "byteLength": len(views[1]),
                "target": _ARRAY_BUFFER,
            },
            {
                "buffer": 0,
                "byteOffset": offsets[2],
                "byteLength": len(views[2]),
                "target": _ARRAY_BUFFER,
            },
            {
                "buffer": 0,
                "byteOffset": offsets[3],
                "byteLength": len(indices) * 2,
                "target": _ELEMENT_ARRAY_BUFFER,
            },
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": _FLOAT,
                "count": vertex_count,
                "type": "VEC3",
                "min": [-HALF, -HALF, -HALF],
                "max": [HALF, HALF, HALF],
            },
            {"bufferView": 1, "componentType": _FLOAT, "count": vertex_count, "type": "VEC3"},
            {"bufferView": 2, "componentType": _FLOAT, "count": vertex_count, "type": "VEC2"},
            {"bufferView": 3, "componentType": _USHORT, "count": len(indices), "type": "SCALAR"},
        ],
    }
    json_chunk = _pad(json.dumps(doc, separators=(",", ":"), sort_keys=True).encode(), b" ")
    bin_chunk = _pad(binary, b"\x00")
    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    return b"".join(
        (
            struct.pack("<4sII", b"glTF", 2, total),
            struct.pack("<I4s", len(json_chunk), b"JSON"),
            json_chunk,
            struct.pack("<I4s", len(bin_chunk), b"BIN\x00"),
            bin_chunk,
        )
    )


def main(argv: list[str]) -> int:
    data = build()
    if "--check" in argv:
        if not OUT.is_file() or OUT.read_bytes() != data:
            print(f"{OUT} is stale; run tests/godot/make_crate_glb.py", file=sys.stderr)
            return 1
        return 0
    OUT.write_bytes(data)
    print(f"Wrote {OUT} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
