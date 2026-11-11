"""Tiling mode for environment pieces: a seamless bake on a temporary 1 m tile, and the checks.

Each tiling material is baked onto a 1 m plane whose UVs span 0 to 1, so the texture image is
exactly one UV period. The seam check judges each wrap against the texture's own interior
difference (seam_metric). Texel density is checked per mesh against the contract minimum
(256 px/m Desktop, 128 px/m Mobile).
"""

from __future__ import annotations

import math

import bmesh
import bpy
import numpy as np

from . import seam_metric
from .errors import BakeError
from .uv import uv_area, world_area

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
    """Largest wrap difference across both axes: the mean absolute first-vs-last pixel step."""
    return max(seam.wrap for seam in seam_metric.measure(rgb))


def check_seams(name: str, channels: dict[str, np.ndarray]) -> dict[str, float]:
    """Raise not_seamless unless every channel's wrap passes the interior-relative seam measure."""
    measured = {kind: seam_metric.measure(rgb) for kind, rgb in channels.items()}
    failing = sorted(kind for kind, seams in measured.items() if not all(s.passes for s in seams))
    if failing:
        details = ", ".join(seam_metric.failure_detail(kind, measured[kind]) for kind in failing)
        raise BakeError(
            "not_seamless",
            f"Tiling material '{name}' is not seamless ({details}); a wrap may differ by at most "
            f"{seam_metric.SEAM_RATIO:g}x the interior difference "
            f"(minimum {seam_metric.SEAM_FLOOR:.3f}).",
            target=name,
        )
    return {kind: max(seam.wrap for seam in seams) for kind, seams in measured.items()}


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
