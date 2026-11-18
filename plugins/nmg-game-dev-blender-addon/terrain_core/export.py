"""Terrain variant export: chunk meshes, heightmap, splat map, and layer textures (#154, #249).

Each variant folder gets:

- ``<Name>_Chunk_<row>_<col>.glb``: the heightfield cut into square chunks of ``CHUNK_QUADS``
  quads per side. Row 0 / column 0 is the Blender +Y / -X corner, the same order as the grid.
  Every chunk sits in world space (object at the origin), with smooth normals taken from the
  whole grid so chunk seams shade continuously, and one UV map that addresses the splat map's
  pixel centres across the whole terrain (``u = (col + 0.5) / n``, image row ``row``).
- ``T_<Name>_Height.png``: the 16-bit heightmap the re-import check decodes.
- ``T_<Name>_Splat.png``: an 8-bit RGBA weightmap, layer *i* in channel *i*, unused channels 0,
  every pixel summing to 255 over the layers.
- ``T_<Name>_<Layer>_{BC,N,ORM}.png`` for each kept layer.

The Mobile textures are copies scaled to the Mobile maximum, so the scene keeps its Desktop
images. Nothing is written when the caller has not validated the terrain first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import bpy
import numpy as np

from ..contract_core.terrain import TEXTURE_SUFFIXES
from ..variants_core.errors import VariantError
from ..variants_core.export import STATIC_GLB_OPTIONS
from ..variants_core.textures import mobile_image_copy, source_images, write_png
from .heightfield import (
    CHUNK_QUADS,
    SPLAT_CHANNELS,
    chunk_name,
    encode_heights,
    quantize_weights,
    splat_pixels,
    write_png_gray16,
    write_png_rgba8,
)
from .variants import DESKTOP, MOBILE, TerrainVariant

_SCRATCH_COLLECTION: Final = "__nmg_terrain_chunks"


def export_terrain(
    collection_name: str,
    category: str,
    export_root: str,
    variants: dict[str, TerrainVariant],
) -> dict[str, Any]:
    """Write the Desktop and Mobile folders; return their paths and texture byte totals.

    Raises VariantError ``variants.terrain_layers_unsupported`` before any write when a variant
    keeps more layers than the splat map has channels.
    """
    for label, variant in ((DESKTOP, variants[DESKTOP]), (MOBILE, variants[MOBILE])):
        _require_splat_layers(collection_name, label, variant)
    root = Path(export_root) / category / collection_name
    result: dict[str, Any] = {}
    for label, mobile in ((DESKTOP, False), (MOBILE, True)):
        folder = root / label
        folder.mkdir(parents=True, exist_ok=True)
        variant = variants[label]
        key = label.lower()
        result[f"{key}_texture_bytes"] = _write_textures(
            collection_name, variant, folder, mobile=mobile
        )
        result[f"{key}_chunks"] = _write_chunks(collection_name, variant, folder)
        result[f"{key}_heightmap"] = folder / f"T_{collection_name}_Height.png"
        result[f"{key}_splat"] = folder / f"T_{collection_name}_Splat.png"
    return result


def _require_splat_layers(name: str, label: str, variant: TerrainVariant) -> None:
    if len(variant.layers) <= SPLAT_CHANNELS:
        return
    raise VariantError(
        "variants.terrain_layers_unsupported",
        f"The {label} variant of {name} keeps {len(variant.layers)} layers; the splat map holds "
        f"at most {SPLAT_CHANNELS}.",
        f"Merge or remove paint layers so {name} has at most {SPLAT_CHANNELS}, or lower the "
        "terrain layers budget, then rerun the export step.",
    )


def _write_textures(name: str, variant: TerrainVariant, folder: Path, *, mobile: bool) -> int:
    """Write one variant's heightmap, splat map, and layer textures; return the bytes written."""
    n = variant.heightmap_px
    total = 0

    height_path = folder / f"T_{name}_Height.png"
    height_bytes, _zmin, _zmax = encode_heights(variant.heights, n)
    write_png_gray16(height_bytes, n, n, height_path)
    total += height_path.stat().st_size

    splat_path = folder / f"T_{name}_Splat.png"
    write_png_rgba8(splat_pixels(quantize_weights(variant.weights)), n, n, splat_path)
    total += splat_path.stat().st_size

    for layer in variant.layers:
        for source in _layer_images(name, layer):
            path = folder / f"{source.name}.png"
            if mobile:
                copy = mobile_image_copy(source, variant.texture_px[layer])
                try:
                    total += write_png(copy, path)
                finally:
                    bpy.data.images.remove(copy)
            else:
                total += _save_keeping_path(source, path)
    return total


def _write_chunks(name: str, variant: TerrainVariant, folder: Path) -> list[Path]:
    """Cut the variant heightfield into chunk meshes and write one GLB per chunk, row-major."""
    n = variant.heightmap_px
    spacing = variant.spacing_m
    heights = np.asarray(variant.heights, dtype=np.float64).reshape(n, n)
    normals = _grid_normals(heights, spacing)
    count = (n - 1) // CHUNK_QUADS
    scratch = bpy.data.collections.new(_SCRATCH_COLLECTION)
    bpy.context.scene.collection.children.link(scratch)
    paths: list[Path] = []
    try:
        for row in range(count):
            for col in range(count):
                obj = _chunk_object(name, row, col, heights, normals, spacing, scratch)
                path = folder / f"{chunk_name(name, row, col)}.glb"
                try:
                    _select_only([obj])
                    bpy.ops.export_scene.gltf(filepath=str(path), **STATIC_GLB_OPTIONS)
                finally:
                    mesh = obj.data
                    bpy.data.objects.remove(obj)
                    bpy.data.meshes.remove(mesh)
                    # Background Blender keeps a stale view-layer entry until it is updated.
                    bpy.context.view_layer.update()
                paths.append(path)
    finally:
        bpy.data.collections.remove(scratch)
    return paths


def _chunk_object(
    name: str,
    row: int,
    col: int,
    heights: np.ndarray,
    normals: np.ndarray,
    spacing: float,
    scratch: bpy.types.Collection,
) -> bpy.types.Object:
    """Build chunk (row, col) as a world-space mesh object linked into scratch."""
    n = heights.shape[0]
    side = CHUNK_QUADS + 1
    rows = np.arange(row * CHUNK_QUADS, row * CHUNK_QUADS + side)
    cols = np.arange(col * CHUNK_QUADS, col * CHUNK_QUADS + side)
    grid_rows, grid_cols = np.meshgrid(rows, cols, indexing="ij")
    half = (n - 1) * spacing / 2
    coords = np.stack(
        [
            -half + grid_cols * spacing,
            half - grid_rows * spacing,
            heights[grid_rows, grid_cols],
        ],
        axis=-1,
    ).reshape(-1, 3)

    quad_rows, quad_cols = np.meshgrid(
        np.arange(CHUNK_QUADS), np.arange(CHUNK_QUADS), indexing="ij"
    )
    corner = (quad_rows * side + quad_cols).ravel()
    # Counter-clockwise seen from +Z: down a row, across a column, back up.
    loops = np.stack([corner, corner + side, corner + side + 1, corner + 1], axis=1).ravel()
    quads = CHUNK_QUADS * CHUNK_QUADS

    mesh = bpy.data.meshes.new(chunk_name(name, row, col))
    mesh.vertices.add(side * side)
    mesh.vertices.foreach_set("co", coords.astype(np.float32).ravel())
    mesh.loops.add(loops.size)
    mesh.loops.foreach_set("vertex_index", loops.astype(np.int32))
    mesh.polygons.add(quads)
    mesh.polygons.foreach_set("loop_start", np.arange(0, loops.size, 4, dtype=np.int32))
    mesh.polygons.foreach_set("use_smooth", np.ones(quads, dtype=bool))
    mesh.update(calc_edges=True)

    vertex_rows = grid_rows.ravel()[loops]
    vertex_cols = grid_cols.ravel()[loops]
    # Blender's V runs up the image and the GLB writer flips it, so image row r sits at 1 - v.
    uvs = np.stack([(vertex_cols + 0.5) / n, 1.0 - (vertex_rows + 0.5) / n], axis=1)
    layer = mesh.uv_layers.new(name="UVMap")
    layer.data.foreach_set("uv", uvs.astype(np.float32).ravel())
    mesh.normals_split_custom_set_from_vertices(
        normals[grid_rows, grid_cols].reshape(-1, 3).tolist()
    )

    obj = bpy.data.objects.new(chunk_name(name, row, col), mesh)
    scratch.objects.link(obj)
    return obj


def _grid_normals(heights: np.ndarray, spacing: float) -> np.ndarray:
    """Unit vertex normals of the whole heightfield (n, n, 3), from central differences.

    x grows with the column and y falls with the row, so dz/dy is minus the per-row slope.
    """
    if heights.shape[0] < 2:
        flat = np.zeros((*heights.shape, 3))
        flat[..., 2] = 1.0
        return flat
    slope_row, slope_col = np.gradient(heights, spacing)
    normals = np.stack([-slope_col, slope_row, np.ones_like(heights)], axis=-1)
    lengths = np.linalg.norm(normals, axis=-1, keepdims=True)
    result: np.ndarray = normals / lengths
    return result


def _select_only(objects: list[bpy.types.Object]) -> None:
    view_layer = bpy.context.view_layer
    for obj in view_layer.objects:
        if obj is not None:
            obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    view_layer.objects.active = objects[0] if objects else None


def _layer_images(name: str, layer: str) -> list[bpy.types.Image]:
    """The layer's BC, N, and ORM images, found through its material M_<Name>_<Layer>."""
    material = bpy.data.materials.get(f"M_{name}_{layer}")
    if material is None:
        raise VariantError(
            "variants.terrain_material_missing",
            f"No material M_{name}_{layer} holds the {layer} layer's textures.",
            "Map each Layer_<LayerName> to its own baked material, then rerun the variants step.",
        )
    images = source_images([material])
    picked: list[bpy.types.Image] = []
    for suffix in TEXTURE_SUFFIXES:
        image = images.get(f"T_{name}_{layer}_{suffix}")
        if image is None:
            raise VariantError(
                "variants.terrain_texture_missing",
                f"M_{name}_{layer} does not sample T_{name}_{layer}_{suffix}.",
                "Bake the terrain layer so its BC, N, and ORM images exist, then rerun.",
            )
        picked.append(image)
    return picked


def _save_keeping_path(image: bpy.types.Image, path: Path) -> int:
    """Save a Desktop image as PNG and restore its original file path and format afterwards."""
    original = (image.filepath_raw, image.file_format)
    try:
        return write_png(image, path)
    finally:
        image.filepath_raw, image.file_format = original
