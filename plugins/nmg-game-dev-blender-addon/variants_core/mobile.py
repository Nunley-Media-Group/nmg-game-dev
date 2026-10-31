"""Mobile build: copy the Desktop hierarchy, decimate to budget, and wrap LODs in a group."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import bpy
from mathutils import Matrix

from .assets import (
    asset_armature,
    asset_meshes,
    distinct_materials,
    mobile_collection_name,
    require_asset,
)
from .meshes import evaluated_mesh, fit_meshes, replace_mesh, triangle_count
from .textures import max_texture_px, mobile_image_copy, mobile_material_copy, source_images

#: Modifier name for the skin, matching the name rig_core gives the rig's own Armature modifier.
_SKIN_MODIFIER = "Armature"


def build_mobile(collection_name: str, budget: Mapping[str, int]) -> dict[str, Any]:
    """Rebuild <Name>_Mobile from the Desktop asset. Caller must validate inputs first."""
    collection, root = require_asset(collection_name)
    mobile_name = mobile_collection_name(collection_name)
    _remove_previous_mobile(mobile_name)
    rig = asset_armature(collection_name)

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
    copies = _copy_objects(sources, mobile_materials, mobile_collection, rig)

    root_copy = copies[root.name]
    parts = [copies[src.name] for src in sources if src.name != root.name]
    if parts:
        lod_tris = [_fit_objects([root_copy, *parts], budget["tris"], mobile_name)]
    elif rig is not None:
        lod_tris = _build_rigged_chain(
            root_copy,
            root.matrix_world.copy(),
            budget["tris"],
            mobile_collection,
            rig,
            collection_name,
        )
    else:
        lod_tris = _build_lod_group(root_copy, budget["tris"], mobile_collection, collection_name)

    return {
        "collection": mobile_name,
        "root": f"SM_{collection_name}_Mobile",
        "rigged": rig is not None,
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
    rig: bpy.types.Object | None,
) -> dict[str, bpy.types.Object]:
    if rig is not None:
        # The rig's world matrix must be current before the copies are placed against it.
        bpy.context.view_layer.update()
    copies: dict[str, bpy.types.Object] = {}
    for src in sources:
        # A rigged source was cleaned to its rest mesh with only the skin left, so copy the data
        # as it is. Evaluating it would bake the current pose into the Mobile copy.
        mesh = src.data.copy() if rig is not None else evaluated_mesh(src)
        for index, material in enumerate(mesh.materials):
            if material is not None:
                mesh.materials[index] = mobile_materials[material.name]
        obj = bpy.data.objects.new(f"{src.name}_Mobile", mesh)
        mobile_collection.objects.link(obj)
        if rig is not None:
            _copy_vertex_groups(src, obj)
        copies[src.name] = obj

    for src in sources:
        obj = copies[src.name]
        parent = copies.get(src.parent.name) if src.parent is not None else None
        if parent is not None:
            obj.parent = parent
            obj.matrix_parent_inverse = src.matrix_parent_inverse.copy()
            obj.matrix_basis = src.matrix_basis.copy()
        elif rig is not None:
            _bind_to_rig(obj, rig, src.matrix_world.copy())
        else:
            obj.matrix_world = src.matrix_world.copy()
    return copies


def _copy_vertex_groups(src: bpy.types.Object, obj: bpy.types.Object) -> None:
    """Give obj src's vertex groups by name, in index order, so the copied weights resolve.

    A copied mesh can already carry the group names, so the groups are rebuilt only when they
    differ. Rebuilding on top of matching names would double them.
    """
    wanted = [group.name for group in src.vertex_groups]
    if [group.name for group in obj.vertex_groups] == wanted:
        return
    for group in list(obj.vertex_groups):
        obj.vertex_groups.remove(group)
    for name in wanted:
        obj.vertex_groups.new(name=name)


def _bind_to_rig(obj: bpy.types.Object, rig: bpy.types.Object, world: Matrix) -> None:
    """Parent obj to the rig with an identity parent inverse, keep its world matrix, and skin it."""
    obj.parent = rig
    obj.parent_type = "ARMATURE"
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_world = world
    skin = obj.modifiers.new(name=_SKIN_MODIFIER, type="ARMATURE")
    skin.object = rig
    skin.use_vertex_groups = True


def _build_rigged_chain(
    root: bpy.types.Object,
    world: Matrix,
    budget_tris: int,
    mobile_collection: bpy.types.Collection,
    rig: bpy.types.Object,
    asset_name: str,
) -> list[int]:
    """LOD0 at budget, LOD1 at 50%, LOD2 at 25%, as three skinned meshes with no Empty.

    Each LOD is a separate skinned mesh parented to the rig, so each exports to its own FBX.
    world is the Desktop root's world matrix, which every LOD takes. Returns the triangle count
    of each LOD level, LOD0 first.
    """
    group_name = f"SM_{asset_name}_Mobile"
    (lod0,) = fit_meshes([root.data], budget_tris, group_name)
    replace_mesh(root, lod0)
    lod0_tris = triangle_count(lod0)

    lods = [root]
    for level, target in ((1, lod0_tris // 2), (2, lod0_tris // 4)):
        mesh = fit_meshes([lod0], target, f"{group_name} LOD{level}")[0]
        obj = bpy.data.objects.new(f"{group_name}_LOD{level}", mesh)
        mobile_collection.objects.link(obj)
        _copy_vertex_groups(root, obj)
        _bind_to_rig(obj, rig, world)
        lods.append(obj)
    return [triangle_count(obj.data) for obj in lods]


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
