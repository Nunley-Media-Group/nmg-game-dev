"""Assets for the bake tests, built in code under headless Blender (#67).

Each builder returns the asset collection. Materials cover the three kinds the spec requires
(procedural, triplanar or position-driven, image texture), a periodic and a non-periodic image for
tiling, and one fixture per AC6 reason.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import bmesh
import bpy
import numpy as np

from .contract_fixtures import clear_scene

__all__ = [
    "budgets_file",
    "build_asset",
    "build_failure",
    "build_tiling_plane",
    "clear_scene",
    "image_material",
    "new_crate",
]

_MARGIN = 0.05


def budgets_file(directory: Path) -> str:
    """nmg-budgets.json with 256 px Desktop and 128 px Mobile, for fast bakes in tests."""
    path = directory / "nmg-budgets.json"
    overrides: dict[str, Any] = {
        "standard_prop": {"max_texture_px": 128, "desktop": {"max_texture_px": 256}},
        "environment_piece": {"max_texture_px": 128, "desktop": {"max_texture_px": 256}},
    }
    path.write_text(json.dumps(overrides), encoding="utf-8")
    return str(path)


def new_crate(
    name: str = "Crate",
    *,
    packed: bool = True,
    cuts: int = 1,
) -> bpy.types.Collection:
    """A collection named name holding one cube mesh SM_<name> with UVMap.

    packed=True lays the six faces on non-overlapping islands (a valid existing layout);
    packed=False maps every face onto the full 0-1 square, so the islands overlap.
    """
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    mesh = bpy.data.meshes.new(f"SM_{name}")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    if cuts > 1:
        bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=cuts - 1, use_grid_fill=True)
    layer = bm.loops.layers.uv.new("UVMap")
    count = len(bm.faces)
    columns = math.ceil(math.sqrt(count))
    rows = math.ceil(count / columns)
    for index, face in enumerate(bm.faces):
        axis = max(range(3), key=lambda item: abs(face.normal[item]))
        u_axis, v_axis = [item for item in range(3) if item != axis]
        cell_u = (index % columns) / columns
        cell_v = (index // columns) / rows
        scale_u = (1.0 / columns) * (1 - 2 * _MARGIN)
        scale_v = (1.0 / rows) * (1 - 2 * _MARGIN)
        for loop in face.loops:
            co = loop.vert.co
            if packed:
                u = cell_u + _MARGIN / columns + (co[u_axis] + 0.5) * scale_u
                v = cell_v + _MARGIN / rows + (co[v_axis] + 0.5) * scale_v
            else:
                u = co[u_axis] + 0.5
                v = co[v_axis] + 0.5
            loop[layer].uv = (u, v)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(f"SM_{name}", mesh)
    collection.objects.link(obj)
    return collection


def build_asset(
    name: str,
    materials: list[bpy.types.Material],
    *,
    packed: bool = True,
    cuts: int = 1,
) -> bpy.types.Collection:
    """new_crate with its faces split across the materials (by height, so each covers a band)."""
    collection = new_crate(name, packed=packed, cuts=cuts)
    obj = collection.objects[0]
    for material in materials:
        obj.data.materials.append(material)
    if len(materials) > 1:
        bands = len(materials)
        for face in obj.data.polygons:
            center_z = sum(obj.data.vertices[index].co.z for index in face.vertices) / len(
                face.vertices
            )
            face.material_index = min(bands - 1, int((center_z + 0.5) * bands))
    return collection


def build_tiling_plane(
    name: str,
    material: bpy.types.Material,
    uv_span: float = 10.0,
) -> bpy.types.Collection:
    """A 1 m environment plane whose single UVMap spans 0 to uv_span (overlap and tile)."""
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    mesh = bpy.data.meshes.new(f"SM_{name}")
    bm = bmesh.new()
    corners = [
        bm.verts.new((-0.5, -0.5, 0.0)),
        bm.verts.new((0.5, -0.5, 0.0)),
        bm.verts.new((0.5, 0.5, 0.0)),
        bm.verts.new((-0.5, 0.5, 0.0)),
    ]
    face = bm.faces.new(corners)
    layer = bm.loops.layers.uv.new("UVMap")
    for loop in face.loops:
        co = loop.vert.co
        loop[layer].uv = ((co.x + 0.5) * uv_span, (co.y + 0.5) * uv_span)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    obj = bpy.data.objects.new(f"SM_{name}", mesh)
    collection.objects.link(obj)
    return collection


def _principled(material: bpy.types.Material) -> tuple[Any, Any]:
    tree = material.node_tree
    bsdf = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")
    return tree, bsdf


def _material(name: str) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    return material


def plain_material(name: str, color: tuple[float, float, float] = (0.6, 0.4, 0.2)) -> Any:
    material = _material(name)
    _, bsdf = _principled(material)
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    return material


def procedural_material(name: str) -> bpy.types.Material:
    """Noise color into Base Color, Noise fac through a Bump into Normal, Noise fac to Roughness."""
    material = _material(name)
    tree, bsdf = _principled(material)
    noise = tree.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 6.0
    bump = tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.2
    tree.links.new(noise.outputs["Color"], bsdf.inputs["Base Color"])
    tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    tree.links.new(noise.outputs["Fac"], bsdf.inputs["Roughness"])
    return material


def triplanar_material(name: str) -> bpy.types.Material:
    """World-position noise (Geometry Position): the coordinates a Blender-only look relies on."""
    material = _material(name)
    tree, bsdf = _principled(material)
    geometry = tree.nodes.new("ShaderNodeNewGeometry")
    noise = tree.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.0
    tree.links.new(geometry.outputs["Position"], noise.inputs["Vector"])
    tree.links.new(noise.outputs["Color"], bsdf.inputs["Base Color"])
    tree.links.new(noise.outputs["Fac"], bsdf.inputs["Roughness"])
    return material


def image_material(name: str, image: bpy.types.Image) -> bpy.types.Material:
    """Image Texture sampled through UVMap, into Base Color."""
    material = _material(name)
    tree, bsdf = _principled(material)
    uv = tree.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    tree.links.new(uv.outputs["UV"], texture.inputs["Vector"])
    tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
    return material


def checker_image(name: str, size: int = 64, periodic: bool = True) -> bpy.types.Image:
    """A color image. Periodic: cos(2 pi u) * cos(2 pi v), so opposite edges match exactly.

    Non-periodic: a horizontal ramp, so the first and last columns differ.
    """
    image = bpy.data.images.new(name, size, size, alpha=True, float_buffer=True)
    image.colorspace_settings.name = "sRGB"
    coords = (np.arange(size, dtype=np.float32) + 0.5) / size
    u, v = np.meshgrid(coords, coords)
    if periodic:
        value = 0.5 + 0.5 * np.cos(2 * np.pi * u) * np.cos(2 * np.pi * v)
    else:
        value = u
    rgba = np.stack([value, 0.6 * value, 0.3 + 0.2 * value, np.ones_like(value)], axis=-1)
    image.pixels.foreach_set(rgba.astype(np.float32).ravel())
    return image


def build_failure(reason: str) -> bpy.types.Collection:
    """An asset the bake must refuse for one AC6 reason, with the material it names."""
    if reason == "transparency":
        material = _material("M_Crate_Glass")
        _, bsdf = _principled(material)
        bsdf.inputs["Alpha"].default_value = 0.5
        return build_asset("Crate", [material])
    if reason == "unsupported_shader":
        material = _material("M_Crate_Gloss")
        tree = material.node_tree
        output = next(node for node in tree.nodes if node.type == "OUTPUT_MATERIAL")
        glossy = tree.nodes.new("ShaderNodeBsdfGlossy")
        tree.links.new(glossy.outputs["BSDF"], output.inputs["Surface"])
        return build_asset("Crate", [material])
    if reason == "emission":
        material = _material("M_Crate_Lamp")
        _, bsdf = _principled(material)
        bsdf.inputs["Emission Strength"].default_value = 2.0
        bsdf.inputs["Emission Color"].default_value = (1.0, 0.2, 0.1, 1.0)
        return build_asset("Crate", [material])
    if reason == "volume_or_displacement":
        material = _material("M_Crate_Fog")
        tree = material.node_tree
        output = next(node for node in tree.nodes if node.type == "OUTPUT_MATERIAL")
        absorption = tree.nodes.new("ShaderNodeVolumeAbsorption")
        tree.links.new(absorption.outputs["Volume"], output.inputs["Volume"])
        return build_asset("Crate", [material])
    if reason == "no_material":
        collection = build_asset("Crate", [plain_material("M_Crate_Body")])
        collection.objects[0].data.materials.append(None)
        return collection
    if reason == "uv_unwrap_failed":
        collection = bpy.data.collections.new("Crate")
        bpy.context.scene.collection.children.link(collection)
        mesh = bpy.data.meshes.new("SM_Crate")
        mesh.from_pydata([(0.0, 0.0, 0.0), (0.1, 0.0, 0.0), (0.2, 0.0, 0.0)], [], [])
        mesh.materials.append(plain_material("M_Crate_Body"))
        obj = bpy.data.objects.new("SM_Crate", mesh)
        collection.objects.link(obj)
        return collection
    raise ValueError(f"no failure fixture for {reason}")
