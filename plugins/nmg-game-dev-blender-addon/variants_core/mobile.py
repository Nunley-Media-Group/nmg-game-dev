"""Mobile build: copy the Desktop hierarchy, decimate to budget, and wrap LODs in a group."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import bpy

from .assets import asset_meshes, distinct_materials, mobile_collection_name, require_asset
from .meshes import evaluated_mesh, fit_meshes, replace_mesh, triangle_count
from .textures import max_texture_px, mobile_image_copy, mobile_material_copy, source_images


def build_mobile(collection_name: str, budget: Mapping[str, int]) -> dict[str, Any]:
    """Rebuild <Name>_Mobile from the Desktop asset. Caller must validate inputs first."""
    collection, root = require_asset(collection_name)
    mobile_name = mobile_collection_name(collection_name)
    _remove_previous_mobile(mobile_name)

    sources = asset_meshes(collection)
    materials = distinct_materials(sources)
    mobile_images = {
        name: mobile_image_copy(image, budget["max_texture_px"])
        for name, image in sorted(source_images(materials).items())
    }
    mobile_materials = {
        material.name: mobile_material_copy(material, mobile_images) for material in materials
    }

    mobile_collection = bpy.data.collections.new(mobile_name)
    bpy.context.scene.collection.children.link(mobile_collection)
    copies = _copy_objects(sources, mobile_materials, mobile_collection)

    root_copy = copies[root.name]
    parts = [copies[src.name] for src in sources if src.name != root.name]
    if parts:
        lod_tris = [_fit_objects([root_copy, *parts], budget["tris"], mobile_name)]
    else:
        lod_tris = _build_lod_group(root_copy, budget["tris"], mobile_collection, collection_name)

    return {
        "collection": mobile_name,
        "root": f"SM_{collection_name}_Mobile",
        "lod_levels": len(lod_tris),
        "lod_tris": lod_tris,
        "tris": lod_tris[0],
        "materials": len(mobile_materials),
        "max_texture_px": max_texture_px(list(mobile_images.values())),
        "budget": dict(budget),
    }


def _copy_objects(
    sources: list[bpy.types.Object],
    mobile_materials: Mapping[str, bpy.types.Material],
    mobile_collection: bpy.types.Collection,
) -> dict[str, bpy.types.Object]:
    copies: dict[str, bpy.types.Object] = {}
    for src in sources:
        mesh = evaluated_mesh(src)
        for index, material in enumerate(mesh.materials):
            if material is not None:
                mesh.materials[index] = mobile_materials[material.name]
        obj = bpy.data.objects.new(f"{src.name}_Mobile", mesh)
        mobile_collection.objects.link(obj)
        copies[src.name] = obj

    for src in sources:
        obj = copies[src.name]
        parent = copies.get(src.parent.name) if src.parent is not None else None
        if parent is not None:
            obj.parent = parent
            obj.matrix_parent_inverse = src.matrix_parent_inverse.copy()
            obj.matrix_basis = src.matrix_basis.copy()
        else:
            obj.matrix_world = src.matrix_world.copy()
    return copies


def _fit_objects(objects: list[bpy.types.Object], target: int, label: str) -> int:
    """Decimate every object's mesh so the group totals at most target; return the total."""
    fitted = fit_meshes([obj.data for obj in objects], target, label)
    for obj, mesh in zip(objects, fitted, strict=True):
        replace_mesh(obj, mesh)
    return sum(triangle_count(obj.data) for obj in objects)


def _build_lod_group(
    root: bpy.types.Object,
    budget_tris: int,
    mobile_collection: bpy.types.Collection,
    asset_name: str,
) -> list[int]:
    """LOD0 at budget, LOD1 at 50%, LOD2 at 25%, parented under an Empty LodGroup.

    Returns the triangle count of each LOD level, LOD0 first.
    """
    group_name = f"SM_{asset_name}_Mobile"
    (lod0,) = fit_meshes([root.data], budget_tris, group_name)
    replace_mesh(root, lod0)
    lod0_tris = triangle_count(lod0)
    lod1 = fit_meshes([lod0], lod0_tris // 2, f"{group_name} LOD1")[0]
    lod2 = fit_meshes([lod0], lod0_tris // 4, f"{group_name} LOD2")[0]

    root.name = f"{group_name}_LOD0"
    group = bpy.data.objects.new(group_name, None)
    group.empty_display_type = "PLAIN_AXES"
    group["fbx_type"] = "LodGroup"
    group.matrix_world = root.matrix_world.copy()
    mobile_collection.objects.link(group)

    lods = [root]
    for level, mesh in ((1, lod1), (2, lod2)):
        obj = bpy.data.objects.new(f"{group_name}_LOD{level}", mesh)
        mobile_collection.objects.link(obj)
        lods.append(obj)
    for obj in lods:
        obj.parent = group
        obj.matrix_parent_inverse = group.matrix_world.inverted()
    return [triangle_count(obj.data) for obj in lods]


def _remove_previous_mobile(mobile_name: str) -> None:
    """Delete the previous Mobile collection and its _Mobile-suffixed datablocks."""
    collection = bpy.data.collections.get(mobile_name)
    if collection is not None:
        objects = list(collection.all_objects)
        meshes = [obj.data for obj in objects if obj.type == "MESH" and obj.data is not None]
        for obj in objects:
            bpy.data.objects.remove(obj)
        bpy.data.collections.remove(collection)
        for mesh in meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)

    for material in list(bpy.data.materials):
        if material.name.endswith("_Mobile") and material.users == 0:
            bpy.data.materials.remove(material)
    for image in list(bpy.data.images):
        if image.name.endswith("_Mobile") and image.users == 0:
            bpy.data.images.remove(image)
