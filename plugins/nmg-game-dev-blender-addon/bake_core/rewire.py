"""Export-ready materials that sample the baked PNGs, part naming, and slot reassignment.

A rewired material is a Principled BSDF fed only by Image Texture nodes (BC sRGB into Base Color;
ORM Non-Color into Separate Color, G to Roughness and B to Metallic; N Non-Color through a Normal
Map on UVMap). Every Image Texture's Vector input is linked to one UV Map node on UVMap, which the
contract (section 4, material.uv_coordinates) requires. Leaving it unlinked makes Blender sample
Generated coordinates, so the export gate would reject the bake output.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import bpy

_NUMBER_SUFFIX = re.compile(r"\.\d+$")


def part_names(sources: Sequence[bpy.types.Material], asset: str, merged: bool) -> list[str]:
    """Part name for each source material: kept from M_<Name>_<Part>, Body, or PascalCase."""
    if merged:
        return ["Body"]
    names: list[str] = []
    used: set[str] = set()
    prefix = f"M_{asset}_"
    for source in sources:
        plain = _NUMBER_SUFFIX.sub("", source.name)
        if plain.startswith(prefix) and len(plain) > len(prefix):
            part = plain[len(prefix) :]
        elif len(sources) == 1:
            part = "Body"
        else:
            words = re.findall(r"[A-Za-z0-9]+", plain)
            part = "".join(word[:1].upper() + word[1:] for word in words) or "Part"
        base, number = part, 2
        while part in used:
            part = f"{base}{number}"
            number += 1
        used.add(part)
        names.append(part)
    return names


def build_material(name: str, asset: str, part: str, paths: dict[str, Path]) -> bpy.types.Material:
    """A new M_<Name>_<Part> material whose image nodes reference the Desktop PNGs."""
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    nodes = tree.nodes
    links = tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")

    base = _image_node(tree, f"T_{asset}_{part}_BC", paths["BC"], "sRGB")
    orm = _image_node(tree, f"T_{asset}_{part}_ORM", paths["ORM"], "Non-Color")
    normal = _image_node(tree, f"T_{asset}_{part}_N", paths["N"], "Non-Color")
    split = nodes.new("ShaderNodeSeparateColor")
    normal_map = nodes.new("ShaderNodeNormalMap")
    normal_map.uv_map = "UVMap"
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"

    for image in (base, orm, normal):
        links.new(uv.outputs["UV"], image.inputs["Vector"])
    links.new(base.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(orm.outputs["Color"], split.inputs["Color"])
    links.new(split.outputs["Green"], bsdf.inputs["Roughness"])
    links.new(split.outputs["Blue"], bsdf.inputs["Metallic"])
    links.new(normal.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
    return material


def assign(
    meshes: Sequence[bpy.types.Object],
    replacements: dict[int, bpy.types.Material],
) -> None:
    """Point every slot holding a replaced source material at its rewired material."""
    for obj in meshes:
        slots = obj.data.materials
        for index, material in enumerate(list(slots)):
            if material is not None and material.as_pointer() in replacements:
                slots[index] = replacements[material.as_pointer()]


def collapse(meshes: Sequence[bpy.types.Object], material: bpy.types.Material) -> None:
    """Merged asset: every face uses the one material in a single slot.

    Faces are moved to index 0 first, so removing the extra slots never strands a face.
    """
    for obj in meshes:
        obj.data.polygons.foreach_set("material_index", [0] * len(obj.data.polygons))
        slots = obj.data.materials
        while len(slots) > 1:
            slots.pop()
        if len(slots):
            slots[0] = material
        else:
            slots.append(material)


def retire(sources: Sequence[bpy.types.Material]) -> None:
    """Rename authored originals to <name>_Authoring and keep them alive for re-authoring."""
    for source in sources:
        source.name = f"{source.name}_Authoring"
        source.use_fake_user = True


def _image_node(tree: bpy.types.NodeTree, name: str, path: Path, colorspace: str) -> bpy.types.Node:
    image = bpy.data.images.load(str(path), check_existing=False)
    image.name = name
    image.colorspace_settings.name = colorspace
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    node.label = name
    return node
