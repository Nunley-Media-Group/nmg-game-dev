"""Blender fixtures for the contract tests: a compliant Crate and one defect per AC2 class.

The compliant Crate is a unit box with a Desktop root (SM_Crate) and a Mobile LOD group
(SM_Crate_Mobile with LOD0-2). Its six faces sit in separate UV islands, and each variant has a
baked-style material whose Image Texture nodes sample UVMap through a UV Map node.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import bmesh
import bpy

DEFECTS: tuple[str, ...] = (
    "root_rotation",
    "origin_off_center",
    "no_uv",
    "uv_overlap",
    "noise_material",
    "position_coords",
    "mobile_lod0_4000_tris",
    "mobile_name_mismatch",
)
_ISLAND_COLUMNS = 3
_ISLAND_ROWS = 2
_MARGIN = 0.05


def clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)
    for image in list(bpy.data.images):
        # Generated images report type UV_TEST, so only keep Blender's own render slots.
        if image.type not in {"RENDER_RESULT", "COMPOSITING", "VIEWER"}:
            bpy.data.images.remove(image)
    for light in list(bpy.data.lights):
        bpy.data.lights.remove(light)
    for camera in list(bpy.data.cameras):
        bpy.data.cameras.remove(camera)
    # In background Blender, removed objects leave None entries in the view layer until it is
    # updated; export_variants iterates that layer, so sync it before the next build.
    bpy.context.view_layer.update()


def build_crate() -> None:
    """Build a compliant Crate (Desktop and Mobile) in a clean scene."""
    clear_scene()
    scene = bpy.context.scene
    desktop = bpy.data.collections.new("Crate")
    mobile = bpy.data.collections.new("Crate_Mobile")
    scene.collection.children.link(desktop)
    scene.collection.children.link(mobile)

    desktop_material = _baked_material("M_Crate_Body", "")
    root = bpy.data.objects.new("SM_Crate", _box_mesh("SM_Crate", desktop_material))
    desktop.objects.link(root)

    mobile_material = _baked_material("M_Crate_Body_Mobile", "_Mobile")
    group = bpy.data.objects.new("SM_Crate_Mobile", None)
    group.empty_display_type = "PLAIN_AXES"
    group["fbx_type"] = "LodGroup"
    mobile.objects.link(group)
    for level in range(3):
        name = f"SM_Crate_Mobile_LOD{level}"
        lod = bpy.data.objects.new(name, _box_mesh(name, mobile_material))
        mobile.objects.link(lod)
        lod.parent = group


def apply_defect(defect: str) -> None:
    """Break the compliant Crate in one way that AC2 must catch."""
    if defect == "root_rotation":
        bpy.data.objects["SM_Crate"].rotation_euler = (0.0, 0.0, 0.3)
    elif defect == "origin_off_center":
        for vert in bpy.data.objects["SM_Crate"].data.vertices:
            vert.co.z += 0.5
    elif defect == "no_uv":
        mesh = bpy.data.objects["SM_Crate"].data
        mesh.uv_layers.remove(mesh.uv_layers["UVMap"])
    elif defect == "uv_overlap":
        _overlap_uvs(bpy.data.objects["SM_Crate"].data)
    elif defect == "noise_material":
        _noise_base_color(bpy.data.materials["M_Crate_Body"])
    elif defect == "position_coords":
        _position_coordinates(bpy.data.materials["M_Crate_Body"])
    elif defect == "mobile_lod0_4000_tris":
        _replace_with_dense_grid(bpy.data.objects["SM_Crate_Mobile_LOD0"])
    elif defect == "mobile_name_mismatch":
        _rename_mobile("SM_Crate_Mobile", "SM_Krate_Mobile")
    else:
        raise ValueError(f"unknown defect {defect!r}")


def _baked_material(name: str, suffix: str) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    nodes, links = tree.nodes, tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    # Generated images default to black, which renders as a mirror-smooth black surface, so
    # the fixture gives each map a flat, plausible value.
    base = _texture_node(nodes, f"T_Crate_Body_BC{suffix}", "sRGB", (0.7, 0.45, 0.25, 1.0))
    normal = _texture_node(nodes, f"T_Crate_Body_N{suffix}", "Non-Color", (0.5, 0.5, 1.0, 1.0))
    orm = _texture_node(nodes, f"T_Crate_Body_ORM{suffix}", "Non-Color", (1.0, 0.6, 0.0, 1.0))
    for node in (base, normal, orm):
        links.new(uv.outputs["UV"], node.inputs["Vector"])
    normal_map = nodes.new("ShaderNodeNormalMap")
    split = nodes.new("ShaderNodeSeparateColor")
    links.new(base.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(normal.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(orm.outputs["Color"], split.inputs["Color"])
    links.new(split.outputs["Green"], bsdf.inputs["Roughness"])
    links.new(split.outputs["Blue"], bsdf.inputs["Metallic"])
    return material


def _texture_node(nodes: Any, image_name: str, colorspace: str, color: tuple[float, ...]) -> Any:
    image = bpy.data.images.new(image_name, 512, 512)
    image.generated_color = color
    image.colorspace_settings.name = colorspace
    node = nodes.new("ShaderNodeTexImage")
    node.image = image
    return node


def _box_mesh(name: str, material: bpy.types.Material) -> bpy.types.Mesh:
    """A unit box on the ground plane (z from 0 to 1), with one UV island per face."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0.0, 0.0, 0.5))
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for index, face in enumerate(bm.faces):
        column, row = index % _ISLAND_COLUMNS, index // _ISLAND_COLUMNS
        axis = max(range(3), key=lambda k: abs(face.normal[k]))
        u_axis, v_axis = [k for k in range(3) if k != axis]
        for loop in face.loops:
            local = _local(loop.vert.co)
            loop[uv_layer].uv = (
                (column + _MARGIN + (1 - 2 * _MARGIN) * local[u_axis]) / _ISLAND_COLUMNS,
                (row + _MARGIN + (1 - 2 * _MARGIN) * local[v_axis]) / _ISLAND_ROWS,
            )
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    return mesh


def _local(co: Any) -> list[float]:
    """Face-local coordinates in [0, 1]: x and y are centered on the box, z already starts at 0."""
    return [co.x + 0.5, co.y + 0.5, co.z]


def _overlap_uvs(mesh: bpy.types.Mesh) -> None:
    """Map every face onto the whole unit square, so all six faces overlap."""
    uv = mesh.uv_layers["UVMap"].data
    for poly in mesh.polygons:
        axis = max(range(3), key=lambda k: abs(poly.normal[k]))
        u_axis, v_axis = [k for k in range(3) if k != axis]
        for loop_index in poly.loop_indices:
            local = _local(mesh.vertices[mesh.loops[loop_index].vertex_index].co)
            uv[loop_index].uv = (local[u_axis], local[v_axis])


def _noise_base_color(material: bpy.types.Material) -> None:
    tree = material.node_tree
    bsdf = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")
    for link in list(bsdf.inputs["Base Color"].links):
        tree.links.remove(link)
    noise = tree.nodes.new("ShaderNodeTexNoise")
    tree.links.new(noise.outputs["Color"], bsdf.inputs["Base Color"])


def _position_coordinates(material: bpy.types.Material) -> None:
    tree = material.node_tree
    for node in [node for node in tree.nodes if node.type == "TEX_IMAGE"]:
        for link in list(node.inputs["Vector"].links):
            tree.links.remove(link)
        geometry = tree.nodes.new("ShaderNodeNewGeometry")
        tree.links.new(geometry.outputs["Position"], node.inputs["Vector"])


def _replace_with_dense_grid(obj: bpy.types.Object) -> None:
    """Give obj a 40 x 50 quad grid, which is 4,000 triangles."""
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=40, y_segments=50, size=0.5)
    bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0.0, 0.0, 0.5))
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            loop[uv_layer].uv = (loop.vert.co.x + 0.5, loop.vert.co.y + 0.5)
    mesh = bpy.data.meshes.new(f"{obj.name}_dense")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(obj.data.materials[0])
    old = obj.data
    obj.data = mesh
    bpy.data.meshes.remove(old)


def _rename_mobile(old_root: str, new_root: str) -> None:
    bpy.data.objects[old_root].name = new_root
    for level in range(3):
        bpy.data.objects[f"{old_root}_LOD{level}"].name = f"{new_root}_LOD{level}"


def export_crate(export_root: Path) -> Path:
    """Export the compliant Crate through variants_core, returning <export_root>/Props/Crate."""
    from importlib import import_module  # noqa: PLC0415 - the add-on is enabled by the fixture

    export = import_module("nmg_game_dev_blender_addon.variants_core.export")
    export.export_variants("Crate", "Props", str(export_root))
    return export_root / "Props" / "Crate"
