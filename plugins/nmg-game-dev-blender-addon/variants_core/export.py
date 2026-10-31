"""FBX and PNG export for both variants, with identical object, material, and texture names."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import bpy

from .assets import (
    ARMATURE_EXPORT_NAME,
    asset_armature,
    desktop_export_objects,
    distinct_materials,
    mobile_collection_name,
    require_armature_name_free,
)
from .textures import source_images, write_png

_TEMP_PREFIX = "__nmg_tmp_"
_MOBILE_SUFFIX = "_Mobile"
_LOD_LEVELS = (1, 2)
_FBX_OPTIONS: dict[str, Any] = {
    "use_selection": True,
    "use_mesh_modifiers": True,
    "mesh_smooth_type": "FACE",
    "apply_scale_options": "FBX_SCALE_UNITS",
    "path_mode": "STRIP",
    "embed_textures": False,
}
_RIG_FBX_OPTIONS: dict[str, Any] = {
    **_FBX_OPTIONS,
    "add_leaf_bones": False,
    "use_armature_deform_only": True,
    "primary_bone_axis": "Y",
    "secondary_bone_axis": "X",
    "bake_anim": False,
}


def export_variants(collection_name: str, category: str, export_root: str) -> dict[str, Any]:
    """Write Desktop and Mobile FBX plus PNG textures; return paths and texture byte totals.

    A rigged asset (SK_<Name> in its collection) exports skinned: the armature is named Armature
    for the export, and Mobile writes one FBX per LOD level. An unrigged asset exports as before.
    """
    rig = asset_armature(collection_name)
    require_armature_name_free(rig)
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
    # Planned from the Mobile names before the export rename below replaces them.
    rigged_jobs = _rigged_mobile_jobs(rig, mobile_objects, mobile_dir, collection_name)

    desktop_fbx = desktop_dir / f"SM_{collection_name}.fbx"
    mobile_fbx = mobile_dir / f"SM_{collection_name}.fbx"
    options = _RIG_FBX_OPTIONS if rig is not None else _FBX_OPTIONS
    original_paths = {img.name: (img.filepath_raw, img.file_format) for img in desktop_images}
    restores: list[tuple[bpy.types.ID, str]] = []
    try:
        if rig is not None:
            restores.append((rig, rig.name))
            rig.name = ARMATURE_EXPORT_NAME
        desktop_bytes = sum(
            write_png(image, desktop_dir / f"{image.name}.png") for image in desktop_images
        )
        _select_only(desktop_objects)
        bpy.ops.export_scene.fbx(
            filepath=str(desktop_fbx), object_types={"MESH", "ARMATURE"}, **options
        )

        # The rig keeps its export name, so the Mobile FBX files name it the same way.
        restores += _rename(
            [obj for obj in desktop_objects if obj != rig] + desktop_materials + desktop_images,
            _to_temp,
        )
        restores += _rename(mobile_objects + mobile_materials + mobile_images, _unsuffixed)
        mobile_bytes = sum(
            write_png(image, mobile_dir / f"{image.name}.png") for image in mobile_images
        )
        if rigged_jobs is None:
            _select_only(mobile_objects)
            bpy.ops.export_scene.fbx(
                filepath=str(mobile_fbx),
                object_types={"EMPTY", "MESH", "ARMATURE"},
                **_FBX_OPTIONS,
            )
            mobile_files = [mobile_fbx]
        else:
            for path, objects in rigged_jobs:
                _select_only(objects)
                bpy.ops.export_scene.fbx(
                    filepath=str(path), object_types={"ARMATURE", "MESH"}, **_RIG_FBX_OPTIONS
                )
            mobile_files = [path for path, _objects in rigged_jobs]
    finally:
        for datablock, original_name in reversed(restores):
            datablock.name = original_name
        for image in desktop_images:
            image.filepath_raw, image.file_format = original_paths[image.name]

    return {
        "desktop_fbx": desktop_fbx,
        "mobile_fbx": mobile_fbx,
        "mobile_fbx_files": mobile_files,
        "rigged": rig is not None,
        "desktop_texture_bytes": desktop_bytes,
        "mobile_texture_bytes": mobile_bytes,
    }


def _rigged_mobile_jobs(
    rig: bpy.types.Object | None,
    mobile_objects: list[bpy.types.Object],
    mobile_dir: Path,
    collection_name: str,
) -> list[tuple[Path, list[bpy.types.Object]]] | None:
    """Plan one skinned FBX per Mobile LOD: the armature with LOD0 and any parts, then LOD1, LOD2.

    Returns None for an unrigged asset, which keeps its single Mobile FBX. A rigged asset without
    LOD1 and LOD2 (child parts) writes only the LOD0 file.
    """
    if rig is None:
        return None
    root_name = f"SM_{collection_name}{_MOBILE_SUFFIX}"
    lod_names = {level: f"{root_name}_LOD{level}" for level in _LOD_LEVELS}
    by_name = {obj.name: obj for obj in mobile_objects}
    base = [
        obj for obj in mobile_objects if obj.type == "MESH" and obj.name not in lod_names.values()
    ]
    jobs: list[tuple[Path, list[bpy.types.Object]]] = [
        (mobile_dir / f"SM_{collection_name}.fbx", [rig, *base])
    ]
    for level, name in lod_names.items():
        if name in by_name:
            jobs.append((mobile_dir / f"SM_{collection_name}_LOD{level}.fbx", [rig, by_name[name]]))
    return jobs


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
