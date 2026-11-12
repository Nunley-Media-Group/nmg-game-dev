"""Environment pieces with several material slots, built in code under headless Blender (#151).

A piece is one mesh, SM_<Name>, cut into one strip per slot along X. Strip i is a single face that
uses material slot i and covers `width` metres of the 1 m square. A strip with a UV span s tiles its
UVs across s units per metre, so its density is px * s; a strip with span None collapses its UVs
onto one point (a flat-colour slot).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import bmesh
import bpy

TRIM_PROPERTY = "nmg_trim_atlas"


def slot_material(name: str, px: int, *, trim: bool = False) -> bpy.types.Material:
    """A material with one px-square image sampled through UVMap, marked as trim when asked."""
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    bsdf = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")
    image = bpy.data.images.new(f"T_{name.removeprefix('M_')}_BC", px, px)
    uv = tree.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    tree.links.new(uv.outputs["UV"], texture.inputs["Vector"])
    tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
    if trim:
        material[TRIM_PROPERTY] = True
    return material


Strip = tuple[bpy.types.Material, float | None, float]


def build_piece(name: str, strips: Sequence[Strip]) -> bpy.types.Collection:
    """A 1 m square cut into strips left to right; strip i is (material, UV span, width in m)."""
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    bm = bmesh.new()
    layer = bm.loops.layers.uv.new("UVMap")
    left = -0.5
    for index, (_material, span, width) in enumerate(strips):
        right = left + width
        corners = [
            bm.verts.new((left, -0.5, 0.0)),
            bm.verts.new((right, -0.5, 0.0)),
            bm.verts.new((right, 0.5, 0.0)),
            bm.verts.new((left, 0.5, 0.0)),
        ]
        face = bm.faces.new(corners)
        face.material_index = index
        for loop in face.loops:
            co = loop.vert.co
            if span is None:
                loop[layer].uv = (0.0, 0.0)
            else:
                loop[layer].uv = ((co.x + 0.5) * span, (co.y + 0.5) * span)
        left = right
    mesh = bpy.data.meshes.new(f"SM_{name}")
    bm.to_mesh(mesh)
    bm.free()
    for material, _span, _width in strips:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(f"SM_{name}", mesh)
    collection.objects.link(obj)
    return collection


def texel_findings(report: dict[str, Any]) -> list[dict[str, str]]:
    return [item for item in report["findings"] if item["rule"] == "texel.density"]


def snapshot_texel(report: dict[str, Any], obj_name: str) -> list[dict[str, Any]]:
    return report["snapshot"][obj_name]["texel"]
