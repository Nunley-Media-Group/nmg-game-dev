"""Terrain contract checks: the heightmap grid, its paint layers, and the terrain report (#154).

A terrain collection holds one mesh, SM_<Name>: an n x n grid with one vertex per grid point,
1 m apart on X and Y and centred on the origin. Each paint layer is a Layer_<LayerName> float
point attribute with values in 0-1, mapped to the material M_<Name>_<LayerName>. The checks read
an evaluated copy, so the scene is never changed.

Grid order follows terrain_core/heightfield.py: row 0 is the +Y edge and column 0 the -X edge.
Heights are metres in Blender Z. UV overlap is not checked, because terrain tiles.
"""

from __future__ import annotations

import math
from array import array
from bisect import bisect_left
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import bpy

from ..terrain_core.heightfield import VALID_SIZES, downsample, mobile_size, normalize_weights
from . import texel
from .report import finding

TERRAIN_CLASS: Final = "terrain"
LAYER_PREFIX: Final = "Layer_"
TEXTURE_SUFFIXES: Final[tuple[str, ...]] = ("BC", "N", "ORM")
TEXEL_DENSITY_MIN: Final[dict[str, float]] = {
    "desktop": texel.DESKTOP_MIN,
    "mobile": texel.MOBILE_MIN,
}
SPACING_TOLERANCE: Final = 1e-3
CENTRE_TOLERANCE: Final = 1e-3
CLUSTER_TOLERANCE: Final = 1e-3
LAYER_TOLERANCE: Final = 1e-6
LOCATION_TOLERANCE: Final = 1e-5
ANGLE_TOLERANCE: Final = 1e-5


@dataclass(frozen=True)
class _Mesh:
    """Per-vertex data of the evaluated grid, in mesh order."""

    xs: array
    ys: array
    zs: array
    layers: dict[str, array]
    uv_area: float
    world_area: float


@dataclass(frozen=True)
class TerrainGrid:
    """The validated grid in heightfield order, with the Mobile layer set and texel inputs.

    ``weights`` holds each layer's raw Layer_<L> values in the same grid order as ``heights``.
    """

    n: int
    spacing_m: float
    heights: array
    weights: Mapping[str, array]
    layers: tuple[str, ...]
    kept: tuple[str, ...]
    layer_px: Mapping[str, int]
    texel_factor: float


def terrain_findings(
    collection: bpy.types.Collection,
    budgets: Mapping[str, Mapping[str, int]],
    *,
    authored: bool = False,
) -> list[dict[str, str]]:
    """Return every terrain rule the collection breaks, each with its remediation.

    ``budgets`` is ``{"desktop": {...}, "mobile": {...}}`` as validate_asset builds it. With
    ``authored=True`` the texture-set part of terrain.layer_texture_missing is skipped, because
    the bake has not produced the T_<Name>_<Layer>_{BC,N,ORM} images yet.
    """
    return _analyze(collection, budgets, authored=authored)[0]


def terrain_check(
    collection: bpy.types.Collection,
    budgets: Mapping[str, Mapping[str, int]],
    *,
    authored: bool = False,
) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    """Return the findings and, when there are none, the terrain report object.

    The object is ``{"desktop": {...}, "mobile": {...}}``. Each variant holds ``heightmap_px``,
    ``spacing_m``, ``height_min_m``, ``height_max_m``, ``layers`` (names), and ``texel_density``
    (layer name to px/m). The Mobile values come from the planned downsample: the stride-sampled
    heightmap, its own height range, and the layers that survive the Mobile limit. A layer's
    density appears only once its texture images exist, so an authored asset has none yet.
    """
    findings, grid = _analyze(collection, budgets, authored=authored)
    if findings or grid is None:
        return findings, None
    return findings, _terrain_object(grid, budgets)


def terrain_grid(
    collection: bpy.types.Collection,
    budgets: Mapping[str, Mapping[str, int]],
) -> tuple[list[dict[str, str]], TerrainGrid | None]:
    """Return the findings and the validated grid, or None when the grid is not valid.

    The variants and export steps read the heights, layer weights, and texture sizes from it. The
    check is the post-bake one, so the texture-set rule applies.
    """
    return _analyze(collection, budgets, authored=False)


def mesh_areas(mesh: bpy.types.Mesh) -> tuple[float, float]:
    """Return (UV area, world area) of the mesh, for the texel density estimate."""
    layer = mesh.uv_layers[0].data if mesh.uv_layers else None
    uv_total = 0.0
    if layer is not None:
        for poly in mesh.polygons:
            points = [
                layer[index].uv
                for index in range(poly.loop_start, poly.loop_start + poly.loop_total)
            ]
            for index in range(1, len(points) - 1):
                a, b, c = points[0], points[index], points[index + 1]
                uv_total += abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)) / 2
    world_total = sum(poly.area for poly in mesh.polygons)
    return uv_total, world_total


def _analyze(
    collection: bpy.types.Collection,
    budgets: Mapping[str, Mapping[str, int]],
    *,
    authored: bool,
) -> tuple[list[dict[str, str]], TerrainGrid | None]:
    desktop = budgets["desktop"]
    mobile = budgets["mobile"]
    name = collection.name
    root_name = f"SM_{name}"
    objects = sorted(collection.all_objects, key=lambda obj: obj.name)
    findings: list[dict[str, str]] = []

    for obj in objects:
        if obj.name == root_name and obj.type == "MESH":
            continue
        findings.append(
            finding(
                "terrain.structure",
                obj.name,
                f"{obj.name} is not the terrain mesh; the {name} terrain collection holds only "
                f"{root_name}.",
            )
        )
    root = next((obj for obj in objects if obj.name == root_name and obj.type == "MESH"), None)
    if root is None:
        if not any(obj.name == root_name for obj in objects):
            findings.append(
                finding(
                    "terrain.structure",
                    root_name,
                    f"The {name} terrain collection has no mesh named {root_name}.",
                )
            )
        return findings, None
    findings += _root_basis_findings(root)

    mesh = _read_mesh(root, need_areas=any(_images_of(m) for m in _materials_of(root)))
    count = len(mesh.xs)
    n = math.isqrt(count)
    if n * n != count or n not in VALID_SIZES:
        findings.append(
            finding(
                "terrain.resolution_invalid",
                root.name,
                f"{root.name} has {count} vertices; a terrain grid needs n x n vertices with n "
                f"one of {_sizes_text()}.",
            )
        )
        return findings, None

    xc = _centres(mesh.xs)
    yc = _centres(mesh.ys)
    if len(xc) != n or len(yc) != n:
        findings.append(
            finding(
                "terrain.resolution_invalid",
                root.name,
                f"{root.name} has {len(xc)} distinct X and {len(yc)} distinct Y positions; a "
                f"{n} x {n} grid needs {n} of each, with one vertex per grid point.",
            )
        )
        return findings, None
    slots = _grid_slots(mesh.xs, mesh.ys, xc, yc, n)
    if slots is None:
        findings.append(
            finding(
                "terrain.resolution_invalid",
                root.name,
                f"{root.name} puts two vertices on one grid point; a {n} x {n} grid needs one "
                "vertex per grid point.",
            )
        )
        return findings, None

    findings += _spacing_and_centre_findings(root.name, xc, yc)

    names = tuple(sorted(mesh.layers))
    if not names:
        findings.append(
            finding(
                "terrain.layer_missing",
                root.name,
                f"{root.name} has no Layer_<LayerName> float point attribute; add one weight "
                "attribute per paint layer.",
            )
        )
    for layer in names:
        low, high = min(mesh.layers[layer]), max(mesh.layers[layer])
        if low < -LAYER_TOLERANCE or high > 1.0 + LAYER_TOLERANCE:
            findings.append(
                finding(
                    "terrain.layer_range",
                    f"{LAYER_PREFIX}{layer}",
                    f"{LAYER_PREFIX}{layer} ranges from {low:.4f} to {high:.4f}; layer weights "
                    "must stay within 0 to 1.",
                )
            )

    if n > desktop["heightmap_px"]:
        findings.append(
            finding(
                "terrain.over_budget",
                root.name,
                f"{root.name} is {n} samples a side; the terrain Desktop heightmap_px budget is "
                f"{desktop['heightmap_px']}.",
            )
        )
    if len(names) > desktop["layers"]:
        findings.append(
            finding(
                "terrain.over_budget",
                root.name,
                f"{root.name} has {len(names)} layers; the terrain Desktop layers budget is "
                f"{desktop['layers']}.",
            )
        )

    layer_images = _layer_textures(root, name, names, authored, desktop, findings)

    layer_px = {
        layer: max(max(image.size) for image in images)
        for layer, images in layer_images.items()
        if images
    }
    factor = 0.0
    if layer_px and mesh.uv_area > 0 and mesh.world_area > 0:
        factor = math.sqrt(mesh.uv_area / mesh.world_area)
    kept = _kept_layers(mesh.layers, names, mobile["layers"])
    findings += _texel_findings(root.name, layer_px, kept, factor, mobile["max_texture_px"])

    grid = TerrainGrid(
        n=n,
        spacing_m=(xc[-1] - xc[0]) / (n - 1),
        heights=_scatter(mesh.zs, slots, count),
        weights={layer: _scatter(mesh.layers[layer], slots, count) for layer in names},
        layers=names,
        kept=kept,
        layer_px=layer_px,
        texel_factor=factor,
    )
    return findings, grid


def _root_basis_findings(root: bpy.types.Object) -> list[dict[str, str]]:
    location, rotation, scale = root.matrix_basis.decompose()
    problems: list[str] = []
    if any(abs(value) > LOCATION_TOLERANCE for value in location):
        problems.append(f"location {_format(location)}")
    if rotation.angle > ANGLE_TOLERANCE:
        problems.append(f"rotation {math.degrees(rotation.angle):.3f} deg")
    if any(abs(value - 1.0) > LOCATION_TOLERANCE for value in scale):
        problems.append(f"scale {_format(scale)}")
    if not problems:
        return []
    return [
        finding(
            "transform.root_applied",
            root.name,
            f"{root.name} is not in identity: {', '.join(problems)}.",
        )
    ]


def _spacing_and_centre_findings(
    target: str, xc: Sequence[float], yc: Sequence[float]
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for axis, centres in (("X", xc), ("Y", yc)):
        steps = [later - earlier for earlier, later in zip(centres, centres[1:], strict=False)]
        if max(abs(step - 1.0) for step in steps) > SPACING_TOLERANCE:
            findings.append(
                finding(
                    "terrain.spacing",
                    target,
                    f"{target} vertices are {min(steps):.4f} to {max(steps):.4f} m apart along "
                    f"{axis}; a terrain needs exactly 1 m.",
                )
            )
        centre = (centres[0] + centres[-1]) / 2
        if abs(centre) > CENTRE_TOLERANCE:
            findings.append(
                finding(
                    "terrain.not_centered",
                    target,
                    f"{target} is centred {centre:.4f} m off the origin along {axis}; its "
                    f"{axis} extent must be symmetric about 0.",
                )
            )
    return findings


def _layer_textures(
    root: bpy.types.Object,
    name: str,
    names: Sequence[str],
    authored: bool,
    desktop: Mapping[str, int],
    findings: list[dict[str, str]],
) -> dict[str, list[bpy.types.Image]]:
    """Check each layer's material (and texture set after the bake); return the images per layer."""
    materials = {material.name: material for material in _materials_of(root)}
    layer_images: dict[str, list[bpy.types.Image]] = {}
    for layer in names:
        target = f"{LAYER_PREFIX}{layer}"
        material_name = f"M_{name}_{layer}"
        material = materials.get(material_name)
        if material is None:
            findings.append(
                finding(
                    "terrain.layer_texture_missing",
                    target,
                    f"{target} has no material {material_name} on {root.name}; map each paint "
                    "layer to its own tiling material.",
                )
            )
            continue
        images = _images_of(material)
        if not authored:
            present = {image.name for image in images}
            expected = [f"T_{name}_{layer}_{suffix}" for suffix in TEXTURE_SUFFIXES]
            missing = [image for image in expected if image not in present]
            if missing:
                findings.append(
                    finding(
                        "terrain.layer_texture_missing",
                        material_name,
                        f"{material_name} lacks texture image(s) {', '.join(missing)}; bake the "
                        "layer so its BC, N, and ORM images exist.",
                    )
                )
        for image in images:
            if max(image.size) > desktop["max_texture_px"]:
                findings.append(
                    finding(
                        "terrain.over_budget",
                        image.name,
                        f"{image.name} is {max(image.size)} px; the terrain Desktop maximum is "
                        f"{desktop['max_texture_px']} px.",
                    )
                )
        layer_images[layer] = images
    return layer_images


def _texel_findings(
    target: str,
    layer_px: Mapping[str, int],
    kept: Sequence[str],
    factor: float,
    mobile_max_px: int,
) -> list[dict[str, str]]:
    """texel.density for each layer on Desktop, and for each kept layer at its Mobile size."""
    findings: list[dict[str, str]] = []
    for layer, px in layer_px.items():
        findings += _density_finding(target, layer, px * factor, "desktop")
    for layer in kept:
        if layer in layer_px:
            size = min(layer_px[layer], mobile_max_px)
            findings += _density_finding(target, layer, size * factor, "mobile")
    return findings


def _density_finding(target: str, layer: str, density: float, variant: str) -> list[dict[str, str]]:
    minimum = TEXEL_DENSITY_MIN[variant]
    if density >= minimum:
        return []
    return [
        finding(
            "texel.density",
            f"{LAYER_PREFIX}{layer}",
            f"{target} layer {layer} reaches {density:.0f} px/m on {variant}; terrain layers need "
            f"at least {minimum:.0f} px/m on {variant}.",
        )
    ]


def _terrain_object(grid: TerrainGrid, budgets: Mapping[str, Mapping[str, int]]) -> dict[str, Any]:
    mobile = budgets["mobile"]
    size, stride = mobile_size(grid.n, mobile["heightmap_px"])
    return {
        "desktop": _variant_block(
            grid.n,
            grid.spacing_m,
            grid.heights,
            grid.layers,
            grid.layer_px,
            grid.texel_factor,
            cap=None,
        ),
        "mobile": _variant_block(
            size,
            grid.spacing_m * stride,
            downsample(grid.heights, grid.n, stride),
            grid.kept,
            grid.layer_px,
            grid.texel_factor,
            cap=mobile["max_texture_px"],
        ),
    }


def _variant_block(
    n: int,
    spacing_m: float,
    heights: Sequence[float],
    layers: Sequence[str],
    layer_px: Mapping[str, int],
    factor: float,
    *,
    cap: int | None,
) -> dict[str, Any]:
    density: dict[str, float] = {}
    for layer in layers:
        if layer in layer_px:
            px = layer_px[layer] if cap is None else min(layer_px[layer], cap)
            density[layer] = round(px * factor, 3)
    return {
        "heightmap_px": n,
        "spacing_m": round(spacing_m, 6),
        "height_min_m": round(min(heights), 6),
        "height_max_m": round(max(heights), 6),
        "layers": list(layers),
        "texel_density": density,
    }


def _read_mesh(root: bpy.types.Object, *, need_areas: bool) -> _Mesh:
    copy = _evaluated_copy(root)
    try:
        count = len(copy.vertices)
        coords = array("f", bytes(12 * count))
        copy.vertices.foreach_get("co", coords)
        layers: dict[str, array] = {}
        for attribute in copy.attributes:
            if not attribute.name.startswith(LAYER_PREFIX):
                continue
            layer = attribute.name[len(LAYER_PREFIX) :]
            if not layer or attribute.domain != "POINT" or attribute.data_type != "FLOAT":
                continue
            values = array("f", bytes(4 * count))
            attribute.data.foreach_get("value", values)
            layers[layer] = values
        uv_area, world_area = mesh_areas(copy) if need_areas else (0.0, 0.0)
    finally:
        bpy.data.meshes.remove(copy)
    return _Mesh(
        xs=coords[0::3],
        ys=coords[1::3],
        zs=coords[2::3],
        layers=dict(sorted(layers.items())),
        uv_area=uv_area,
        world_area=world_area,
    )


def _centres(values: array) -> list[float]:
    """Cluster sorted coordinates within CLUSTER_TOLERANCE and return each cluster's mean."""
    centres: list[float] = []
    total = 0.0
    members = 0
    previous = 0.0
    for value in sorted(values):
        if members and value - previous > CLUSTER_TOLERANCE:
            centres.append(total / members)
            total = 0.0
            members = 0
        total += value
        members += 1
        previous = value
    if members:
        centres.append(total / members)
    return centres


def _nearest(centres: Sequence[float], value: float) -> int:
    upper = bisect_left(centres, value)
    if upper == 0:
        return 0
    if upper == len(centres):
        return len(centres) - 1
    return upper if centres[upper] - value < value - centres[upper - 1] else upper - 1


def _grid_slots(
    xs: array, ys: array, xc: Sequence[float], yc: Sequence[float], n: int
) -> array | None:
    """Map each vertex to its row-major grid slot. None when two vertices share a grid point."""
    count = len(xs)
    slots = array("q", bytes(8 * count))
    seen = bytearray(count)
    for index in range(count):
        col = _nearest(xc, xs[index])
        row = n - 1 - _nearest(yc, ys[index])
        slot = row * n + col
        if seen[slot]:
            return None
        seen[slot] = 1
        slots[index] = slot
    return slots


def _scatter(values: array, slots: array, count: int) -> array:
    out = array("d", bytes(8 * count))
    for value, slot in zip(values, slots, strict=True):
        out[slot] = value
    return out


def _kept_layers(layers: Mapping[str, array], names: Sequence[str], limit: int) -> tuple[str, ...]:
    """The layers the Mobile variant keeps: the highest normalized totals, in layer order."""
    if len(names) <= limit:
        return tuple(names)
    normalized = normalize_weights([layers[name] for name in names])
    totals = [sum(layer) for layer in normalized]
    ranked = sorted(range(len(names)), key=lambda slot: (-totals[slot], slot))
    return tuple(names[slot] for slot in sorted(ranked[:limit]))


def _sizes_text() -> str:
    return ", ".join(str(size) for size in VALID_SIZES)


def _evaluated_copy(obj: bpy.types.Object) -> bpy.types.Mesh:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), depsgraph=depsgraph)


def _materials_of(obj: bpy.types.Object) -> list[bpy.types.Material]:
    return [slot.material for slot in obj.material_slots if slot.material is not None]


def _images_of(material: bpy.types.Material) -> list[bpy.types.Image]:
    if material.node_tree is None:
        return []
    return [
        node.image
        for node in material.node_tree.nodes
        if node.type == "TEX_IMAGE" and node.image is not None
    ]


def _format(values: Any) -> str:
    return "(" + ", ".join(f"{float(value):.4f}" for value in values) + ")"
