"""Bake passes for a reduce: each source part's look onto its reduced copy, and the coverage check.

Every channel is baked into one shared float image per channel, one part per pass, so each part
writes only its own UV island. Coverage bakes the copy's islands and the rays from the source
onto two masks, and the unbaked share of each part is the islands no ray reached (#139 AC8).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import bpy
import numpy as np

from ..bake_core import bake, pack
from .plan import DEFAULTS, unbaked_share

Pair = tuple[str, bpy.types.Object, bpy.types.Object]
Settings = dict[str, dict[str, float]]

# The per-channel sample count keys in DEFAULTS["samples"] (BC, R, M, N, AO).
_SAMPLE_KEY: Final[dict[str, str]] = {"BC": "BC", "ROUGH": "R", "METAL": "M", "N": "N", "AO": "AO"}
_COVERAGE_SAMPLES: Final = 1
_HIT_THRESHOLD: Final = 0.5


def bake_channels(
    pairs: Sequence[Pair], size: int, settings: Settings
) -> dict[str, bpy.types.Image]:
    """Bake BC, ROUGH, METAL, N, and AO for every pair into one float image per channel."""
    images = {
        channel: bake.new_channel_image(f"__nmg_reduce_{channel}", size)
        for channel in bake.CHANNELS
    }
    for channel in bake.CHANNELS:
        bake.configure(DEFAULTS["samples"][_SAMPLE_KEY[channel]])
        for index, (name, source, copy) in enumerate(pairs):
            used = settings[name]
            bake.bake_transfer(
                source,
                copy,
                channel,
                images[channel],
                size,
                used["cage_extrusion"],
                used["max_ray_distance"],
                clear=index == 0,
            )
    return images


def measure_coverage(pairs: Sequence[Pair], size: int, settings: Settings) -> dict[str, float]:
    """The unbaked share of each part: its island texels that no ray from the copy hit on source."""
    island = bake.new_channel_image("__nmg_reduce_island", size)
    hit = bake.new_channel_image("__nmg_reduce_hit", size)
    shares: dict[str, float] = {}
    try:
        bake.configure(_COVERAGE_SAMPLES)
        for name, source, copy in pairs:
            used = settings[name]
            bake.bake_island(copy, island, clear=True)
            bake.bake_coverage(
                source,
                copy,
                hit,
                used["cage_extrusion"],
                used["max_ray_distance"],
                clear=True,
            )
            island_texels = pack.read_rgba(island)[..., 0] > _HIT_THRESHOLD
            hit_texels = pack.read_rgba(hit)[..., 0] > _HIT_THRESHOLD
            missed = int(np.count_nonzero(island_texels & ~hit_texels))
            shares[name] = unbaked_share(int(np.count_nonzero(island_texels)), missed)
    finally:
        bpy.data.images.remove(island)
        bpy.data.images.remove(hit)
    return shares
