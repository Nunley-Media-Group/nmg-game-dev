"""Terrain variants: the Desktop grid and its Mobile downsample (#154, FR4, FR5, AC3).

The Desktop variant is the validated grid as the scene holds it. The Mobile variant takes every
stride-th sample to the largest valid size within the Mobile budget, keeps the layers the Mobile
limit allows (the lowest-total layer is dropped and its weight is redistributed), and halves the
layer textures to the Mobile maximum. Nothing here changes the scene.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import bpy

from ..contract_core.terrain import TerrainGrid, terrain_grid
from ..variants_core.errors import VariantError
from .heightfield import downsample, mobile_size, normalize_weights, reduce_layers, sample_points

DESKTOP: str = "Desktop"
MOBILE: str = "Mobile"
SAMPLE_DECIMALS = 6


@dataclass(frozen=True)
class TerrainVariant:
    """One exported terrain variant: heights in metres and layer weights in grid order.

    ``weights`` is layer-major and normalized, so every grid sample sums to 1 across the layers.
    ``texture_px`` maps each kept layer to its texture size (the longest edge after the cap).
    """

    heightmap_px: int
    spacing_m: float
    heights: list[float]
    layers: tuple[str, ...]
    weights: list[list[float]]
    texture_px: Mapping[str, int]
    uv_tile_m: float

    @property
    def height_min_m(self) -> float:
        return min(self.heights)

    @property
    def height_max_m(self) -> float:
        return max(self.heights)

    @property
    def max_texture_px(self) -> int:
        return max(self.texture_px.values(), default=0)

    def metrics(self) -> dict[str, Any]:
        """The per-variant fields that nmg-variants.json and the Unreal import read."""
        points = sample_points(self.heights, self.heightmap_px, self.spacing_m)
        return {
            "heightmap_px": self.heightmap_px,
            "spacing_m": round(self.spacing_m, SAMPLE_DECIMALS),
            "height_min_m": round(self.height_min_m, SAMPLE_DECIMALS),
            "height_max_m": round(self.height_max_m, SAMPLE_DECIMALS),
            "uv_tile_m": round(self.uv_tile_m, SAMPLE_DECIMALS),
            "layers": list(self.layers),
            "max_texture_px": self.max_texture_px,
            "samples": [[round(value, SAMPLE_DECIMALS) for value in point] for point in points],
        }


def terrain_variants(
    collection_name: str, budgets: Mapping[str, Mapping[str, int]]
) -> dict[str, TerrainVariant]:
    """Return the Desktop and Mobile variants of a validated terrain collection.

    ``budgets`` is ``{"desktop": {...}, "mobile": {...}}``. Raises VariantError when the grid is
    not valid, so no variant is built from an out-of-contract terrain.
    """
    findings, grid = terrain_grid(bpy.data.collections[collection_name], budgets)
    if findings or grid is None:
        raise VariantError(
            "variants.terrain_invalid",
            f"{collection_name} fails the terrain contract with {len(findings)} finding(s); "
            "no Desktop or Mobile variant was built.",
            "Run the validate step, fix every terrain finding, then rerun the variants step.",
        )
    return {DESKTOP: _desktop(grid), MOBILE: _mobile(grid, budgets["mobile"])}


def _desktop(grid: TerrainGrid) -> TerrainVariant:
    normalized = normalize_weights([grid.weights[layer] for layer in grid.layers])
    return TerrainVariant(
        heightmap_px=grid.n,
        spacing_m=grid.spacing_m,
        heights=list(grid.heights),
        layers=grid.layers,
        weights=normalized,
        texture_px=dict(grid.layer_px),
        uv_tile_m=_uv_tile(grid),
    )


def _mobile(grid: TerrainGrid, budget: Mapping[str, int]) -> TerrainVariant:
    size, stride = mobile_size(grid.n, budget["heightmap_px"])
    normalized = normalize_weights([grid.weights[layer] for layer in grid.layers])
    kept, reduced = reduce_layers(normalized, budget["layers"])
    layers = tuple(grid.layers[slot] for slot in kept)
    return TerrainVariant(
        heightmap_px=size,
        spacing_m=grid.spacing_m * stride,
        heights=downsample(list(grid.heights), grid.n, stride),
        layers=layers,
        weights=[downsample(layer, grid.n, stride) for layer in reduced],
        texture_px={
            layer: min(grid.layer_px[layer], budget["max_texture_px"])
            for layer in layers
            if layer in grid.layer_px
        },
        uv_tile_m=_uv_tile(grid),
    )


def _uv_tile(grid: TerrainGrid) -> float:
    """Metres covered by one UV unit, so one texture repeat spans uv_tile_m metres."""
    return 1.0 / grid.texel_factor if grid.texel_factor > 0 else 1.0
