"""Commit a finished reduce: keep the originals in <Name>_High and link the reduced copies (#139).

Runs only after every earlier step passed. The first run moves each source into a hidden
top-level <Name>_High, renamed <part>_High and tagged with nmg_source_name. A rerun leaves
<Name>_High alone and replaces the reduced meshes, materials, and images in <Name>. An object
parented to a part that is replaced is parented to that part's new copy, keeping its world
transform.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import bpy

HIGH_SUFFIX = "_High"
SOURCE_PROPERTY = "nmg_source_name"
REDUCED_PROPERTY = "nmg_reduced"
COPY_COLLECTION = "__nmg_reduce"

# (object, key of its new parent, world matrix to keep). The key is a reduced part name.
_Follower = tuple[bpy.types.Object, str, object]


def commit(
    collection: bpy.types.Collection,
    high: bpy.types.Collection | None,
    sources: Sequence[tuple[str, bpy.types.Object]],
    copies: Mapping[str, bpy.types.Object],
    material: bpy.types.Material,
) -> None:
    """Keep or move the originals, retire the previous reduced objects, and link the copies."""
    scene = bpy.context.scene
    source_names = {obj.as_pointer(): name for name, obj in sources}
    if high is None:
        followers = _followers(collection, source_names, parent_key=None)
        high = bpy.data.collections.new(f"{collection.name}{HIGH_SUFFIX}")
        scene.collection.children.link(high)
        _move_to_high(sources, high)
    else:
        followers = _retire_previous(collection)
    high.hide_viewport = True
    high.hide_render = True

    for name, copy in copies.items():
        for owner in list(copy.users_collection):
            owner.objects.unlink(copy)
        copy.name = name
        copy.data.name = name
        collection.objects.link(copy)

    for obj, key, world in followers:
        obj.parent = copies.get(key)
        obj.matrix_world = world

    _name_datablocks(collection.name, material)
    collection[REDUCED_PROPERTY] = True
    temp = bpy.data.collections.get(COPY_COLLECTION)
    if temp is not None:
        for obj in list(temp.objects):
            temp.objects.unlink(obj)
        bpy.data.collections.remove(temp)


def _move_to_high(
    sources: Sequence[tuple[str, bpy.types.Object]], high: bpy.types.Collection
) -> None:
    for name, obj in sources:
        for owner in list(obj.users_collection):
            owner.objects.unlink(obj)
        high.objects.link(obj)
        obj[SOURCE_PROPERTY] = name
        obj.name = f"{name}{HIGH_SUFFIX}"
        obj.data.name = f"{obj.data.name}{HIGH_SUFFIX}"


def _followers(
    collection: bpy.types.Collection,
    source_names: Mapping[int, str],
    parent_key: str | None,
) -> list[_Follower]:
    """Objects in collection (not sources) parented to a source, with the source's part name."""
    followers: list[_Follower] = []
    for obj in collection.all_objects:
        if obj.as_pointer() in source_names or obj.parent is None:
            continue
        key = source_names.get(obj.parent.as_pointer(), parent_key)
        if key is not None:
            followers.append((obj, key, obj.matrix_world.copy()))
    return followers


def _retire_previous(collection: bpy.types.Collection) -> list[_Follower]:
    """Delete the previous run's reduced meshes and the datablocks only they used.

    Objects parented to a previous reduced mesh are returned so they can follow the new copy
    of the same part name.
    """
    old_objects = [obj for obj in collection.all_objects if obj.type == "MESH"]
    old_pointers = {obj.as_pointer() for obj in old_objects}
    followers: list[_Follower] = []
    for obj in collection.all_objects:
        if obj.as_pointer() in old_pointers or obj.parent is None:
            continue
        if obj.parent.as_pointer() in old_pointers:
            followers.append((obj, obj.parent.name, obj.matrix_world.copy()))
    old_meshes = {obj.data for obj in old_objects if obj.data is not None}
    old_materials = {
        slot.material for obj in old_objects for slot in obj.material_slots if slot.material
    }
    old_images = {
        node.image
        for material in old_materials
        if material.node_tree is not None
        for node in material.node_tree.nodes
        if node.type == "TEX_IMAGE" and node.image is not None
    }
    for obj in old_objects:
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in old_meshes:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for material in old_materials:
        if material.users == 0:
            bpy.data.materials.remove(material)
    for image in old_images:
        if image.users == 0:
            bpy.data.images.remove(image)
    return followers


def _name_datablocks(asset: str, material: bpy.types.Material) -> None:
    """Give the new material and its images their contract names once the old ones are gone."""
    material.name = f"M_{asset}_Body"
    if material.node_tree is None:
        return
    for node in material.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image is not None and node.label:
            node.image.name = node.label
