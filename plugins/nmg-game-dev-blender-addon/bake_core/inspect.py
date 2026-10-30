"""Material inspection: reject what the bake cannot represent (contract AC6 reasons).

The walk follows only shader-typed links from the active Material Output. Texture, vector, and
math nodes that feed non-shader inputs are allowed, because the bake removes them.
"""

from __future__ import annotations

import bpy

from .errors import BakeError

_SHADER_NODES = frozenset({"BSDF_PRINCIPLED", "MIX_SHADER", "ADD_SHADER"})


def inspect_materials(meshes: list[bpy.types.Object]) -> list[bpy.types.Material]:
    """Return the distinct materials of meshes in first-use order, after checking each one."""
    distinct: list[bpy.types.Material] = []
    for obj in meshes:
        if not obj.material_slots:
            raise BakeError(
                "no_material",
                f"Mesh '{obj.name}' has no material slots.",
                target=obj.name,
            )
        for slot in obj.material_slots:
            material = slot.material
            if material is None:
                raise BakeError(
                    "no_material",
                    f"Mesh '{obj.name}' has an empty material slot.",
                    target=obj.name,
                )
            if material not in distinct:
                inspect_material(material)
                distinct.append(material)
    return distinct


def inspect_material(material: bpy.types.Material) -> None:
    """Raise BakeError naming material when its node tree has an unrepresentable feature."""
    tree = material.node_tree
    output = _active_output(tree)
    if output is None:
        raise BakeError(
            "unsupported_shader",
            f"Material '{material.name}' has no active Material Output node.",
            target=material.name,
        )
    for name in ("Volume", "Displacement"):
        if output.inputs[name].is_linked:
            raise BakeError(
                "volume_or_displacement",
                f"Material '{material.name}' links its {name} output.",
                target=material.name,
            )

    seen: set[str] = set()
    stack = [link.from_node for link in output.inputs["Surface"].links]
    while stack:
        node = stack.pop()
        if node.name in seen:
            continue
        seen.add(node.name)
        if node.type not in _SHADER_NODES:
            raise BakeError(
                "unsupported_shader",
                f"Material '{material.name}' feeds the surface from the {node.type} node "
                f"'{node.name}'.",
                target=material.name,
            )
        if node.type == "BSDF_PRINCIPLED":
            _check_principled(material.name, node)
        for socket in node.inputs:
            if socket.type == "SHADER":
                stack.extend(link.from_node for link in socket.links)


def _active_output(tree: bpy.types.NodeTree | None) -> bpy.types.Node | None:
    if tree is None:
        return None
    return next(
        (node for node in tree.nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output),
        None,
    )


def _check_principled(material_name: str, node: bpy.types.Node) -> None:
    alpha = node.inputs["Alpha"]
    transmission = node.inputs["Transmission Weight"]
    if alpha.is_linked or alpha.default_value < 1.0:
        raise BakeError(
            "transparency",
            f"Material '{material_name}' has Alpha below 1 or linked on '{node.name}'.",
            target=material_name,
        )
    if transmission.is_linked or transmission.default_value > 0.0:
        raise BakeError(
            "transparency",
            f"Material '{material_name}' has Transmission Weight above 0 or linked on "
            f"'{node.name}'.",
            target=material_name,
        )
    strength = node.inputs["Emission Strength"]
    color = node.inputs["Emission Color"]
    color_is_black = tuple(color.default_value[:3]) == (0.0, 0.0, 0.0)
    if strength.is_linked or (
        strength.default_value > 0.0 and (color.is_linked or not color_is_black)
    ):
        raise BakeError(
            "emission",
            f"Material '{material_name}' emits light on '{node.name}' (Emission Strength above 0 "
            "with a non-black or linked Emission Color).",
            target=material_name,
        )
