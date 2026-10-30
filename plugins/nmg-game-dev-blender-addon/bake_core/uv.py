"""UV handling for the bake: keep a valid UVMap layout, or joint-unwrap into a new layer.

The unwrap layer is made active for baking but not active-render, so the authoring coordinates
still evaluate while the bake writes into the new layout. Finalizing removes the other layers
and renames the new one UVMap.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import bpy

from ..contract_core.uv import OVERLAP_LIMIT, polygon_overlap_fraction
from .errors import BakeError

UV_MAP = "UVMap"
UNWRAP_LAYER = "__nmg_bake_uv"
ANGLE_LIMIT = math.radians(66.0)
ISLAND_MARGIN = 0.01

Face = tuple[int, Sequence[tuple[float, float]]]


def layout_is_valid(meshes: list[bpy.types.Object], groups: Iterable[Iterable[Face]]) -> bool:
    """True when every mesh has exactly one UVMap inside 0-1 and no group of faces overlaps.

    The unique bake only writes texels inside the unit square, so a layout that tiles past 1 is
    not valid for it: it is unwrapped instead, like an overlapping one.
    """
    for obj in meshes:
        layers = obj.data.uv_layers
        if len(layers) != 1 or layers[0].name != UV_MAP:
            return False
        for item in layers[0].data:
            if not (0.0 <= item.uv.x <= 1.0 and 0.0 <= item.uv.y <= 1.0):
                return False
    for group in groups:
        if polygon_overlap_fraction(group) > OVERLAP_LIMIT:
            return False
    return True


def faces_of(
    meshes: list[bpy.types.Object], source_of: dict[str, list[int]]
) -> dict[int, list[Face]]:
    """Group every face's UV corners by its source material index (merged callers pass 0)."""
    groups: dict[int, list[Face]] = {}
    face_id = 0
    for obj in meshes:
        layer = obj.data.uv_layers.active
        slot_sources = source_of[obj.name]
        for poly in obj.data.polygons:
            key = slot_sources[poly.material_index]
            corners: list[tuple[float, float]] = []
            if layer is not None:
                corners = [
                    (layer.data[index].uv.x, layer.data[index].uv.y)
                    for index in range(poly.loop_start, poly.loop_start + poly.loop_total)
                ]
            groups.setdefault(key, []).append((face_id, corners))
            face_id += 1
    return groups


def joint_unwrap(meshes: list[bpy.types.Object]) -> None:
    """Smart-unwrap every mesh together into a new layer, made active for the bake."""
    for obj in meshes:
        if not len(obj.data.polygons):
            raise BakeError(
                "uv_unwrap_failed",
                f"Mesh '{obj.name}' has no faces to unwrap.",
                target=obj.name,
            )
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in meshes:
        layers = obj.data.uv_layers
        layers.new(name=UNWRAP_LAYER)
        layers.active_index = len(layers) - 1
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=ANGLE_LIMIT, island_margin=ISLAND_MARGIN)
    bpy.ops.object.mode_set(mode="OBJECT")
    for obj in meshes:
        if uv_area(obj, UNWRAP_LAYER) <= 0.0:
            raise BakeError(
                "uv_unwrap_failed",
                f"Mesh '{obj.name}' has no UV area after the unwrap.",
                target=obj.name,
            )


def finalize_unwrap(meshes: list[bpy.types.Object]) -> None:
    """Keep only the unwrap layer, renamed UVMap and set as the active render map."""
    for obj in meshes:
        _keep_only(obj, UNWRAP_LAYER)
        layers = obj.data.uv_layers
        layers[UNWRAP_LAYER].name = UV_MAP
        layers.active_index = 0
        layers.active_render_index = 0


def finalize_tiling(meshes: list[bpy.types.Object]) -> None:
    """Keep the active render map, renamed UVMap, and remove the rest (tiling mode)."""
    for obj in meshes:
        layers = obj.data.uv_layers
        render_name = layers.active_render.name if len(layers) else ""
        _keep_only(obj, render_name)
        layers = obj.data.uv_layers
        layers[0].name = UV_MAP
        layers.active_index = 0
        layers.active_render_index = 0


def require_uv_layers(meshes: list[bpy.types.Object]) -> None:
    for obj in meshes:
        if not len(obj.data.uv_layers):
            raise BakeError(
                "uv_missing",
                f"Mesh '{obj.name}' has no UV map, so its tiling textures cannot be placed.",
                target=obj.name,
            )


def uv_area(obj: bpy.types.Object, layer_name: str) -> float:
    """Sum of the UV-space polygon areas of one layer, in square UV units."""
    layer = obj.data.uv_layers.get(layer_name)
    if layer is None:
        return 0.0
    total = 0.0
    for poly in obj.data.polygons:
        points = [
            layer.data[index].uv
            for index in range(poly.loop_start, poly.loop_start + poly.loop_total)
        ]
        total += _polygon_area([(p.x, p.y) for p in points])
    return total


def world_area(obj: bpy.types.Object) -> float:
    """Sum of the world-space polygon areas, in square meters."""
    matrix = obj.matrix_world
    total = 0.0
    for poly in obj.data.polygons:
        corners = [matrix @ obj.data.vertices[index].co for index in poly.vertices]
        for index in range(1, len(corners) - 1):
            total += (corners[index] - corners[0]).cross(corners[index + 1] - corners[0]).length / 2
    return total


def _polygon_area(points: Sequence[tuple[float, float]]) -> float:
    area = 0.0
    for index in range(len(points)):
        x0, y0 = points[index]
        x1, y1 = points[(index + 1) % len(points)]
        area += x0 * y1 - x1 * y0
    return abs(area) / 2


def _keep_only(obj: bpy.types.Object, name: str) -> None:
    layers = obj.data.uv_layers
    for layer in [layer for layer in layers if layer.name != name]:
        layers.remove(layer)
