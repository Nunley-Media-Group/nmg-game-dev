"""Headless Blender tests for scripts/blender/meshy_session.py (#98 AC1, AC7, AC11).

Run with ``scripts/run-blender-tests.sh tests/blender/test_meshy_session.py``. Outside Blender the
module skips, because ``bpy`` is only importable inside Blender's bundled Python.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

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
    }
    meshes = _mesh_objects("Crate")
    assert [obj.name for obj in meshes] == ["SM_Crate"]
    assert [slot.material.name for slot in meshes[0].material_slots] == ["M_Crate_Body"]
    assert "SM_Crate" not in bpy.context.scene.collection.objects


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
