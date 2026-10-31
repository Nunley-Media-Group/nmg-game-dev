"""Headless Blender tests for scripts/blender/meshy_session.py (#98 AC1, AC7, AC11; #105 AC1–AC4).

Run with ``scripts/run-blender-tests.sh tests/blender/test_meshy_session.py``. Outside Blender the
module skips, because ``bpy`` is only importable inside Blender's bundled Python.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")
bmesh = pytest.importorskip("bmesh")
mathutils = pytest.importorskip("mathutils")

REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION = REPO_ROOT / "scripts" / "blender" / "meshy_session.py"


def _run(op: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Run meshy_session.py the way the Blender MCP exec call does, and parse its result line."""
    namespace: dict[str, Any] = {"NMG_OP": op, "NMG_PAYLOAD": payload, "__name__": "meshy_session"}
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        exec(compile(SESSION.read_text(encoding="utf-8"), str(SESSION), "exec"), namespace)
    line = next(line for line in captured.getvalue().splitlines() if line.startswith("NMG_RESULT "))
    return json.loads(line[len("NMG_RESULT ") :])


@pytest.fixture()
def empty_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)


def _build_glb(path: Path, cubes: int = 1) -> Path:
    """Build ``cubes`` cubes with one material, export them as GLB, and clear the scene."""
    for index in range(cubes):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(index * 3.0, 0.0, 0.0))
    material = bpy.data.materials.new("Stone")
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            obj.data.materials.append(material)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    return path


def _write_png(path: Path) -> Path:
    image = bpy.data.images.new(path.stem, 4, 4)
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)
    return path


def _mesh_objects(collection_name: str) -> list[Any]:
    return [obj for obj in bpy.data.collections[collection_name].all_objects if obj.type == "MESH"]


def _corner_uvs(mesh: Any) -> list[tuple[float, float]]:
    """Return every face corner's UV, rounded and sorted, so comparisons ignore corner order."""
    uv_layer = mesh.uv_layers.active.data
    return sorted((round(item.uv[0], 5), round(item.uv[1], 5)) for item in uv_layer)


def _island_count(mesh: Any) -> int:
    """Count the connected islands of the mesh's faces, joined through shared vertices."""
    parent = {index: index for poly in mesh.polygons for index in poly.vertices}

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for poly in mesh.polygons:
        root = find(poly.vertices[0])
        for index in poly.vertices[1:]:
            parent[find(index)] = root
    return len({find(index) for index in parent})


def _build_seamed_cube_glb(path: Path) -> tuple[Path, dict[str, Any]]:
    """Export a cube at (2, 3, 4) with inward faces and custom split normals (#105 AC1–AC3).

    The cube's per-face UVs make the exporter split its corners, so the GLB holds more vertices than
    the cube's eight. glTF stores triangles, so the cube is triangulated first, and the source
    counts are taken from the triangles. Returns the GLB path and the source's face count, sorted
    corner UVs, and material slot count.
    """
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(2.0, 3.0, 4.0))
    cube = next(obj for obj in bpy.data.objects if obj.type == "MESH")
    cube.data.materials.append(bpy.data.materials.new("Stone"))
    bm = bmesh.new()
    bm.from_mesh(cube.data)
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(cube.data)
    bm.free()
    cube.data.normals_split_custom_set_from_vertices(
        [tuple(vertex.co.normalized()) for vertex in cube.data.vertices]
    )
    assert cube.data.has_custom_normals
    source = {
        "faces": len(cube.data.polygons),
        "uvs": _corner_uvs(cube.data),
        "slots": len(cube.material_slots),
    }
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    return path, source


def _texture_links(material: Any) -> dict[str, str]:
    """Map each image file stem to the socket of the node it feeds (through a Normal Map if any)."""
    tree = material.node_tree
    links: dict[str, str] = {}
    for node in tree.nodes:
        if node.type != "TEX_IMAGE" or node.image is None:
            continue
        stem = Path(node.image.filepath_raw or node.image.filepath).stem
        for link in node.outputs["Color"].links:
            target = link.to_node
            if target.type == "NORMAL_MAP":
                links[stem] = "Normal"
            else:
                links[stem] = link.to_socket.name
    return links


def test_import_creates_the_collection_with_one_sm_mesh_and_body_material(
    tmp_path: Path, empty_scene: None
) -> None:
    glb = _build_glb(tmp_path / "crate.glb")
    result = _run("import_glb", {"name": "Crate", "path": str(glb)})
    assert result == {
        "ok": True,
        "collection": "Crate",
        "mesh": "SM_Crate",
        "material": "M_Crate_Body",
        "merged_vertices": 16,
        "origin_offset": [0.0, 0.0, 0.5],
    }
    meshes = _mesh_objects("Crate")
    assert [obj.name for obj in meshes] == ["SM_Crate"]
    assert [slot.material.name for slot in meshes[0].material_slots] == ["M_Crate_Body"]
    assert "SM_Crate" not in bpy.context.scene.collection.objects


def test_seam_split_vertices_are_welded_and_the_topology_is_kept(
    tmp_path: Path, empty_scene: None
) -> None:
    glb, source = _build_seamed_cube_glb(tmp_path / "cube.glb")
    result = _run("import_glb", {"name": "Crate", "path": str(glb)})
    assert result["ok"] is True
    assert result["merged_vertices"] > 0
    (obj,) = _mesh_objects("Crate")
    mesh = obj.data
    assert len(mesh.vertices) == 8
    assert _island_count(mesh) == 1
    assert len(mesh.polygons) == source["faces"] == 12
    assert _corner_uvs(mesh) == source["uvs"]
    assert len(obj.material_slots) == source["slots"] == 1


def test_the_origin_moves_to_the_bottom_center_with_identity_transforms(
    tmp_path: Path, empty_scene: None
) -> None:
    glb, _ = _build_seamed_cube_glb(tmp_path / "cube.glb")
    assert _run("import_glb", {"name": "Crate", "path": str(glb)})["ok"] is True
    (obj,) = _mesh_objects("Crate")
    identity = mathutils.Matrix.Identity(4)
    for row, expected_row in zip(obj.matrix_world, identity, strict=True):
        for value, expected in zip(row, expected_row, strict=True):
            assert value == pytest.approx(expected, abs=1e-6)
    corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
    xs = [corner.x for corner in corners]
    ys = [corner.y for corner in corners]
    zs = [corner.z for corner in corners]
    assert (min(xs) + max(xs)) / 2 == pytest.approx(0.0, abs=1e-3)
    assert (min(ys) + max(ys)) / 2 == pytest.approx(0.0, abs=1e-3)
    assert min(zs) == pytest.approx(0.0, abs=1e-3)


def test_custom_normals_are_cleared_and_faces_smooth_with_outward_normals(
    tmp_path: Path, empty_scene: None
) -> None:
    glb, _ = _build_seamed_cube_glb(tmp_path / "cube.glb")
    assert _run("import_glb", {"name": "Crate", "path": str(glb)})["ok"] is True
    (obj,) = _mesh_objects("Crate")
    mesh = obj.data
    assert mesh.has_custom_normals is False
    assert all(poly.use_smooth for poly in mesh.polygons)
    faces_by_edge: dict[tuple[int, int], list[Any]] = {}
    for poly in mesh.polygons:
        for key in poly.edge_keys:
            faces_by_edge.setdefault(tuple(sorted(key)), []).append(poly)
    for edge in mesh.edges:
        first, second = faces_by_edge[tuple(sorted(edge.vertices))]
        sharper_than_30 = math.degrees(first.normal.angle(second.normal)) > 30.0
        assert edge.use_edge_sharp == sharper_than_30
    assert sum(edge.use_edge_sharp for edge in mesh.edges) == 12
    centroid = sum((vertex.co for vertex in mesh.vertices), mathutils.Vector()) / len(mesh.vertices)
    for poly in mesh.polygons:
        assert poly.normal.dot(poly.center - centroid) > 0


def test_the_import_result_reports_the_weld_and_the_origin_offset(
    tmp_path: Path, empty_scene: None
) -> None:
    glb, _ = _build_seamed_cube_glb(tmp_path / "cube.glb")
    result = _run("import_glb", {"name": "Crate", "path": str(glb)})
    expected_keys = {"ok", "collection", "mesh", "material", "merged_vertices", "origin_offset"}
    assert set(result) == expected_keys
    assert isinstance(result["merged_vertices"], int) and result["merged_vertices"] >= 0
    assert result["origin_offset"] == pytest.approx([-2.0, -3.0, -3.5], abs=1e-6)


def test_a_second_import_of_the_same_name_is_refused(tmp_path: Path, empty_scene: None) -> None:
    glb = _build_glb(tmp_path / "crate.glb")
    assert _run("import_glb", {"name": "Crate", "path": str(glb)})["ok"] is True
    second = _run("import_glb", {"name": "Crate", "path": str(glb)})
    assert second["ok"] is False
    assert second["error"]["code"] == "meshy.collection_exists"
    assert second["error"]["remediation"]


def test_several_imported_meshes_are_joined_into_one(tmp_path: Path, empty_scene: None) -> None:
    glb = _build_glb(tmp_path / "pair.glb", cubes=2)
    assert _run("import_glb", {"name": "Crate", "path": str(glb)})["ok"] is True
    assert [obj.name for obj in _mesh_objects("Crate")] == ["SM_Crate"]


def test_collection_state_reports_missing_exists_and_no_mesh(
    tmp_path: Path, empty_scene: None
) -> None:
    assert _run("collection_state", {"name": "Crate"}) == {"ok": True, "state": "missing"}
    glb = _build_glb(tmp_path / "crate.glb")
    _run("import_glb", {"name": "Crate", "path": str(glb)})
    assert _run("collection_state", {"name": "Crate"}) == {"ok": True, "state": "exists"}
    bpy.data.collections.new("Bare")
    bpy.context.scene.collection.children.link(bpy.data.collections["Bare"])
    assert _run("collection_state", {"name": "Bare"}) == {"ok": True, "state": "no_mesh"}


def test_export_writes_a_glb_of_the_collection_meshes(tmp_path: Path, empty_scene: None) -> None:
    glb = _build_glb(tmp_path / "crate.glb")
    _run("import_glb", {"name": "Crate", "path": str(glb)})
    out = tmp_path / "exported.glb"
    result = _run("export_glb", {"name": "Crate", "path": str(out)})
    assert result["ok"] is True
    assert out.read_bytes()[:4] == b"glTF"


@pytest.mark.parametrize("case", ["missing collection", "collection without SM mesh"])
def test_export_refuses_a_missing_collection_or_mesh(
    tmp_path: Path, empty_scene: None, case: str
) -> None:
    if case == "collection without SM mesh":
        bpy.data.collections.new("Crate")
        bpy.context.scene.collection.children.link(bpy.data.collections["Crate"])
    result = _run("export_glb", {"name": "Crate", "path": str(tmp_path / "out.glb")})
    assert result["ok"] is False
    assert result["error"]["code"] == "meshy.collection_not_found"
    assert not (tmp_path / "out.glb").exists()


def test_apply_maps_wires_four_maps_with_their_color_spaces(
    tmp_path: Path, empty_scene: None
) -> None:
    glb = _build_glb(tmp_path / "crate.glb")
    _run("import_glb", {"name": "Crate", "path": str(glb)})
    maps = {
        "base_color": str(_write_png(tmp_path / "base_color.png")),
        "normal": str(_write_png(tmp_path / "normal.png")),
        "roughness": str(_write_png(tmp_path / "roughness.png")),
        "metallic": str(_write_png(tmp_path / "metallic.png")),
    }
    result = _run("apply_maps", {"name": "Crate", "maps": maps})
    assert result == {
        "ok": True,
        "material": "M_Crate_Body",
        "maps": ["base_color", "metallic", "normal", "roughness"],
    }
    material = bpy.data.materials["M_Crate_Body"]
    assert _texture_links(material) == {
        "base_color": "Base Color",
        "normal": "Normal",
        "roughness": "Roughness",
        "metallic": "Metallic",
    }
    spaces = {
        Path(image.filepath).stem: image.colorspace_settings.name
        for image in bpy.data.images
        if Path(image.filepath).stem in {"base_color", "normal", "roughness", "metallic"}
    }
    assert spaces["base_color"] == "sRGB"
    assert spaces["normal"] == spaces["roughness"] == spaces["metallic"] == "Non-Color"
    assert {node.type for node in material.node_tree.nodes} >= {
        "BSDF_PRINCIPLED",
        "OUTPUT_MATERIAL",
        "NORMAL_MAP",
        "TEX_IMAGE",
    }


def test_apply_maps_replaces_the_objects_previous_material_slots(
    tmp_path: Path, empty_scene: None
) -> None:
    glb = _build_glb(tmp_path / "crate.glb")
    _run("import_glb", {"name": "Crate", "path": str(glb)})
    mesh = _mesh_objects("Crate")[0]
    mesh.data.materials.append(bpy.data.materials.new("Previous"))
    assert len(mesh.material_slots) == 2
    maps = {"base_color": str(_write_png(tmp_path / "base_color.png"))}
    assert _run("apply_maps", {"name": "Crate", "maps": maps})["ok"] is True
    assert [slot.material.name for slot in mesh.material_slots] == ["M_Crate_Body"]


def test_apply_maps_refuses_a_missing_collection(tmp_path: Path, empty_scene: None) -> None:
    maps = {"base_color": str(_write_png(tmp_path / "base_color.png"))}
    result = _run("apply_maps", {"name": "Crate", "maps": maps})
    assert result["error"]["code"] == "meshy.collection_not_found"


def test_an_unknown_operation_is_a_session_failure(empty_scene: None) -> None:
    result = _run("delete_everything", {"name": "Crate"})
    assert result["ok"] is False
    assert result["error"]["code"] == "meshy.session_failed"
