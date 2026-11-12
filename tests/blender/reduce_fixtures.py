"""Assets for the reduce tests, built in code under headless Blender (#139).

build_high_poly makes a three-part, generated-style asset of about 20k triangles. Part Hull carries
a vertex-color material, Turret a procedural one, and Lid an image texture, so the bake covers the
three kinds the spec names. reduce_budgets_file overrides Desktop to 3,000 triangles and 256 px.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import bmesh
import bpy

from .bake_fixtures import checker_image, image_material, procedural_material

PARTS: tuple[tuple[str, float, float], ...] = (
    # (part name, cube edge in metres, x offset in metres)
    ("Hull", 1.0, -2.0),
    ("Turret", 1.5, 0.0),
    ("Lid", 1.0, 2.0),
)
# 23 cuts per edge (subdivide_edges(cuts - 1)) gives 6 * 23 * 23 * 2 = 6,348 triangles per part,
# 19,044 for the asset.
HIGH_CUTS = 23
DESKTOP_TRIS = 3000
# Contract layout: x offsets that keep the whole asset's bounds centred on the root (-3 to 3 m).
_CONTRACT_OFFSETS: dict[str, float] = {"Hull": 0.0, "Turret": -2.25, "Lid": 2.5}
DESKTOP_PX = 256


def object_name(collection: str, part: str) -> str:
    return f"SM_{collection}_{part}"


def reduce_budgets_file(directory: Path) -> str:
    """nmg-budgets.json: Desktop 3,000 triangles and 256 px, and Mobile 128 px for speed."""
    path = directory / "nmg-budgets.json"
    overrides: dict[str, Any] = {}
    for asset_class in ("standard_prop", "environment_piece"):
        overrides[asset_class] = {
            "max_texture_px": 128,
            "desktop": {"tris": DESKTOP_TRIS, "max_texture_px": DESKTOP_PX},
        }
    path.write_text(json.dumps(overrides), encoding="utf-8")
    return str(path)


def build_high_poly(
    name: str = "Crate",
    *,
    cuts: int = HIGH_CUTS,
    with_root: bool = False,
    armature: bool = False,
    contract: bool = False,
    scale: float = 1.0,
) -> bpy.types.Collection:
    """The three-part asset in a collection named name.

    with_root adds an empty Root that the Turret is parented to (a non-source parent), and makes
    the Lid a child of the Hull (a source parent). armature adds an armature, for the refusal test.
    contract lays the asset out as contract section 1 requires, so finalize accepts it: the Hull is
    the root mesh SM_<Name> at identity, the other parts are SM_<Name>_<Part> children of it, and
    every part's origin sits at its base, so the asset's pivot is its bottom centre. scale shrinks
    every part and offset, which raises texel density for the environment-piece density rule.
    """
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    objects: dict[str, bpy.types.Object] = {}
    for part, full_edge, full_offset in PARTS:
        edge, offset = full_edge * scale, full_offset * scale
        obj_name = f"SM_{name}" if contract and part == "Hull" else object_name(name, part)
        obj = bpy.data.objects.new(obj_name, _grid_mesh(obj_name, edge, cuts, base=contract))
        if contract:
            obj.location = (_CONTRACT_OFFSETS[part] * scale, 0.0, 0.0)
        else:
            obj.location = (offset, 0.0, edge / 2)
        collection.objects.link(obj)
        objects[part] = obj
    if contract:
        for part in ("Turret", "Lid"):
            objects[part].parent = objects["Hull"]
    _apply_material(objects["Hull"], _vertex_color_material(f"M_{name}_Hull_Authored"))
    _apply_material(objects["Turret"], procedural_material(f"M_{name}_Turret_Authored"))
    _apply_material(
        objects["Lid"],
        image_material(
            f"M_{name}_Lid_Authored", checker_image(f"{name}_Lid_src", 64, periodic=True)
        ),
    )
    if with_root:
        root = bpy.data.objects.new(f"{name}_Root", None)
        root.location = (0.0, 0.0, 0.0)
        collection.objects.link(root)
        objects["Turret"].parent = root
        objects["Lid"].parent = objects["Hull"]
    if armature:
        rig = bpy.data.armatures.new(f"{name}_Rig")
        rig_object = bpy.data.objects.new(f"{name}_Armature", rig)
        collection.objects.link(rig_object)
    return collection


def _grid_mesh(mesh_name: str, edge: float, cuts: int, *, base: bool = False) -> bpy.types.Mesh:
    """A gridded cube of the given edge, UVs laid per face (overlapping, as a source may be).

    base puts the cube on its local origin (bottom centre) instead of centring it there.
    """
    mesh = bpy.data.meshes.new(mesh_name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=edge)
    if cuts > 1:
        bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=cuts - 1, use_grid_fill=True)
    layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        axis = max(range(3), key=lambda item: abs(face.normal[item]))
        u_axis, v_axis = [item for item in range(3) if item != axis]
        for loop in face.loops:
            co = loop.vert.co
            loop[layer].uv = (co[u_axis] / edge + 0.5, co[v_axis] / edge + 0.5)
    if base:
        bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0.0, 0.0, edge / 2))
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _vertex_color_material(name: str) -> bpy.types.Material:
    """Base color read from the Col point attribute, which runs with position across the part."""
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    bsdf = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")
    attribute = tree.nodes.new("ShaderNodeAttribute")
    attribute.attribute_name = "Col"
    tree.links.new(attribute.outputs["Color"], bsdf.inputs["Base Color"])
    return material


def _apply_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    """Give the part its colour attribute (vertex-color materials need it) and one slot."""
    mesh = obj.data
    if material.node_tree is not None and any(
        node.type == "ATTRIBUTE" for node in material.node_tree.nodes
    ):
        attribute = mesh.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
        for index, vertex in enumerate(mesh.vertices):
            x = (vertex.co.x + 1.0) / 2.0
            y = (vertex.co.y + 1.0) / 2.0
            z = (vertex.co.z + 1.0) / 2.0
            attribute.data[index].color = (x, y, z, 1.0)
    mesh.materials.append(material)


def scene_snapshot() -> dict[str, Any]:
    """Everything a failed or refused reduce must leave as it was (AC9, AC13)."""
    scene = bpy.context.scene
    return {
        "engine": scene.render.engine,
        "collections": sorted(
            (
                collection.name,
                sorted(obj.name for obj in collection.objects),
                sorted(child.name for child in collection.children),
            )
            for collection in bpy.data.collections
        ),
        "objects": sorted(
            (
                obj.name,
                obj.data.name if obj.data is not None else None,
                tuple(round(value, 6) for value in obj.location),
                obj.parent.name if obj.parent is not None else None,
            )
            for obj in bpy.data.objects
        ),
        "meshes": sorted(
            (mesh.name, len(mesh.polygons), tuple(layer.name for layer in mesh.uv_layers))
            for mesh in bpy.data.meshes
        ),
        "materials": sorted(material.name for material in bpy.data.materials),
        "images": sorted(image.name for image in bpy.data.images),
        "slots": sorted(
            (
                obj.name,
                tuple(slot.material.name if slot.material else None for slot in obj.material_slots),
            )
            for obj in bpy.data.objects
            if obj.type == "MESH"
        ),
    }
