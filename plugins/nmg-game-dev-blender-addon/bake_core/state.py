"""Snapshot and restore of everything a bake changes in the open file.

``release`` always runs: it puts back render visibility and the scene's render settings.
``rollback`` runs only when the bake raises after mutation started: it puts back material slots,
face material indices, UV layers, material names, and removes datablocks the run created.
"""

from __future__ import annotations

from collections.abc import Iterable
from types import TracebackType
from typing import Any

import bpy
import numpy as np

# Datablock collections a failed run can leave behind.
_DATA_KINDS = ("objects", "meshes", "materials", "images", "lights", "cameras", "worlds")


class BakeState:
    def __init__(self, collection: bpy.types.Collection, meshes: list[bpy.types.Object]) -> None:
        self.collection = collection
        self.meshes = meshes
        self.scene = bpy.context.scene
        self._created_before = _datablock_pointers()
        self._slots = {mesh.name: list(mesh.data.materials) for mesh in meshes}
        self._indices = {mesh.name: _polygon_materials(mesh) for mesh in meshes}
        self._uv = {mesh.name: _uv_state(mesh) for mesh in meshes}
        self._names: dict[int, tuple[bpy.types.Material, str]] = {}
        self._flags: dict[str, bool] = {}
        self._layer = _layer_collection(bpy.context.view_layer, collection)
        self._excluded = self._layer.exclude if self._layer is not None else False
        self._render = _render_settings(self.scene)

    def __enter__(self) -> BakeState:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
        if exc_type is not None:
            self.rollback()

    def track_names(self, materials: Iterable[bpy.types.Material]) -> None:
        """Remember original material names so a rollback can restore them."""
        for material in materials:
            self._names.setdefault(material.as_pointer(), (material, material.name))

    def make_render_enabled(self) -> None:
        """Show the asset and hide every other object in the scene, for the bake and proof.

        Other objects (set dressing, previews, the default scene's cube) would otherwise occlude
        the asset: AO rays hit them and bake to black. Restored by release.
        """
        members = {obj.name for obj in self.collection.all_objects}
        for obj in self.scene.objects:
            self._flags.setdefault(obj.name, obj.hide_render)
            obj.hide_render = obj.name not in members
        if self._layer is not None:
            self._layer.exclude = False

    def release(self) -> None:
        for name, hidden in self._flags.items():
            obj = bpy.data.objects.get(name)
            if obj is not None:
                obj.hide_render = hidden
        if self._layer is not None:
            self._layer.exclude = self._excluded
        _restore_render_settings(self.scene, self._render)

    def rollback(self) -> None:
        for mesh in self.meshes:
            _set_slots(mesh, self._slots[mesh.name])
            mesh.data.polygons.foreach_set("material_index", self._indices[mesh.name])
            _restore_uv(mesh, self._uv[mesh.name])
        _remove_created(self._created_before)
        for material, name in self._names.values():
            if material.name != name and material.name in bpy.data.materials:
                material.name = name


def _datablock_pointers() -> dict[str, set[int]]:
    return {kind: {item.as_pointer() for item in getattr(bpy.data, kind)} for kind in _DATA_KINDS}


def _remove_created(before: dict[str, set[int]]) -> None:
    for obj in list(bpy.data.objects):
        if obj.as_pointer() not in before["objects"]:
            bpy.data.objects.remove(obj, do_unlink=True)
    for kind, remove in (
        ("materials", bpy.data.materials.remove),
        ("images", bpy.data.images.remove),
        ("meshes", bpy.data.meshes.remove),
        ("lights", bpy.data.lights.remove),
        ("cameras", bpy.data.cameras.remove),
        ("worlds", bpy.data.worlds.remove),
    ):
        for item in list(getattr(bpy.data, kind)):
            if item.as_pointer() not in before[kind]:
                remove(item)


def _polygon_materials(mesh: bpy.types.Object) -> list[int]:
    indices = [0] * len(mesh.data.polygons)
    mesh.data.polygons.foreach_get("material_index", indices)
    return indices


def _uv_state(mesh: bpy.types.Object) -> dict[str, Any]:
    """Names, active indices, and coordinates of every UV layer.

    Finalizing a bake removes the authored layer, so a rollback has to rebuild it from these
    coordinates rather than only restoring names.
    """
    layers = mesh.data.uv_layers
    stored = []
    for layer in layers:
        coords = np.empty(len(layer.data) * 2, dtype=np.float32)
        layer.data.foreach_get("uv", coords)
        stored.append((layer.name, coords))
    return {
        "layers": stored,
        "active": layers.active_index if len(layers) else -1,
        "render": layers.active_render_index if len(layers) else -1,
    }


def _restore_uv(mesh: bpy.types.Object, state: dict[str, Any]) -> None:
    layers = mesh.data.uv_layers
    while len(layers):
        layers.remove(layers[0])
    for name, coords in state["layers"]:
        layer = layers.new(name=name)
        layer.data.foreach_set("uv", coords)
    if state["layers"]:
        layers.active_index = state["active"]
        layers.active_render_index = state["render"]


def _set_slots(mesh: bpy.types.Object, materials: list[bpy.types.Material | None]) -> None:
    while len(mesh.data.materials):
        mesh.data.materials.pop()
    for material in materials:
        mesh.data.materials.append(material)


def _layer_collection(
    view_layer: bpy.types.ViewLayer, collection: bpy.types.Collection
) -> bpy.types.LayerCollection | None:
    stack = [view_layer.layer_collection]
    while stack:
        layer = stack.pop()
        if layer.collection == collection:
            return layer
        stack.extend(layer.children)
    return None


def _render_settings(scene: bpy.types.Scene) -> dict[str, Any]:
    return {
        "engine": scene.render.engine,
        "samples": scene.cycles.samples,
        "device": scene.cycles.device,
    }


def _restore_render_settings(scene: bpy.types.Scene, settings: dict[str, Any]) -> None:
    scene.render.engine = settings["engine"]
    scene.cycles.samples = settings["samples"]
    scene.cycles.device = settings["device"]
