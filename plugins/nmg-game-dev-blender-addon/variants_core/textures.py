"""Baked-material validation, Mobile texture downscaling, and PNG writing."""

from __future__ import annotations

from array import array
from collections.abc import Mapping
from pathlib import Path

import bpy

from .errors import VariantError

# Nodes allowed upstream of the Principled BSDF: sampled images, the normal map and
# channel split that feed ORM, the UV Map node that drives image sampling, and reroutes.
_ALLOWED_UPSTREAM = frozenset({"TEX_IMAGE", "NORMAL_MAP", "SEPARATE_COLOR", "UVMAP", "REROUTE"})


def check_baked_material(material: bpy.types.Material) -> None:
    """Raise variants.unbaked_material unless material is a baked, export-ready surface."""
    tree = material.node_tree
    bsdf = (
        next((node for node in tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
        if tree
        else None
    )
    if tree is None or bsdf is None:
        raise _unbaked(material.name, "has no Principled BSDF surface")

    stack = [link.from_node for socket in bsdf.inputs for link in socket.links]
    seen: set[str] = set()
    while stack:
        node = stack.pop()
        if node.name in seen:
            continue
        seen.add(node.name)
        if node.type not in _ALLOWED_UPSTREAM:
            raise _unbaked(
                material.name, f"feeds the surface from the {node.type} node '{node.name}'"
            )
        if node.type == "TEX_IMAGE" and node.image is None:
            raise _unbaked(material.name, f"has an Image Texture node '{node.name}' with no image")
        stack.extend(link.from_node for socket in node.inputs for link in socket.links)


def _unbaked(material_name: str, detail: str) -> VariantError:
    return VariantError(
        "variants.unbaked_material",
        f"Material '{material_name}' {detail}. Mobile and FBX export need a Principled BSDF "
        "fed only by Image Texture, Normal Map, and Separate Color nodes.",
        f"Bake '{material_name}' to T_<Name>_<Part>_BC/_N/_ORM images and rewire it to those "
        "images (the bake step, #67), then rerun.",
    )


def source_images(materials: list[bpy.types.Material]) -> dict[str, bpy.types.Image]:
    """Map image name to image for every Image Texture node in materials."""
    images: dict[str, bpy.types.Image] = {}
    for material in materials:
        for node in material.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None:
                images[node.image.name] = node.image
    return images


def mobile_image_copy(source: bpy.types.Image, max_px: int) -> bpy.types.Image:
    """Return a '_Mobile' copy of source scaled to min(size, max_px) on each axis."""
    width, height = source.size
    dst = bpy.data.images.new(
        f"{source.name}_Mobile",
        width=width,
        height=height,
        alpha=True,
        float_buffer=source.is_float,
    )
    dst.colorspace_settings.name = source.colorspace_settings.name
    pixels = array("f", [0.0]) * len(source.pixels)
    source.pixels.foreach_get(pixels)
    dst.pixels.foreach_set(pixels)
    target = (min(width, max_px), min(height, max_px))
    if target != (width, height):
        dst.scale(*target)
    # A generated image regenerates at its original size when the .blend is reloaded, and its
    # pixels are lost. Packing keeps the scaled size and pixels through save and reload (#69).
    dst.pack()
    return dst


def mobile_material_copy(
    source: bpy.types.Material, mobile_images: Mapping[str, bpy.types.Image]
) -> bpy.types.Material:
    """Return a '_Mobile' copy of source whose image nodes point at the mobile images."""
    copy = source.copy()
    copy.name = f"{source.name}_Mobile"
    for node in copy.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image is not None:
            node.image = mobile_images[node.image.name]
    return copy


def write_png(image: bpy.types.Image, path: Path) -> int:
    """Save image as a PNG at path and return the file size in bytes."""
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    return path.stat().st_size


def max_texture_px(images: list[bpy.types.Image]) -> int:
    return max((max(image.size) for image in images), default=0)
