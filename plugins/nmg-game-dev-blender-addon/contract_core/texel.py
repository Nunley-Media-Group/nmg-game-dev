"""Texel density per material slot: the measure and the exemptions, shared by validation and bake.

A slot is the set of faces of one mesh that share a material index. Its density is
``px * sqrt(UV area / world area)`` over those faces only, compared with the variant minimum on its
own (contract section 6). A slot is exempt when its material carries the trim-atlas marker, or when
its UVs are collapsed onto one flat-colour cell.

Only ``slot_areas``, ``evaluated_copy`` and ``is_trim_atlas`` touch bpy, and they take duck-typed
objects. ``classify``, ``density`` and ``slot_entry`` take plain values, so the unit suite
loads this file by path under plain CPython.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

TRIM_ATLAS_PROPERTY: Final = "nmg_trim_atlas"
FLAT_COLOUR_UV_AREA: Final = 1e-8
DESKTOP_MIN: Final = 256.0
MOBILE_MIN: Final = 128.0


@dataclass(frozen=True)
class SlotArea:
    """One material slot's summed UV area, summed world area, and trim-atlas marker."""

    slot: int
    material: Any
    uv_area: float
    world_area: float
    trim_atlas: bool

    @property
    def name(self) -> str:
        """The material's name, or 'slot N' for a slot without a material."""
        return self.material.name if self.material is not None else f"slot {self.slot}"

    @property
    def kind(self) -> str:
        """How the slot is treated: trim_atlas, flat_colour, skipped, or measured."""
        return classify(self.uv_area, self.world_area, self.trim_atlas)


def classify(uv_area: float, world_area: float, trim_atlas: bool) -> str:
    """Return trim_atlas (marker), flat_colour (UV area at or below the cut-off), skipped (no
    world area), or measured, checked in that order."""
    if trim_atlas:
        return "trim_atlas"
    if uv_area <= FLAT_COLOUR_UV_AREA:
        return "flat_colour"
    if world_area <= 0.0:
        return "skipped"
    return "measured"


def density(px: float, uv_area: float, world_area: float) -> float:
    """Texels per metre for a slot: px * sqrt(UV area / world area). Measure only when world > 0."""
    return px * math.sqrt(uv_area / world_area)


def slot_entry(slot: SlotArea, pixels: Mapping[str, float | None]) -> dict[str, Any] | None:
    """The report entry for one slot.

    A measured slot lists px/m for each variant in ``pixels``; a variant with no image to measure
    gives None. An exempt slot lists its reason. A skipped slot has no area to report, so None.
    """
    kind = slot.kind
    if kind == "skipped":
        return None
    if kind != "measured":
        return {"slot": slot.slot, "material": slot.name, "exempt": kind}
    entry: dict[str, Any] = {"slot": slot.slot, "material": slot.name}
    for variant, px in pixels.items():
        measured = None if px is None else density(px, slot.uv_area, slot.world_area)
        entry[variant] = None if measured is None else round(measured, 1)
    return entry


def is_trim_atlas(material: Any) -> bool:
    """True when the material carries the trim-atlas marker, set in the UI or from a script."""
    return material is not None and bool(material.get(TRIM_ATLAS_PROPERTY, False))


def slot_areas(obj: Any, mesh: Any) -> list[SlotArea]:
    """Sum each material slot's UV and world areas over the evaluated mesh copy.

    The UV area uses the render-active layer (layer 0 when none is render-active), with fan
    triangles. The world area is each face's fan triangles after ``obj.matrix_world``. Slots with
    no faces are omitted.
    """
    layer = _render_layer(mesh)
    matrix = obj.matrix_world
    uv_totals: dict[int, float] = {}
    world_totals: dict[int, float] = {}
    for poly in mesh.polygons:
        index = poly.material_index
        uv_totals[index] = uv_totals.get(index, 0.0) + _uv_face_area(layer, poly)
        world_totals[index] = world_totals.get(index, 0.0) + _world_face_area(matrix, mesh, poly)
    slots: list[SlotArea] = []
    for index in sorted(uv_totals):
        material = obj.material_slots[index].material if index < len(obj.material_slots) else None
        slots.append(
            SlotArea(
                slot=index,
                material=material,
                uv_area=uv_totals[index],
                world_area=world_totals[index],
                trim_atlas=is_trim_atlas(material),
            )
        )
    return slots


def evaluated_copy(obj: Any) -> Any:
    """A mesh of ``obj`` with its modifiers applied, in object space. The caller removes it."""
    import bpy  # Lazy: the pure helpers above load under CPython, where bpy is not installed.

    depsgraph = bpy.context.evaluated_depsgraph_get()
    return bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), depsgraph=depsgraph)


def _render_layer(mesh: Any) -> Any:
    layers = mesh.uv_layers
    if len(layers) == 0:
        return None
    active = layers.active_render
    return active if active is not None else layers[0]


def _uv_face_area(layer: Any, poly: Any) -> float:
    if layer is None:
        return 0.0
    uvs = [
        layer.data[index].uv for index in range(poly.loop_start, poly.loop_start + poly.loop_total)
    ]
    total = 0.0
    for index in range(1, len(uvs) - 1):
        a, b, c = uvs[0], uvs[index], uvs[index + 1]
        total += abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)) / 2
    return total


def _world_face_area(matrix: Any, mesh: Any, poly: Any) -> float:
    corners = [matrix @ mesh.vertices[index].co for index in poly.vertices]
    total = 0.0
    for index in range(1, len(corners) - 1):
        total += (corners[index] - corners[0]).cross(corners[index + 1] - corners[0]).length / 2
    return total
