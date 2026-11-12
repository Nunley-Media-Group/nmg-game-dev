"""PNG export for the terrain variants: heightmap, weightmaps, and layer textures (#154, AC2, FR4).

Each variant folder gets T_<Name>_Height.png (16-bit), one T_<Name>_Layer_<L>.png weightmap per
kept layer (8-bit, summing to 255 per pixel), and each kept layer's T_<Name>_<L>_{BC,N,ORM}.png
textures. The Mobile textures are copies scaled to the Mobile maximum, so the scene keeps its
Desktop images. Nothing is written when the caller has not validated the terrain first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import bpy

from ..contract_core.terrain import TEXTURE_SUFFIXES
from ..variants_core.errors import VariantError
from ..variants_core.textures import mobile_image_copy, source_images, write_png
from .heightfield import encode_heights, quantize_weights, write_png_gray8, write_png_gray16
from .variants import DESKTOP, MOBILE, TerrainVariant


def export_terrain(
    collection_name: str,
    category: str,
    export_root: str,
    variants: dict[str, TerrainVariant],
) -> dict[str, Any]:
    """Write the Desktop and Mobile PNG folders; return their paths and texture byte totals."""
    root = Path(export_root) / category / collection_name
    desktop_dir = root / DESKTOP
    mobile_dir = root / MOBILE
    desktop_dir.mkdir(parents=True, exist_ok=True)
    mobile_dir.mkdir(parents=True, exist_ok=True)
    desktop_bytes = _write_variant(collection_name, variants[DESKTOP], desktop_dir, mobile=False)
    mobile_bytes = _write_variant(collection_name, variants[MOBILE], mobile_dir, mobile=True)
    return {
        "desktop_texture_bytes": desktop_bytes,
        "mobile_texture_bytes": mobile_bytes,
        "desktop_heightmap": desktop_dir / f"T_{collection_name}_Height.png",
        "mobile_heightmap": mobile_dir / f"T_{collection_name}_Height.png",
    }


def _write_variant(name: str, variant: TerrainVariant, folder: Path, *, mobile: bool) -> int:
    """Write one variant's heightmap, weightmaps, and layer textures; return the bytes written."""
    n = variant.heightmap_px
    total = 0

    height_path = folder / f"T_{name}_Height.png"
    height_bytes, _zmin, _zmax = encode_heights(variant.heights, n)
    write_png_gray16(height_bytes, n, n, height_path)
    total += height_path.stat().st_size

    for layer, codes in zip(variant.layers, quantize_weights(variant.weights), strict=True):
        path = folder / f"T_{name}_Layer_{layer}.png"
        write_png_gray8(codes, n, n, path)
        total += path.stat().st_size

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
