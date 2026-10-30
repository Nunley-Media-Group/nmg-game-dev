"""Tiling mode for environment pieces: a seamless bake on a temporary 1 m tile, and the checks.

Each tiling material is baked onto a 1 m plane whose UVs span 0 to 1, so the texture image is
exactly one UV period. The seam check compares opposite edges. Texel density is checked per mesh
against the contract minimum (256 px/m Desktop, 128 px/m Mobile).
"""

from __future__ import annotations

import math

import bmesh
import bpy
import numpy as np

from .errors import BakeError
from .uv import uv_area, world_area

SEAM_TOLERANCE = 0.04
DESKTOP_DENSITY_MIN = 256.0
MOBILE_DENSITY_MIN = 128.0
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
) -> dict[str, dict[str, float]]:
    """Raise texel_density unless every mesh meets the Desktop and Mobile minimums."""
    report: dict[str, dict[str, float]] = {}
    for obj in meshes:
        uv_total = uv_area(obj, obj.data.uv_layers.active_render.name)
        area = world_area(obj)
        ratio = math.sqrt(uv_total / area) if area > 0.0 and uv_total > 0.0 else 0.0
        desktop = desktop_px * ratio
        mobile = mobile_px * ratio
        report[obj.name] = {"desktop": desktop, "mobile": mobile}
        if desktop < DESKTOP_DENSITY_MIN:
            raise _density(obj.name, "Desktop", desktop, DESKTOP_DENSITY_MIN)
        if mobile < MOBILE_DENSITY_MIN:
            raise _density(obj.name, "Mobile", mobile, MOBILE_DENSITY_MIN)
    return report


def _density(name: str, variant: str, measured: float, minimum: float) -> BakeError:
    return BakeError(
        "texel_density",
        f"Mesh '{name}' has {measured:.1f} px/m at {variant} size; the minimum is {minimum:.0f}.",
        target=name,
    )
