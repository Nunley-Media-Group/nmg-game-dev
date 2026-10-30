"""content_hash: the asset identity every finalize step is keyed on (#69, design § Cache).

The hash covers <Name> and <Name>_Mobile when the Mobile collection exists. Each object in them,
sorted by name, contributes its type, parent, world matrix, and modifier stack (type and scalar
properties, without UI-only flags). Meshes also contribute their vertex coordinates, loop vertex
indices, polygon starts, counts, and material indices, and each UV layer. Each material slot
contributes the canonical form that bake_core uses for its own hash (#67), which includes the
bytes of every image file. Material names are excluded, as they are in #67, so a reopened file
with the same content hashes the same.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

import bpy
import numpy as np

from ..bake_core.cache import _material_form

MOBILE_SUFFIX: Final = "_Mobile"
_UI_MODIFIER_PROPERTIES: Final = frozenset({"show_expanded", "is_active"})
_SCALAR_PROPERTY_TYPES: Final = frozenset({"ENUM", "BOOLEAN", "INT", "FLOAT", "STRING"})


def content_hash(collection_name: str) -> str:
    """Return the SHA-256 hex digest of <collection_name> and its Mobile sibling when present.

    Reads only. The view layer is updated first so matrix_world reflects the current transforms.
    """
    bpy.context.view_layer.update()
    digest = hashlib.sha256()
    digest.update(collection_name.encode())
    for name in (collection_name, f"{collection_name}{MOBILE_SUFFIX}"):
        collection = bpy.data.collections.get(name)
        if collection is None:
            continue
        digest.update(f"\x00collection:{name}".encode())
        for obj in sorted(collection.all_objects, key=lambda item: item.name):
            _update_object(digest, obj)
    return digest.hexdigest()


def _update_object(digest: Any, obj: bpy.types.Object) -> None:
    form = {
        "name": obj.name,
        "type": obj.type,
        "parent": obj.parent.name if obj.parent is not None else None,
        "matrix": [[float(value) for value in row] for row in obj.matrix_world],
        "modifiers": [_modifier_form(modifier) for modifier in obj.modifiers],
        "slots": [_material_form(slot.material) for slot in obj.material_slots],
    }
    digest.update(_dump(form))
    if obj.type == "MESH":
        _update_mesh(digest, obj.data)


def _update_mesh(digest: Any, mesh: bpy.types.Mesh) -> None:
    coords = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", coords)
    loops = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loops)
    starts = np.empty(len(mesh.polygons), dtype=np.int32)
    totals = np.empty(len(mesh.polygons), dtype=np.int32)
    indices = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get("loop_start", starts)
    mesh.polygons.foreach_get("loop_total", totals)
    mesh.polygons.foreach_get("material_index", indices)
    digest.update(coords.tobytes())
    digest.update(loops.tobytes())
    digest.update(starts.tobytes() + totals.tobytes() + indices.tobytes())
    for layer in mesh.uv_layers:
        digest.update(layer.name.encode())
        uvs = np.empty(len(layer.data) * 2, dtype=np.float32)
        layer.data.foreach_get("uv", uvs)
        digest.update(uvs.tobytes())


def _modifier_form(modifier: bpy.types.Modifier) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for prop in modifier.bl_rna.properties:
        identifier = prop.identifier
        if identifier == "rna_type" or prop.is_readonly or identifier in _UI_MODIFIER_PROPERTIES:
            continue
        if prop.type in _SCALAR_PROPERTY_TYPES:
            properties[identifier] = _plain(getattr(modifier, identifier))
        elif prop.type == "POINTER":
            value = getattr(modifier, identifier, None)
            if isinstance(value, bpy.types.ID):
                properties[identifier] = f"id:{value.name}"
    return {"name": modifier.name, "type": modifier.type, "properties": properties}


def _dump(form: Any) -> bytes:
    return json.dumps(form, sort_keys=True, default=str).encode()


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
