"""Shared fixtures for Blender headless tests (run under blender --background)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_host: skip test when ahujasid/blender-mcp is not installed",
    )


@pytest.fixture(scope="session")
def enabled_addon():
    # Session scope is deliberate — enabling/disabling per-test would leak
    # registered classes and confound AC1's idempotency assertion.
    try:
        import addon_utils  # noqa: PLC0415
    except ImportError:
        pytest.skip("Blender add-on tests require Blender's bundled Python runtime")

    module_id = "nmg_game_dev_blender_addon"
    addon_utils.enable(module_id, default_set=True, persistent=False)
    yield module_id
    addon_utils.disable(module_id, default_set=False)


@pytest.fixture()
def blender_context(enabled_addon: str):  # noqa: ARG001 — ordering dependency
    try:
        import bpy  # noqa: PLC0415
    except ImportError:
        pytest.skip("Blender add-on tests require Blender's bundled Python runtime")

    if not bpy.data.scenes:
        bpy.data.scenes.new("TestScene")
    return bpy.context


# Grid-filled cube builder: 6 faces x 32 x 32 cells x 2 triangles = 12,288 triangles.
_CRATE_CUTS = 31


def _clear_scene() -> None:
    import bpy  # noqa: PLC0415

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)
    for image in list(bpy.data.images):
        if image.type == "IMAGE":
            bpy.data.images.remove(image)


@pytest.fixture()
def reset_scene(enabled_addon: str) -> Any:  # noqa: ARG001 — ordering dependency
    return _clear_scene


def _inject_defects(bm: Any) -> None:
    """Add duplicate and loose vertices, a zero-area face, and flipped normals."""
    import bmesh  # noqa: PLC0415

    for vert in list(bm.verts)[:24]:
        bm.verts.new(vert.co.copy())  # coincident duplicate vertices
    bm.verts.new((3.0, 3.0, 3.0))  # loose vertex
    a = bm.verts.new((2.0, 0.0, 0.0))
    b = bm.verts.new((2.5, 0.0, 0.0))
    c = bm.verts.new((3.0, 0.0, 0.0))
    bm.faces.new((a, b, c))  # zero-area face
    bmesh.ops.reverse_faces(bm, faces=[face for face in bm.faces if face.normal.x > 0.5])


def _crate_mesh(name: str, split_materials: bool) -> Any:
    import bmesh  # noqa: PLC0415
    import bpy  # noqa: PLC0415

    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=_CRATE_CUTS, use_grid_fill=True)
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        axis = max(range(3), key=lambda index: abs(face.normal[index]))
        u_axis, v_axis = [index for index in range(3) if index != axis]
        for loop in face.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co[u_axis] + 0.5, co[v_axis] + 0.5)
        if split_materials:
            # The second material covers the top half of the crate.
            face.material_index = 1 if face.calc_center_median().z > 0 else 0
    _inject_defects(bm)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _image_material(name: str, texture_dir: Path) -> Any:
    import bpy  # noqa: PLC0415

    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"

    def sampled(suffix: str, colorspace: str) -> Any:
        image = bpy.data.images.new(f"T_Crate_Body_{suffix}", 2048, 2048)
        image.colorspace_settings.name = colorspace
        image.filepath_raw = str(texture_dir / f"T_Crate_Body_{suffix}.png")
        image.file_format = "PNG"
        image.save()
        node = nodes.new("ShaderNodeTexImage")
        node.image = image
        links.new(uv.outputs["UV"], node.inputs["Vector"])
        return node

    base_color = sampled("BC", "sRGB")
    normal = sampled("N", "Non-Color")
    orm = sampled("ORM", "Non-Color")
    normal_map = nodes.new("ShaderNodeNormalMap")
    split = nodes.new("ShaderNodeSeparateColor")
    links.new(base_color.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(normal.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(orm.outputs["Color"], split.inputs["Color"])
    links.new(split.outputs["Green"], bsdf.inputs["Roughness"])
    links.new(split.outputs["Blue"], bsdf.inputs["Metallic"])
    return material


def _unbaked_material(name: str) -> Any:
    material = _plain_material(name)
    nodes = material.node_tree.nodes
    noise = nodes.new("ShaderNodeTexNoise")
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    material.node_tree.links.new(noise.outputs["Color"], bsdf.inputs["Base Color"])
    return material


def _plain_material(name: str) -> Any:
    import bpy  # noqa: PLC0415

    material = bpy.data.materials.new(name)
    material.use_nodes = True
    return material


@pytest.fixture()
def build_crate(enabled_addon: str, tmp_path_factory: pytest.TempPathFactory) -> Any:  # noqa: ARG001
    """Return a builder that makes collection Crate in a fresh scene.

    material: "baked" (default), "unbaked" (Noise Texture), or "two" (two materials).
    parts: add a child part SM_Crate_Trim parented to the root.
    """

    def _build(material: str = "baked", parts: bool = False) -> Any:
        import bmesh  # noqa: PLC0415
        import bpy  # noqa: PLC0415

        _clear_scene()
        texture_dir = tmp_path_factory.mktemp("crate_textures")
        collection = bpy.data.collections.new("Crate")
        bpy.context.scene.collection.children.link(collection)

        if material == "unbaked":
            body = _unbaked_material("M_Crate_Body")
        else:
            body = _image_material("M_Crate_Body", texture_dir)
        mesh = _crate_mesh("SM_Crate", split_materials=material == "two")
        mesh.materials.append(body)
        if material == "two":
            mesh.materials.append(_plain_material("M_Crate_Trim"))
        root = bpy.data.objects.new("SM_Crate", mesh)
        collection.objects.link(root)

        if parts:
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=0.2)
            bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0.6, 0.0, 0.0))
            part_mesh = bpy.data.meshes.new("SM_Crate_Trim")
            bm.to_mesh(part_mesh)
            bm.free()
            part_mesh.materials.append(body)
            part = bpy.data.objects.new("SM_Crate_Trim", part_mesh)
            collection.objects.link(part)
            part.parent = root
        return collection

    return _build
