"""The finalize ``import_godot`` step for a terrain asset (#249 FR4, AC4).

``import_terrain`` imports the project once, asks ``probe_terrain.gd`` (``mode: meshes``) for the
mesh nodes inside each chunk ``.glb``, writes one ``<Variant>/<Name>.tscn`` per variant, and checks
each scene with ``probe_terrain.gd`` (``mode: scene``). The scene is written after the import
because it needs the chunk mesh node paths, and a ``.tscn`` itself needs no import:

- The scene root is a ``Node3D`` named ``<Name>``. It instances every
  ``<Name>_Chunk_<row>_<col>.glb`` the export wrote (square chunks of ``CHUNK_QUADS`` quads) and
  overrides each chunk mesh's material with a ``ShaderMaterial`` that uses
  ``res://addons/nmg_game_dev/terrain/nmg_terrain.gdshader``: ``splat`` is the
  ``T_<Name>_Splat.png`` weightmap, ``layer<i>_{bc,n,orm}`` are layer *i*'s
  ``T_<Name>_<Layer>_{BC,N,ORM}.png``, and ``uv_scale`` is the terrain width over ``uv_tile_m``.
- A ``StaticBody3D``/``CollisionShape3D`` holds a ``HeightMapShape3D`` with
  ``map_width = map_depth = heightmap_px`` and ``map_data`` decoded from the 16-bit
  ``T_<Name>_Height.png`` in metres. The shape is scaled ``(spacing_m, 1, spacing_m)`` and, like the
  mesh, centred on the origin. Godot's heightmap rows run along +Z, which is Blender's -Y, so the
  PNG's row order (row 0 = Blender north = Godot -Z) is ``map_data``'s order.

The probe reports the chunk count, the ``map_data`` height range, and the union of the chunk
meshes' AABB Y extents. Either range differing from the sidecar's ``height_min_m``/``height_max_m``
by more than 0.05 m raises ``import_godot.terrain_height_mismatch``; a missing chunk raises
``import_godot.mismatch``.
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from nmg_game_dev.pipeline.errors import PipelineError

from .project import godot_string, res_path
from .runner import GodotRunner, import_project, run_probe

VARIANTS: Final = ("Desktop", "Mobile")
CHUNK_QUADS: Final = 63
MAX_LAYERS: Final = 4
HEIGHT_TOLERANCE_M: Final = 0.05
HEIGHT_CODE_MAX: Final = 65535
SHADER_PATH: Final = "res://addons/nmg_game_dev/terrain/nmg_terrain.gdshader"
PROBE: Final = "probe_terrain.gd"
TEXTURE_SUFFIXES: Final = ("BC", "N", "ORM")
_STAGE: Final = "import_godot"
_PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
_HEIGHT_REMEDIATION: Final = (
    "The imported terrain does not reproduce the Blender heightfield within 0.05 m. Re-export the "
    "terrain and rerun import_godot. If it persists, check T_<Name>_Height.png (0 is the minimum "
    "height, 65535 the maximum) against height_min_m and height_max_m in nmg-variants.json."
)
_EXPORT_REMEDIATION: Final = (
    "Rerun the export step so the variant folder holds every <Name>_Chunk_<row>_<col>.glb, "
    "T_<Name>_Height.png, T_<Name>_Splat.png and the layer textures, then rerun import_godot."
)


@dataclass(frozen=True)
class TerrainVariant:
    """The sidecar fields one terrain variant's scene needs."""

    heightmap_px: int
    spacing_m: float
    height_min_m: float
    height_max_m: float
    uv_tile_m: float
    layers: tuple[str, ...]

    @property
    def uv_scale(self) -> float:
        """Layer repeats across the terrain: its width in metres over ``uv_tile_m``.

        The shader samples the splat with the mesh UV (0 to 1 across the whole terrain) and the
        layer textures with ``UV * uv_scale``, so each texture repeat spans ``uv_tile_m`` metres.
        """
        return (self.heightmap_px - 1) * self.spacing_m / self.uv_tile_m

    @property
    def chunks_per_side(self) -> int:
        """The chunk grid size: ``ceil((heightmap_px - 1) / CHUNK_QUADS)``."""
        return max(1, -(-(self.heightmap_px - 1) // CHUNK_QUADS))


def parse_variant(sidecar: Mapping[str, Any], variant: str) -> TerrainVariant:
    """Read one variant's terrain entry from ``nmg-variants.json``, or raise ``mismatch``."""
    entry = sidecar.get(variant.lower())
    if not isinstance(entry, dict):
        raise _export_error(f"nmg-variants.json has no {variant.lower()} terrain entry")
    fields = cast(dict[str, Any], entry)
    try:
        heightmap_px = fields["heightmap_px"]
        if isinstance(heightmap_px, bool) or not isinstance(heightmap_px, int) or heightmap_px < 2:
            raise ValueError("heightmap_px must be an integer of at least 2")
        numbers = {
            key: float(fields[key])
            for key in ("spacing_m", "height_min_m", "height_max_m", "uv_tile_m")
        }
        layers = fields["layers"]
        if not isinstance(layers, list) or not layers:
            raise ValueError("layers must be a non-empty list")
    except (KeyError, TypeError, ValueError) as error:
        raise _export_error(f"the {variant} terrain entry is not usable: {error}") from error
    if numbers["spacing_m"] <= 0 or numbers["uv_tile_m"] <= 0:
        raise _export_error(f"the {variant} terrain spacing_m and uv_tile_m must be positive")
    names = tuple(str(layer) for layer in cast(list[object], layers))
    if len(names) > MAX_LAYERS:
        raise _export_error(
            f"the {variant} terrain has {len(names)} layers; the splat shader takes {MAX_LAYERS}"
        )
    return TerrainVariant(
        heightmap_px=heightmap_px,
        spacing_m=numbers["spacing_m"],
        height_min_m=numbers["height_min_m"],
        height_max_m=numbers["height_max_m"],
        uv_tile_m=numbers["uv_tile_m"],
        layers=names,
    )


def chunk_names(name: str, terrain: TerrainVariant) -> list[str]:
    """Return the chunk file names the export writes, row-major."""
    side = terrain.chunks_per_side
    return [f"{name}_Chunk_{row}_{col}.glb" for row in range(side) for col in range(side)]


def read_png_gray16(path: Path) -> tuple[int, int, list[int]]:
    """Return ``(width, height, codes)`` for a non-interlaced 16-bit grayscale PNG."""
    data = path.read_bytes()
    if not data.startswith(_PNG_SIGNATURE):
        raise ValueError(f"{path} is not a PNG file")
    position = len(_PNG_SIGNATURE)
    header: bytes | None = None
    compressed = bytearray()
    while position + 8 <= len(data):
        (length,) = struct.unpack_from(">I", data, position)
        kind = data[position + 4 : position + 8]
        body = data[position + 8 : position + 8 + length]
        position += 12 + length
        if kind == b"IHDR":
            header = body
        elif kind == b"IDAT":
            compressed += body
        elif kind == b"IEND":
            break
    if header is None:
        raise ValueError(f"{path} has no IHDR chunk")
    width, height, depth, color, _compression, _filter, interlace = struct.unpack(
        ">IIBBBBB", header
    )
    if depth != 16 or color != 0 or interlace != 0:
        raise ValueError(f"{path} is not a non-interlaced 16-bit grayscale PNG")
    raw = zlib.decompress(bytes(compressed))
    stride = width * 2
    rows: list[bytes] = []
    previous = bytearray(stride)
    offset = 0
    for _row in range(height):
        filter_type = raw[offset]
        line = bytearray(raw[offset + 1 : offset + 1 + stride])
        offset += 1 + stride
        _unfilter(filter_type, line, previous, 2)
        rows.append(bytes(line))
        previous = line
    joined = b"".join(rows)
    codes = list(struct.unpack(f">{width * height}H", joined))
    return width, height, codes


def _unfilter(kind: int, line: bytearray, previous: bytearray, bpp: int) -> None:
    for index in range(len(line)):
        left = line[index - bpp] if index >= bpp else 0
        up = previous[index]
        if kind == 0:
            continue
        if kind == 1:
            line[index] = (line[index] + left) & 0xFF
        elif kind == 2:
            line[index] = (line[index] + up) & 0xFF
        elif kind == 3:
            line[index] = (line[index] + (left + up) // 2) & 0xFF
        elif kind == 4:
            upper_left = previous[index - bpp] if index >= bpp else 0
            estimate = left + up - upper_left
            pa, pb, pc = abs(estimate - left), abs(estimate - up), abs(estimate - upper_left)
            predictor = left if pa <= pb and pa <= pc else up if pb <= pc else upper_left
            line[index] = (line[index] + predictor) & 0xFF
        else:
            raise ValueError(f"unknown PNG filter type {kind}")


def decode_heights(path: Path, terrain: TerrainVariant) -> list[float]:
    """Decode ``T_<Name>_Height.png`` into ``heightmap_px²`` heights in metres, row-major."""
    try:
        width, height, codes = read_png_gray16(path)
    except (OSError, ValueError, zlib.error, struct.error) as error:
        raise _export_error(f"the heightmap {path} cannot be read: {error}") from error
    if width != terrain.heightmap_px or height != terrain.heightmap_px:
        raise _export_error(
            f"the heightmap {path.name} is {width}x{height}; nmg-variants.json says "
            f"{terrain.heightmap_px}"
        )
    span = terrain.height_max_m - terrain.height_min_m
    return [terrain.height_min_m + code / HEIGHT_CODE_MAX * span for code in codes]


def render_scene(
    project: Path,
    folder: Path,
    name: str,
    terrain: TerrainVariant,
    heights: Sequence[float],
    mesh_paths: Mapping[str, Sequence[str]],
) -> str:
    """Return the ``<Name>.tscn`` text for one terrain variant (Godot ``format=3``).

    ``mesh_paths`` maps each chunk file name to the paths of its ``MeshInstance3D`` nodes relative
    to the chunk scene root; each gets the terrain ``ShaderMaterial`` as ``material_override``.
    """
    chunks = [chunk[: -len(".glb")] for chunk in chunk_names(name, terrain)]
    ext: list[tuple[str, str, str]] = []
    for chunk in chunks:
        ext.append(("PackedScene", res_path(project, folder / f"{chunk}.glb"), f"chunk_{chunk}"))
    ext.append(("Shader", SHADER_PATH, "shader"))
    ext.append(("Texture2D", res_path(project, folder / f"T_{name}_Splat.png"), "splat"))
    for index, layer in enumerate(terrain.layers):
        for suffix in TEXTURE_SUFFIXES:
            texture = folder / f"T_{name}_{layer}_{suffix}.png"
            ext.append(("Texture2D", res_path(project, texture), f"layer{index}_{suffix.lower()}"))

    lines = [f"[gd_scene load_steps={len(ext) + 3} format=3]", ""]
    for kind, resource, ident in ext:
        lines.append(f'[ext_resource type="{kind}" path={godot_string(resource)} id="{ident}"]')
    lines += [
        "",
        '[sub_resource type="ShaderMaterial" id="ShaderMaterial_terrain"]',
        'shader = ExtResource("shader")',
        'shader_parameter/splat = ExtResource("splat")',
        f"shader_parameter/uv_scale = {_num(terrain.uv_scale)}",
    ]
    for index in range(len(terrain.layers)):
        for suffix in TEXTURE_SUFFIXES:
            key = f"layer{index}_{suffix.lower()}"
            lines.append(f'shader_parameter/{key} = ExtResource("{key}")')
    data = ", ".join(_num(value) for value in heights)
    lines += [
        "",
        '[sub_resource type="HeightMapShape3D" id="HeightMapShape3D_terrain"]',
        f"map_width = {terrain.heightmap_px}",
        f"map_depth = {terrain.heightmap_px}",
        f"map_data = PackedFloat32Array({data})",
        "",
        f'[node name={godot_string(name)} type="Node3D"]',
    ]
    for chunk in chunks:
        lines += [
            "",
            f'[node name={godot_string(chunk)} parent="." instance=ExtResource("chunk_{chunk}")]',
        ]
        for mesh in mesh_paths.get(f"{chunk}.glb", ()):
            parent, _, leaf = mesh.rpartition("/")
            owner = f"{chunk}/{parent}" if parent else chunk
            lines += [
                "",
                f"[node name={godot_string(leaf)} parent={godot_string(owner)}]",
                'material_override = SubResource("ShaderMaterial_terrain")',
            ]
    spacing = _num(terrain.spacing_m)
    lines += [
        "",
        '[node name="Collision" type="StaticBody3D" parent="."]',
        "",
        '[node name="HeightMap" type="CollisionShape3D" parent="Collision"]',
        f"transform = Transform3D({spacing}, 0, 0, 0, 1, 0, 0, 0, {spacing}, 0, 0, 0)",
        'shape = SubResource("HeightMapShape3D_terrain")',
        "",
    ]
    return "\n".join(lines)


def import_terrain(
    runner: GodotRunner,
    project: Path,
    *,
    name: str,
    variant_dirs: Mapping[str, Path],
    sidecar: Mapping[str, Any],
    timeout: float | None = None,
) -> dict[str, dict[str, Any]]:
    """Import once, write both terrain scenes, and probe each. Returns per-variant results.

    Both sidecar entries, every chunk file and both heightmaps are checked before Godot runs or
    anything is written, so a broken Mobile export fails before the Desktop scene changes.
    """
    plans: dict[str, tuple[TerrainVariant, Path]] = {}
    for variant in VARIANTS:
        terrain = parse_variant(sidecar, variant)
        folder = variant_dirs[variant]
        missing = [chunk for chunk in chunk_names(name, terrain) if not (folder / chunk).is_file()]
        if missing:
            raise PipelineError(
                code="import_godot.mismatch",
                message=f"{variant} terrain chunk {missing[0]} is missing from {folder} "
                f"({len(missing)} of {terrain.chunks_per_side**2} missing).",
                remediation=_EXPORT_REMEDIATION,
                stage=_STAGE,
            )
        plans[variant] = (terrain, folder)

    heights = {
        variant: decode_heights(folder / f"T_{name}_Height.png", terrain)
        for variant, (terrain, folder) in plans.items()
    }

    import_project(runner, project, timeout=timeout)

    glbs = {
        res_path(project, folder / chunk): (variant, chunk)
        for variant, (terrain, folder) in plans.items()
        for chunk in chunk_names(name, terrain)
    }
    listed = run_probe(
        runner,
        project,
        PROBE,
        {"mode": "meshes", "glbs": sorted(glbs)},
        error_code="import_godot.import_failed",
        timeout=timeout,
    ).get("meshes")
    found: dict[str, Any] = cast(dict[str, Any], listed) if isinstance(listed, dict) else {}
    mesh_paths: dict[str, dict[str, list[str]]] = {variant: {} for variant in plans}
    for resource, (variant, chunk) in sorted(glbs.items()):
        paths = found.get(resource)
        if not isinstance(paths, list) or not paths:
            raise PipelineError(
                code="import_godot.mismatch",
                message=f"{variant} terrain chunk {chunk} imported with no mesh.",
                remediation=_EXPORT_REMEDIATION,
                stage=_STAGE,
            )
        mesh_paths[variant][chunk] = [str(path) for path in cast(list[object], paths)]

    scenes: dict[str, str] = {}
    for variant, (terrain, folder) in plans.items():
        scene = folder / f"{name}.tscn"
        text = render_scene(project, folder, name, terrain, heights[variant], mesh_paths[variant])
        if not scene.is_file() or scene.read_text(encoding="utf-8") != text:
            scene.write_text(text, encoding="utf-8")
        scenes[variant] = res_path(project, scene)

    results: dict[str, dict[str, Any]] = {}
    for variant, (terrain, _folder) in plans.items():
        probe = run_probe(
            runner,
            project,
            PROBE,
            {"mode": "scene", "scene": scenes[variant]},
            error_code="import_godot.import_failed",
            timeout=timeout,
        )
        check_probe(variant, terrain, probe)
        results[variant] = {
            "resource_path": scenes[variant],
            "chunks": int(probe["chunks"]),
            "height_min": float(probe["height_min"]),
            "height_max": float(probe["height_max"]),
            "mesh_height_min": float(probe["mesh_height_min"]),
            "mesh_height_max": float(probe["mesh_height_max"]),
        }
    return results


def check_probe(variant: str, terrain: TerrainVariant, probe: Mapping[str, Any]) -> None:
    """Compare a ``probe_terrain.gd`` result with the sidecar; raise on any difference."""
    try:
        chunks = int(probe["chunks"])
        ranges = {
            "collision": (float(probe["height_min"]), float(probe["height_max"])),
            "mesh": (float(probe["mesh_height_min"]), float(probe["mesh_height_max"])),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise PipelineError(
            code="import_godot.import_failed",
            message=f"The {variant} terrain probe result is incomplete: {error}",
            remediation="Read the Godot output, confirm probe_terrain.gd ran on the scene, then "
            "rerun import_godot.",
            stage=_STAGE,
        ) from error
    expected_chunks = terrain.chunks_per_side**2
    if chunks != expected_chunks:
        raise PipelineError(
            code="import_godot.mismatch",
            message=f"{variant} terrain scene instances {chunks} chunk(s); the export wrote "
            f"{expected_chunks}.",
            remediation=_EXPORT_REMEDIATION,
            stage=_STAGE,
        )
    for label, (low, high) in ranges.items():
        error_m = max(abs(low - terrain.height_min_m), abs(high - terrain.height_max_m))
        if error_m > HEIGHT_TOLERANCE_M:
            raise PipelineError(
                code="import_godot.terrain_height_mismatch",
                message=f"The {variant} terrain {label} height range is {low:.3f} to {high:.3f} m; "
                f"the heightfield is {terrain.height_min_m:.3f} to {terrain.height_max_m:.3f} m "
                f"(off by {error_m:.3f} m, limit {HEIGHT_TOLERANCE_M:g} m).",
                remediation=_HEIGHT_REMEDIATION,
                stage=_STAGE,
            )


def _export_error(message: str) -> PipelineError:
    return PipelineError(
        code="import_godot.mismatch",
        message=f"The terrain export is not usable: {message}.",
        remediation=_EXPORT_REMEDIATION,
        stage=_STAGE,
    )


def _num(value: float) -> str:
    text = format(round(value, 5), ".10g")
    return "0" if text == "-0" else text


__all__ = [
    "CHUNK_QUADS",
    "HEIGHT_TOLERANCE_M",
    "SHADER_PATH",
    "TerrainVariant",
    "check_probe",
    "chunk_names",
    "decode_heights",
    "import_terrain",
    "parse_variant",
    "read_png_gray16",
    "render_scene",
]
