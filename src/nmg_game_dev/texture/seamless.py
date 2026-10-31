"""Seamless post-process for generated albedo (#7 FR15, AC18).

Neither model tiles natively. ``make_seamless`` blends each axis with a half-rolled copy under a
``sin²`` window. The wrap seam then joins two pixels that sat next to each other in the original
interior, so it no longer shows as a hard edge.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

Image = NDArray[np.generic]


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


def is_seamless(img: Image, ratio: float = 1.5) -> bool:
    """True when both wrap seams differ by at most ``ratio`` times the interior step (AC18)."""
    return all(seam_mad(img, axis) <= ratio * interior_mad(img, axis) for axis in (0, 1))
