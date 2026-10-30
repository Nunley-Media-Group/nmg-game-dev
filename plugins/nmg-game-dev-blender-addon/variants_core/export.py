"""FBX and PNG export for both variants, with identical object, material, and texture names."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import bpy

from .assets import desktop_export_objects, distinct_materials, mobile_collection_name
from .textures import source_images, write_png

_TEMP_PREFIX = "__nmg_tmp_"
_MOBILE_SUFFIX = "_Mobile"
_FBX_OPTIONS: dict[str, Any] = {
    "use_selection": True,
    "use_mesh_modifiers": True,
    "mesh_smooth_type": "FACE",
    "apply_scale_options": "FBX_SCALE_UNITS",
    "path_mode": "STRIP",
    "embed_textures": False,
}


def export_variants(collection_name: str, category: str, export_root: str) -> dict[str, Any]:
    """Write Desktop and Mobile FBX plus PNG textures; return paths and texture byte totals."""
    variant_root = Path(export_root) / category / collection_name
    desktop_dir = variant_root / "Desktop"
    mobile_dir = variant_root / "Mobile"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    mobile_dir.mkdir(parents=True, exist_ok=True)

    desktop_objects = desktop_export_objects(bpy.data.collections[collection_name])
    mobile_collection = bpy.data.collections[mobile_collection_name(collection_name)]
    mobile_objects = sorted(mobile_collection.all_objects, key=lambda obj: obj.name)
    desktop_materials = distinct_materials(desktop_objects)
    mobile_materials = distinct_materials(mobile_objects)
    desktop_images = _images_of(desktop_materials)
    mobile_images = _images_of(mobile_materials)

    desktop_fbx = desktop_dir / f"SM_{collection_name}.fbx"
    mobile_fbx = mobile_dir / f"SM_{collection_name}.fbx"
    original_paths = {img.name: (img.filepath_raw, img.file_format) for img in desktop_images}
    restores: list[tuple[bpy.types.ID, str]] = []
    try:
        desktop_bytes = sum(
            write_png(image, desktop_dir / f"{image.name}.png") for image in desktop_images
        )
        _select_only(desktop_objects)
        bpy.ops.export_scene.fbx(
            filepath=str(desktop_fbx), object_types={"MESH", "ARMATURE"}, **_FBX_OPTIONS
        )

        restores += _rename(desktop_objects + desktop_materials + desktop_images, _to_temp)
        restores += _rename(mobile_objects + mobile_materials + mobile_images, _unsuffixed)
        mobile_bytes = sum(
            write_png(image, mobile_dir / f"{image.name}.png") for image in mobile_images
        )
        _select_only(mobile_objects)
        bpy.ops.export_scene.fbx(
            filepath=str(mobile_fbx), object_types={"EMPTY", "MESH", "ARMATURE"}, **_FBX_OPTIONS
        )
    finally:
        for datablock, original_name in reversed(restores):
            datablock.name = original_name
        for image in desktop_images:
            image.filepath_raw, image.file_format = original_paths[image.name]

    return {
        "desktop_fbx": desktop_fbx,
        "mobile_fbx": mobile_fbx,
        "desktop_texture_bytes": desktop_bytes,
        "mobile_texture_bytes": mobile_bytes,
    }


def _images_of(materials: list[bpy.types.Material]) -> list[bpy.types.Image]:
    return sorted(source_images(materials).values(), key=lambda image: image.name)


def _rename(
    datablocks: list[Any], new_name: Callable[[str], str]
) -> list[tuple[bpy.types.ID, str]]:
    originals = [(datablock, datablock.name) for datablock in datablocks]
    for datablock in datablocks:
        datablock.name = new_name(datablock.name)
    return originals


def _to_temp(name: str) -> str:
    return f"{_TEMP_PREFIX}{name}"


def _unsuffixed(name: str) -> str:
    return name.replace(_MOBILE_SUFFIX, "", 1)


def _select_only(objects: list[bpy.types.Object]) -> None:
    view_layer = bpy.context.view_layer
    for obj in view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    view_layer.objects.active = objects[0] if objects else None
