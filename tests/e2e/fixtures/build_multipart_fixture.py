"""Build the multi-part Gantry fixture for the opt-in finalize e2e test (#145, AC7).

``build_gantry()`` makes a non-rigged ``Gantry`` collection in the open Blender scene. The root,
``SM_Gantry``, is a 2 m cube whose bottom centre sits at the world origin, which is the contract's
pivot rule. Two child parts sit inside that footprint with their origins away from the asset
origin. The mesh datablock of ``SM_Gantry_Trim`` is ``SM_Gantry_Trim.001``, so it differs from its
object name. Each mesh has a material slot ``M_Gantry_<Part>`` (``Body``, ``Trim``, ``Hinge``) with
a procedural Principled BSDF, which the finalize bake turns into textures.

Run it headless to write the fixture::

    blender --background --factory-startup --python build_multipart_fixture.py -- <out.blend>

The module imports bpy, so only Blender runs it. The default suite never imports it;
``tests/blender/test_e2e_fixture_builder.py`` loads it inside headless Blender.
"""

from __future__ import annotations

import sys
from pathlib import Path

import bmesh
import bpy

COLLECTION = "Gantry"
_UV_COLUMNS = 3
_UV_ROWS = 2
_Vector3 = tuple[float, float, float]


def _clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)


def _box_mesh(name: str, size: _Vector3, center: _Vector3) -> bpy.types.Mesh:
    """A box of ``size`` metres centred on ``center``, with one UV cell per face.

    Each face gets its own cell of a grid, so no two UV islands overlap and every coordinate stays
    in 0..1.
    """
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    bmesh.ops.translate(bm, vec=center, verts=bm.verts)
    uv_layer = bm.loops.layers.uv.new("UVMap")
    low = [center[axis] - size[axis] / 2.0 for axis in range(3)]
    for index, face in enumerate(bm.faces):
        cell_u = (index % _UV_COLUMNS) / _UV_COLUMNS
        cell_v = (index // _UV_COLUMNS) / _UV_ROWS
        normal_axis = max(range(3), key=lambda axis: abs(face.normal[axis]))
        u_axis, v_axis = [axis for axis in range(3) if axis != normal_axis]
        for loop in face.loops:
            u = (loop.vert.co[u_axis] - low[u_axis]) / size[u_axis]
            v = (loop.vert.co[v_axis] - low[v_axis]) / size[v_axis]
            loop[uv_layer].uv = (cell_u + u / _UV_COLUMNS, cell_v + v / _UV_ROWS)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _material(name: str) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.5, 0.5, 0.5, 1.0)
    return material


def build_gantry() -> bpy.types.Collection:
    """Replace the open scene's content with the Gantry collection and return the collection."""
    _clear_scene()
    collection = bpy.data.collections.new(COLLECTION)
    bpy.context.scene.collection.children.link(collection)

    root_mesh = _box_mesh("SM_Gantry", size=(2.0, 2.0, 2.0), center=(0.0, 0.0, 1.0))
    root_mesh.materials.append(_material("M_Gantry_Body"))
    root = bpy.data.objects.new("SM_Gantry", root_mesh)
    collection.objects.link(root)

    trim_mesh = _box_mesh("SM_Gantry_Trim.001", size=(0.2, 0.2, 0.2), center=(0.0, 0.0, 0.0))
    trim_mesh.materials.append(_material("M_Gantry_Trim"))
    trim = bpy.data.objects.new("SM_Gantry_Trim", trim_mesh)
    trim.location = (0.6, 0.0, 1.0)

    hinge_mesh = _box_mesh("SM_Gantry_Hinge", size=(0.3, 0.3, 0.3), center=(0.0, 0.0, 0.0))
    hinge_mesh.materials.append(_material("M_Gantry_Hinge"))
    hinge = bpy.data.objects.new("SM_Gantry_Hinge", hinge_mesh)
    hinge.location = (-0.5, 0.4, 0.5)

    for part in (trim, hinge):
        collection.objects.link(part)
        part.parent = root
    return collection


def _main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 1:
        raise SystemExit(
            "usage: blender --background --python build_multipart_fixture.py -- <out.blend>"
        )
    build_gantry()
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args[0]).resolve()))


if __name__ == "__main__":
    _main()
