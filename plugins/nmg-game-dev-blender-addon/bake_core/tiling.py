"""Tiling mode for environment pieces: a seamless bake on a temporary 1 m tile, and the checks.

Each tiling material is baked onto a 1 m plane whose UVs span 0 to 1, so the texture image is
exactly one UV period. The seam check compares opposite edges. Texel density is checked per material
slot against the contract minimum (256 px/m Desktop, 128 px/m Mobile), with the same measure and
exemptions as contract validation (contract_core/texel.py).
"""

from __future__ import annotations

from typing import Any

import bmesh
import bpy
import numpy as np

from ..contract_core import texel
from .errors import BakeError

SEAM_TOLERANCE = 0.04
DESKTOP_DENSITY_MIN = texel.DESKTOP_MIN
MOBILE_DENSITY_MIN = texel.MOBILE_MIN
TILE_NAME = "__nmg_bake_tile"


def make_tile() -> bpy.types.Object:
    """A 1 m square in the XY plane with one UVMap spanning 0 to 1, linked to the scene."""
    mesh = bpy.data.meshes.new(TILE_NAME)
    bm = bmesh.new()
    corners = [
        bm.verts.new((-0.5, -0.5, 0.0)),
        bm.verts.new((0.5, -0.5, 0.0)),
        bm.verts.new((0.5, 0.5, 0.0)),
        bm.verts.new((-0.5, 0.5, 0.0)),
    ]
    bm.faces.new(corners)
    bm.to_mesh(mesh)
    bm.free()
    layer = mesh.uv_layers.new(name="UVMap")
    for loop in mesh.loops:
        co = mesh.vertices[loop.vertex_index].co
        layer.data[loop.index].uv = (co.x + 0.5, co.y + 0.5)
    obj = bpy.data.objects.new(TILE_NAME, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def seam_error(rgb: np.ndarray) -> float:
    """Largest mean absolute difference between opposite edges (first vs last column or row)."""
    columns = np.mean(np.abs(rgb[:, 0, :] - rgb[:, -1, :]))
    rows = np.mean(np.abs(rgb[0, :, :] - rgb[-1, :, :]))
    return float(max(columns, rows))


def check_seams(name: str, channels: dict[str, np.ndarray]) -> dict[str, float]:
    """Raise not_seamless unless every channel's opposite edges match within tolerance."""
    errors = {kind: seam_error(rgb) for kind, rgb in channels.items()}
    failing = {kind: value for kind, value in errors.items() if value > SEAM_TOLERANCE}
    if failing:
        worst = ", ".join(f"{kind} {value:.3f}" for kind, value in sorted(failing.items()))
        raise BakeError(
            "not_seamless",
            f"Tiling material '{name}' is not seamless ({worst}; tolerance {SEAM_TOLERANCE}).",
            target=name,
        )
    return errors


def check_density(
    meshes: list[bpy.types.Object], desktop_px: int, mobile_px: int
) -> dict[str, list[dict[str, Any]]]:
    """Raise texel_density for the first measured slot below a minimum, in mesh then slot order.

    Each mesh is measured on an evaluated copy, which is removed again, so the bake and validation
    see the same faces. Returns {mesh name: slot entries} for the bake report; exempt slots are
    listed with their reason and are not checked.
    """
    report: dict[str, list[dict[str, Any]]] = {}
    for obj in meshes:
        copy = texel.evaluated_copy(obj)
        try:
            slots = texel.slot_areas(obj, copy)
        finally:
            bpy.data.meshes.remove(copy)
        entries: list[dict[str, Any]] = []
        for slot in slots:
            entry = texel.slot_entry(slot, {"desktop": desktop_px, "mobile": mobile_px})
            if entry is None:
                continue
            entries.append(entry)
            if slot.kind != "measured":
                continue
            desktop = texel.density(desktop_px, slot.uv_area, slot.world_area)
            mobile = texel.density(mobile_px, slot.uv_area, slot.world_area)
            if desktop < DESKTOP_DENSITY_MIN:
                raise _density(obj.name, slot.name, "Desktop", desktop, DESKTOP_DENSITY_MIN)
            if mobile < MOBILE_DENSITY_MIN:
                raise _density(obj.name, slot.name, "Mobile", mobile, MOBILE_DENSITY_MIN)
        report[obj.name] = entries
    return report


def _density(name: str, slot: str, variant: str, measured: float, minimum: float) -> BakeError:
    return BakeError(
        "texel_density",
        f"Mesh '{name}' slot '{slot}' has {measured:.1f} px/m at {variant} size; the minimum is "
        f"{minimum:.0f}.",
        target=name,
    )
