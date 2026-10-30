"""load_back: replace the open session's <Name> and <Name>_Mobile with a finalize result (#69, AC2).

The host calls this in the live session after every Blender step passed. If the session's content
hash no longer matches the checkpoint hash, nothing is replaced. Otherwise the session's old
datablocks are renamed under OLD_PREFIX, the result's collections are appended, linked where the
old ones lived, and the renamed datablocks are deleted. Any failure before that deletion restores
the old names and removes what was appended.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

import bpy

from .hashing import MOBILE_SUFFIX, content_hash

OLD_PREFIX: Final = "__nmg_old_"
LOAD_BACK_CODE: Final = "finalize.load_back_failed"

_Renamed = list[tuple[Any, str]]


class LoadBackError(Exception):
    """The result could not be loaded. The session keeps its datablocks under their old names."""

    def __init__(self, message: str, remediation: str) -> None:
        super().__init__(message)
        self.code = LOAD_BACK_CODE
        self.message = message
        self.remediation = remediation


def load_back(result_blend: str, collection_name: str, expected_hash: str) -> dict[str, Any]:
    """Replace <collection_name> (and its Mobile sibling) with the result file's copies.

    Returns {"loaded": True, "hash": <post-load content hash>} on success, or
    {"loaded": False, "reason": "session_changed"} without touching the session when its hash
    differs from expected_hash. Raises LoadBackError when the result cannot be loaded.
    """
    if content_hash(collection_name) != expected_hash:
        return {"loaded": False, "reason": "session_changed"}

    targets = _result_targets(result_blend, collection_name)
    scene_collection = bpy.context.scene.collection
    parents = {
        name: _parents_of(bpy.data.collections[name], scene_collection)
        for name in targets
        if name in bpy.data.collections
    }
    before = _snapshot()
    renamed: _Renamed = []
    try:
        for name in targets:
            if name in bpy.data.collections:
                _mark_old(bpy.data.collections[name], renamed)
        # Blender rewrites the list it is given with the loaded datablocks, so pass a copy.
        with bpy.data.libraries.load(result_blend, link=False) as (_source, loaded):
            loaded.collections = list(targets)
        for name in targets:
            new = _appended_collection(name, before)
            for parent in parents.get(name) or [scene_collection]:
                parent.children.link(new)
        _remove_old(renamed)
    except Exception as error:
        _restore(renamed, before)
        raise LoadBackError(
            f"Load-back of {collection_name} from {result_blend} failed: {error}",
            "The session was left as it was. Rerun finalize; if it fails again, open "
            f"{result_blend} in Blender and check that it holds {collection_name}.",
        ) from error

    bpy.context.view_layer.update()
    return {"loaded": True, "hash": content_hash(collection_name)}


def _result_targets(result_blend: str, collection_name: str) -> list[str]:
    try:
        with bpy.data.libraries.load(result_blend, link=False) as (source, _loaded):
            available = set(source.collections)
    except (OSError, RuntimeError) as error:
        raise LoadBackError(
            f"The result file {result_blend} cannot be read: {error}",
            "Rerun the bake and variants steps so they write a readable result .blend.",
        ) from error
    targets = [
        name for name in (collection_name, f"{collection_name}{MOBILE_SUFFIX}") if name in available
    ]
    if collection_name not in targets:
        raise LoadBackError(
            f"The result file {result_blend} holds no collection named {collection_name}.",
            "Rerun the variants step for this asset, then load its result.",
        )
    return targets


def _parents_of(collection: Any, scene_collection: Any) -> list[Any]:
    candidates = [scene_collection, *bpy.data.collections]
    return [
        parent
        for parent in candidates
        if parent != collection and any(child == collection for child in parent.children)
    ]


def _mark_old(collection: Any, renamed: _Renamed) -> None:
    """Rename the collection and everything it owns under OLD_PREFIX, once per datablock."""
    seen: set[int] = set()

    def mark(block: Any) -> None:
        pointer = block.as_pointer()
        if pointer in seen:
            return
        seen.add(pointer)
        renamed.append((block, block.name))
        block.name = OLD_PREFIX + block.name

    mark(collection)
    objects = list(collection.all_objects)
    for obj in objects:
        mark(obj)
    for obj in objects:
        if isinstance(obj.data, bpy.types.Mesh):
            mark(obj.data)
    for obj in objects:
        for slot in obj.material_slots:
            if slot.material is not None:
                mark(slot.material)
    for obj in objects:
        if isinstance(obj.data, bpy.types.Mesh):
            for material in obj.data.materials:
                if material is not None:
                    mark(material)
    for obj in objects:
        for slot in obj.material_slots:
            material = slot.material
            if material is None or material.node_tree is None:
                continue
            for node in material.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image is not None:
                    mark(node.image)


def _remove_old(renamed: _Renamed) -> None:
    """Delete the renamed datablocks, dependants first so each one is removed once."""
    removers: list[tuple[type, Callable[[Any], None]]] = [
        (bpy.types.Object, lambda block: bpy.data.objects.remove(block, do_unlink=True)),
        (bpy.types.Mesh, lambda block: bpy.data.meshes.remove(block, do_unlink=True)),
        (bpy.types.Material, lambda block: bpy.data.materials.remove(block, do_unlink=True)),
        (bpy.types.Image, lambda block: bpy.data.images.remove(block, do_unlink=True)),
        (bpy.types.Collection, lambda block: bpy.data.collections.remove(block, do_unlink=True)),
    ]
    for kind, remove in removers:
        for block, _original in renamed:
            if isinstance(block, kind):
                remove(block)


_DATA_KEYS: Final = ("objects", "meshes", "materials", "images", "collections", "node_groups")
# Dependants before the blocks they use, so removing a block never invalidates one still listed.
_RESTORE_ORDER: Final = ("objects", "collections", "meshes", "materials", "images", "node_groups")


def _snapshot() -> dict[str, set[int]]:
    return {key: {block.as_pointer() for block in getattr(bpy.data, key)} for key in _DATA_KEYS}


def _appended_collection(name: str, before: dict[str, set[int]]) -> Any:
    collection = bpy.data.collections.get(name)
    if collection is None or collection.as_pointer() in before["collections"]:
        raise LoadBackError(
            f"The result file did not bring in a collection named {name}.",
            "Rerun the variants step, then load its result again.",
        )
    return collection


def _restore(renamed: _Renamed, before: dict[str, set[int]]) -> None:
    """Remove what load-back appended, then give the renamed datablocks their old names back."""
    for key in _RESTORE_ORDER:
        datablocks = getattr(bpy.data, key)
        for block in list(datablocks):
            if block.as_pointer() in before[key]:
                continue
            try:
                datablocks.remove(block, do_unlink=True)
            except ReferenceError:
                continue
    for block, original in renamed:
        try:
            block.name = original
        except ReferenceError:
            continue
