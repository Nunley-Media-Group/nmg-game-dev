"""Write the anims and terrain probe fixtures under ``tests/godot/fixture/`` for the Godot gate.

    uv run python -m tests.godot.make_probe_fixtures [--check]

``fixture/anims/`` holds a two-bone skinned rig (``Rig.glb``, imported as a scene) and three clip
files, each with an ``.import`` that selects Godot's ``animation_library`` importer, as
``import_anims`` writes it:

- ``A_Rig_Walk.glb``: authored from frame 0 to 24 at 24 fps; keys 0 to 1 s, so 24 frames.
- ``A_Rig_Wave.glb``: authored from frame 10 to 25 at 30 fps and exported the way finalize exports
  it (``export_anim_slide_to_zero``), so its keys run 0 to 0.5 s: 15 frames, which is
  ``frame_end - frame_start``.
- ``A_Rig_WaveUnslid.glb``: the same clip with its keys left at 10/30 to 25/30 s. Godot keeps the
  absolute key times, so it measures 25 frames (``frame_end``): the reason the export slides.

``fixture/terrain/`` holds a one-chunk terrain scene written by the real
``nmg_game_dev.godot.terrain.render_scene``: the chunk is the fixture cube, the heightfield spans
-0.5 to 0.5 m, and each texture is a 1x1 PNG.

``expected-anims.json`` and ``expected-terrain.json`` hold each probe's params and the
``NMG_RESULT`` the gate requires from real Godot. ``--check`` exits 1 when a committed file differs.
"""

from __future__ import annotations

import json
import math
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, Final

from nmg_game_dev.godot.anims import IMPORTER
from nmg_game_dev.godot.terrain import TEXTURE_SUFFIXES, TerrainVariant, render_scene
from tests.godot.make_crate_glb import build as build_crate_glb

FIXTURE: Final = Path(__file__).resolve().parent / "fixture"
ANIMS: Final = FIXTURE / "anims"
TERRAIN: Final = FIXTURE / "terrain"
BONES: Final = ("Hip", "Spine")

_FLOAT: Final = 5126
_UBYTE: Final = 5121
_USHORT: Final = 5123


# (clip name, fps, key times in seconds, measured frame count)
CLIPS: Final = (
    ("Walk", 24.0, (0.0, 0.5, 1.0), 24),
    ("Wave", 30.0, (0.0, 0.25, 0.5), 15),
    ("WaveUnslid", 30.0, (10 / 30, 17.5 / 30, 25 / 30), 25),
)

TERRAIN_NAME: Final = "Valley"
TERRAIN_VARIANT: Final = TerrainVariant(
    heightmap_px=2,
    spacing_m=1.0,
    height_min_m=-0.5,
    height_max_m=0.5,
    uv_tile_m=1.0,
    layers=("Grass",),
)
TERRAIN_HEIGHTS: Final = (-0.5, 0.5, 0.5, -0.5)


def _pad(data: bytes, fill: bytes) -> bytes:
    return data + fill * (-len(data) % 4)


def _glb(doc: dict[str, Any], views: list[bytes]) -> bytes:
    """Pack ``doc`` and its buffer views (each 4-byte aligned) into GLB bytes."""
    offset = 0
    buffer_views = []
    for view in views:
        buffer_views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(view)})
        offset += len(_pad(view, b"\x00"))
    binary = b"".join(_pad(view, b"\x00") for view in views)
    doc = {**doc, "buffers": [{"byteLength": len(binary)}], "bufferViews": buffer_views}
    json_chunk = _pad(json.dumps(doc, separators=(",", ":"), sort_keys=True).encode(), b" ")
    total = 12 + 8 + len(json_chunk) + 8 + len(binary)
    return b"".join(
        (
            struct.pack("<4sII", b"glTF", 2, total),
            struct.pack("<I4s", len(json_chunk), b"JSON"),
            json_chunk,
            struct.pack("<I4s", len(binary), b"BIN\x00"),
            binary,
        )
    )


def _quat_z(degrees: float) -> tuple[float, float, float, float]:
    """The unit quaternion (x, y, z, w) for a rotation about Z, rounded for stable bytes."""
    half = math.radians(degrees) / 2
    return (0.0, 0.0, round(math.sin(half), 6), round(math.cos(half), 6))


def build_rig(clip: tuple[str, float, tuple[float, ...], int] | None) -> bytes:
    """A skinned triangle on a Hip -> Spine chain, with ``clip`` as its one animation if given."""
    positions = [0.0, 0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 1.0, 0.0]
    joints = [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0]
    weights = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
    # Column-major inverse bind matrices: identity for Hip, a -1 m Y translation for Spine.
    identity = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]
    spine = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, -1.0, 0, 1.0]
    views = [
        struct.pack("<9f", *positions),
        struct.pack("<12B", *joints),
        struct.pack("<12f", *weights),
        struct.pack("<32f", *identity, *spine),
        struct.pack("<3H", 0, 1, 2),
    ]
    accessors: list[dict[str, Any]] = [
        {
            "bufferView": 0,
            "componentType": _FLOAT,
            "count": 3,
            "type": "VEC3",
            "min": [0.0, 0.0, 0.0],
            "max": [0.2, 1.0, 0.0],
        },
        {"bufferView": 1, "componentType": _UBYTE, "count": 3, "type": "VEC4"},
        {"bufferView": 2, "componentType": _FLOAT, "count": 3, "type": "VEC4"},
        {"bufferView": 3, "componentType": _FLOAT, "count": 2, "type": "MAT4"},
        {"bufferView": 4, "componentType": _USHORT, "count": 3, "type": "SCALAR"},
    ]
    doc: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "nmg-game-dev tests/godot/make_probe_fixtures.py"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [
            {"name": "Armature", "children": [1, 3]},
            {"name": BONES[0], "children": [2]},
            {"name": BONES[1], "translation": [0.0, 1.0, 0.0]},
            {"name": "Body", "mesh": 0, "skin": 0},
        ],
        "skins": [{"joints": [1, 2], "skeleton": 1, "inverseBindMatrices": 3}],
        "meshes": [
            {
                "name": "Body",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "JOINTS_0": 1, "WEIGHTS_0": 2},
                        "indices": 4,
                        "mode": 4,
                    }
                ],
            }
        ],
    }
    if clip is not None:
        name, _fps, times, _frames = clip
        rotations = [_quat_z(angle) for angle in (0.0, 20.0, 0.0)]
        views.append(struct.pack(f"<{len(times)}f", *times))
        views.append(struct.pack(f"<{4 * len(rotations)}f", *(c for q in rotations for c in q)))
        accessors += [
            {
                "bufferView": 5,
                "componentType": _FLOAT,
                "count": len(times),
                "type": "SCALAR",
                "min": [min(times)],
                "max": [max(times)],
            },
            {"bufferView": 6, "componentType": _FLOAT, "count": len(rotations), "type": "VEC4"},
        ]
        doc["animations"] = [
            {
                "name": name,
                "samplers": [{"input": 5, "output": 6, "interpolation": "LINEAR"}],
                "channels": [
                    {"sampler": 0, "target": {"node": node, "path": "rotation"}} for node in (1, 2)
                ],
            }
        ]
    doc["accessors"] = accessors
    return _glb(doc, views)


def png_1x1(rgba: tuple[int, int, int, int]) -> bytes:
    """A 1x1 RGBA PNG."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    pixels = zlib.compress(b"\x00" + bytes(rgba), 9)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")
    )


def _json(data: object) -> bytes:
    return (json.dumps(data, indent=2) + "\n").encode()


def files() -> dict[Path, bytes]:
    """Every generated fixture file and its bytes."""
    out: dict[Path, bytes] = {ANIMS / "Rig.glb": build_rig(None)}
    for clip in CLIPS:
        path = ANIMS / f"A_Rig_{clip[0]}.glb"
        out[path] = build_rig(clip)
        out[path.with_name(path.name + ".import")] = f"[remap]\n\nimporter={IMPORTER}\n".encode()
    out[FIXTURE / "expected-anims.json"] = _json(
        {
            "params": {
                "clips": [
                    {"name": name, "path": f"res://anims/A_Rig_{name}.glb", "fps": fps}
                    for name, fps, _times, _frames in CLIPS
                ],
                "skeletons": ["res://anims/Rig.glb"],
            },
            "result": {
                "clips": {
                    name: {"animation": name, "frame_count": frames, "bones": list(BONES)}
                    for name, _fps, _times, frames in CLIPS
                },
                "skeletons": {"res://anims/Rig.glb": {"found": True, "bones": list(BONES)}},
            },
        }
    )

    chunk = f"{TERRAIN_NAME}_Chunk_0_0.glb"
    out[TERRAIN / chunk] = build_crate_glb()
    out[TERRAIN / f"T_{TERRAIN_NAME}_Splat.png"] = png_1x1((255, 0, 0, 0))
    for layer in TERRAIN_VARIANT.layers:
        for suffix, rgba in zip(
            TEXTURE_SUFFIXES,
            ((90, 140, 60, 255), (128, 128, 255, 255), (255, 200, 0, 255)),
            strict=True,
        ):
            out[TERRAIN / f"T_{TERRAIN_NAME}_{layer}_{suffix}.png"] = png_1x1(rgba)
    scene = render_scene(
        FIXTURE,
        TERRAIN,
        TERRAIN_NAME,
        TERRAIN_VARIANT,
        TERRAIN_HEIGHTS,
        {chunk: ["Crate"]},
    )
    out[TERRAIN / f"{TERRAIN_NAME}.tscn"] = scene.encode()
    out[FIXTURE / "expected-terrain.json"] = _json(
        {
            "params": {"mode": "scene", "scene": f"res://terrain/{TERRAIN_NAME}.tscn"},
            "result": {
                "chunks": 1,
                "height_min": TERRAIN_VARIANT.height_min_m,
                "height_max": TERRAIN_VARIANT.height_max_m,
                "mesh_height_min": -0.5,
                "mesh_height_max": 0.5,
            },
        }
    )
    return out


def main(argv: list[str]) -> int:
    generated = files()
    if "--check" in argv:
        stale = [
            path
            for path, data in generated.items()
            if not path.is_file() or path.read_bytes() != data
        ]
        for path in stale:
            print(
                f"{path} is stale; run uv run python -m tests.godot.make_probe_fixtures",
                file=sys.stderr,
            )
        return 1 if stale else 0
    for path, data in generated.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"Wrote {path.relative_to(FIXTURE.parent)} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
