"""Terrain grid fixtures for the headless contract tests (#154), built in code.

A terrain is one mesh SM_<Name>: an n x n grid with one vertex per grid point, ``spacing`` metres
apart and centred on the origin. Its UVMap tiles every ``tile_m`` metres, it carries one
Layer_<L> float point attribute per paint layer, and each layer has the material M_<Name>_<L>.
With ``textures`` set, each layer material also samples the tiling T_<Name>_<L>_{BC,N,ORM} images,
as the bake leaves them. Grid order matches terrain_core/heightfield.py: row 0 is the +Y edge.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import bmesh
import bpy

from .contract_fixtures import clear_scene

DEFAULT_LAYERS: Mapping[str, float] = {"Grass": 0.6, "Rock": 0.4}


def build_terrain(
    name: str = "Ground",
    n: int = 127,
    *,
    layers: Mapping[str, float] | None = None,
    spacing: float = 1.0,
    tile_m: float = 3.0,
    texture_px: int = 1024,
    textures: bool = True,
    materials: bool = True,
    offset_x: float = 0.0,
    height_at: Callable[[float, float], float] | None = None,
    spike: tuple[str, float] | None = None,
    extra_object: bool = False,
) -> bpy.types.Collection:
    """Build a terrain collection named ``name`` in a clean scene and return it.

    ``layers`` maps each layer name to its constant weight. ``spike`` sets the first vertex of one
    layer to another value, so a single sample can break the range rule. ``offset_x`` shifts the
    grid off centre. ``height_at(x, y)`` gives each vertex its Z in metres.
    """
    clear_scene()
    scene = bpy.context.scene
    collection = bpy.data.collections.new(name)
    scene.collection.children.link(collection)
    layer_values = dict(DEFAULT_LAYERS if layers is None else layers)

    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=n - 1, y_segments=n - 1, size=(n - 1) * spacing / 2)
    for vert in bm.verts:
        vert.co.z = height_at(vert.co.x, vert.co.y) if height_at is not None else 0.0
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            loop[uv_layer].uv = (loop.vert.co.x / tile_m + 0.5, loop.vert.co.y / tile_m + 0.5)
    for vert in bm.verts:
        vert.co.x += offset_x
    mesh = bpy.data.meshes.new(f"SM_{name}")
    bm.to_mesh(mesh)
    bm.free()

    count = len(mesh.vertices)
    for layer, value in layer_values.items():
        attribute = mesh.attributes.new(f"Layer_{layer}", "FLOAT", "POINT")
        values = [value] * count
        if spike is not None and spike[0] == layer:
            values[0] = spike[1]
        attribute.data.foreach_set("value", values)

    obj = bpy.data.objects.new(f"SM_{name}", mesh)
    collection.objects.link(obj)
    if materials:
        for layer in layer_values:
            mesh.materials.append(_layer_material(name, layer, texture_px, textures))
    if extra_object:
        collection.objects.link(bpy.data.objects.new("Stray", None))
    return collection


def _layer_material(name: str, layer: str, texture_px: int, textures: bool) -> bpy.types.Material:
    material = bpy.data.materials.new(f"M_{name}_{layer}")
    material.use_nodes = True
    if not textures:
        return material
    tree = material.node_tree
    nodes, links = tree.nodes, tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    for suffix, colorspace in (("BC", "sRGB"), ("N", "Non-Color"), ("ORM", "Non-Color")):
        image: Any = bpy.data.images.new(f"T_{name}_{layer}_{suffix}", texture_px, texture_px)
        image.colorspace_settings.name = colorspace
        node = nodes.new("ShaderNodeTexImage")
        node.image = image
        links.new(uv.outputs["UV"], node.inputs["Vector"])
        if suffix == "BC":
            links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
    return material


def bump_at(x: float, y: float, *, at_x: float, at_y: float, height: float) -> float:
    """Return ``height`` at the one sample (at_x, at_y) and 0 everywhere else.

    On a 253 grid the sample at (-125, 125) sits at column 1 and row 1, which a stride-2 Mobile
    downsample drops, so the Desktop and Mobile height ranges differ.
    """
    return height if abs(x - at_x) < 0.5 and abs(y - at_y) < 0.5 else 0.0
