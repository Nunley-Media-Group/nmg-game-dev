"""Content hash and bake.json for the cache hit on an unchanged, already-baked asset.

The hash covers every mesh object in the collection (sorted by name): matrix, vertices, polygon
vertex indices, material indices, UV data, and each slot's material in canonical form (node types,
unlinked input values, node properties, image file bytes, and links). It also covers the asset
class, the resolved budgets, the mode, and BAKE_VERSION. Material names are excluded, so a rewired
asset hashes the same after a reopen.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import bpy
import numpy as np

BAKE_VERSION = "1"
MANIFEST = "bake.json"
_NODE_PROPERTY_TYPES = frozenset({"ENUM", "BOOLEAN", "INT", "FLOAT", "STRING"})
_NODE_PROPERTY_IGNORE = frozenset(
    {
        "name",
        "label",
        "location",
        "width",
        "height",
        "width_hidden",
        "select",
        "hide",
        "show_options",
        "show_preview",
        "show_texture",
        "use_custom_color",
        "color",
        "dimensions",
        "is_active_output",
    }
)


def hash_asset(meshes: list[bpy.types.Object], settings: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(json.dumps(settings, sort_keys=True, default=str).encode())
    for obj in sorted(meshes, key=lambda item: item.name):
        digest.update(obj.name.encode())
        digest.update(json.dumps([list(row) for row in obj.matrix_world]).encode())
        mesh = obj.data
        coords = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        mesh.vertices.foreach_get("co", coords)
        digest.update(coords.tobytes())
        loops = np.empty(len(mesh.loops), dtype=np.int32)
        mesh.loops.foreach_get("vertex_index", loops)
        digest.update(loops.tobytes())
        starts = np.empty(len(mesh.polygons), dtype=np.int32)
        totals = np.empty(len(mesh.polygons), dtype=np.int32)
        indices = np.empty(len(mesh.polygons), dtype=np.int32)
        mesh.polygons.foreach_get("loop_start", starts)
        mesh.polygons.foreach_get("loop_total", totals)
        mesh.polygons.foreach_get("material_index", indices)
        digest.update(starts.tobytes() + totals.tobytes() + indices.tobytes())
        for layer in mesh.uv_layers:
            digest.update(layer.name.encode())
            uvs = np.array([[item.uv.x, item.uv.y] for item in layer.data], dtype=np.float32)
            digest.update(uvs.tobytes())
        for slot in obj.material_slots:
            digest.update(json.dumps(_material_form(slot.material), sort_keys=True).encode())
    return digest.hexdigest()


def read_manifest(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / MANIFEST
    if not path.is_file():
        return None
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_manifest(out_dir: Path, result: dict[str, Any]) -> Path:
    path = out_dir / MANIFEST
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def is_cache_hit(manifest: dict[str, Any] | None, current_hash: str) -> bool:
    """True when the recorded baked hash matches and every recorded PNG still exists."""
    if manifest is None or manifest.get("baked_hash") != current_hash:
        return False
    paths = [*manifest.get("desktop_textures", []), *manifest.get("mobile_textures", [])]
    return bool(paths) and all(Path(path).is_file() for path in paths)


def _material_form(material: bpy.types.Material | None) -> dict[str, Any]:
    if material is None or material.node_tree is None:
        return {"material": None}
    tree = material.node_tree
    nodes: list[dict[str, Any]] = []
    for node in sorted(tree.nodes, key=lambda item: item.name):
        entry: dict[str, Any] = {"type": node.bl_idname, "name": node.name, "inputs": {}}
        entry["properties"] = _node_properties(node)
        for socket in node.inputs:
            if not socket.is_linked and hasattr(socket, "default_value"):
                entry["inputs"][socket.identifier] = _plain(socket.default_value)
        if node.type == "TEX_IMAGE" and node.image is not None:
            entry["image"] = _image_identity(node.image)
        nodes.append(entry)
    links = sorted(
        (
            link.from_node.name,
            link.from_socket.identifier,
            link.to_node.name,
            link.to_socket.identifier,
        )
        for link in tree.links
    )
    return {"nodes": nodes, "links": links}


def _node_properties(node: bpy.types.Node) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for prop in node.bl_rna.properties:
        if prop.is_readonly or prop.identifier in _NODE_PROPERTY_IGNORE:
            continue
        if prop.type not in _NODE_PROPERTY_TYPES:
            continue
        try:
            values[prop.identifier] = _plain(getattr(node, prop.identifier))
        except (AttributeError, TypeError):
            continue
    return values


def _image_identity(image: bpy.types.Image) -> str:
    path = Path(bpy.path.abspath(image.filepath_raw or image.filepath))
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return f"name:{image.name}"


def _plain(value: Any) -> Any:
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str | bool | int):
        return value
    if isinstance(value, set):
        return sorted(str(item) for item in value)
    try:
        return [_plain(item) for item in value]
    except TypeError:
        return str(value)
