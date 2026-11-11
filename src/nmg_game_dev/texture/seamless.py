"""Seamless post-process for generated albedo (#7 FR15, AC18).

Neither model tiles natively. ``make_seamless`` blends each axis with a half-rolled copy under a
``sin²`` window. The wrap seam then joins two pixels that sat next to each other in the original
interior, so it no longer shows as a hard edge.

``is_seamless`` uses the same definition as the bake seam check (``bake_core/seam_metric.py``,
#147): integer images are normalised by their dtype maximum, and each axis passes when its wrap is
at most ``max(ratio × interior, SEAM_FLOOR)``. A parity test keeps the two implementations in step.
"""

from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

Image = NDArray[np.generic]

SEAM_RATIO: Final = 1.5
SEAM_FLOOR: Final = 2 / 255


def make_seamless(img: Image) -> Image:
    """Return ``img`` (H×W or H×W×C) cross-faded so both wrap seams join smoothly. Shape is kept."""
    work = img.astype(np.float64)
    for axis in (0, 1):
        n = work.shape[axis]
        shifted = np.roll(work, n // 2, axis=axis)
        i = np.arange(n, dtype=np.float64)
        weight = np.sin(np.pi * (i + 0.5) / n) ** 2
        shape = [1] * work.ndim
        shape[axis] = n
        w = weight.reshape(shape)
        work = w * work + (1.0 - w) * shifted
    if np.issubdtype(img.dtype, np.integer):
        # Integer input is 8-bit albedo (the worker writes 8-bit PNGs).
        return np.clip(np.rint(work), 0, 255).astype(img.dtype)
    return work.astype(img.dtype)


def seam_mad(img: Image, axis: int) -> float:
    """Mean absolute difference between the last and first pixels along ``axis`` (the wrap seam)."""
    first = np.take(img, [0], axis=axis).astype(np.float64)
    last = np.take(img, [-1], axis=axis).astype(np.float64)
    return float(np.abs(last - first).mean())


def interior_mad(img: Image, axis: int) -> float:
    """Mean absolute difference between adjacent pixels along ``axis``, excluding the wrap seam."""
    return float(np.abs(np.diff(img.astype(np.float64), axis=axis)).mean())


def _normalize(img: Image) -> NDArray[np.float64]:
    """Integer images divided by their dtype maximum; float images as float64 (as the bake does)."""
    work: NDArray[np.float64] = img.astype(np.float64)
    if np.issubdtype(img.dtype, np.integer):
        # The name round-trip gives mypy a concrete integer dtype; the maximum is unchanged.
        work = work / float(np.iinfo(np.dtype(img.dtype.name)).max)
    return work


def is_seamless(img: Image, ratio: float = SEAM_RATIO) -> bool:
    """True when both wrap seams are within ``max(ratio × interior, SEAM_FLOOR)`` (AC18, #147)."""
    work = _normalize(img)
    return all(
        seam_mad(work, axis) <= max(ratio * interior_mad(work, axis), SEAM_FLOOR) for axis in (0, 1)
    )
