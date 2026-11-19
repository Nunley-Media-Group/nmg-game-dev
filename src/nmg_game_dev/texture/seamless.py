"""Seamless post-process for generated albedo (#7 FR15, AC18).

Neither model tiles natively. ``make_seamless`` blends each axis with a half-rolled copy under a
``sin²`` window. The wrap seam then joins two pixels that sat next to each other in the original
interior, so it no longer shows as a hard edge.

``is_seamless`` uses the same definition as the bake seam check (``bake_core/seam_metric.py``,
#147): integer images are normalised by their dtype maximum, and each axis passes when its wrap is
at most ``max(ratio × interior, SEAM_FLOOR)``. A parity test keeps the two implementations in step.

``make_seamless`` alone does not guarantee a pass: at the wrap it still joins two original pixels,
so the wrap/interior ratio can land just over the rule (#238). ``repair_seam`` is the guaranteed
repair. ``edge_band`` cross-fades the lines within ``EDGE_BAND_WIDTH`` pixels of each edge with
their mirror lines across the wrap, weight 0.5 at the wrap, so the two wrap lines become identical.
``fix_seam`` picks a repair by severity: a passing image is returned unchanged, a narrow failure
(every axis within ``GROSS_SEAM_RATIO`` of its allowance) gets only the edge band, and a gross
failure gets ``make_seamless`` and then the edge band. Its wrap never ends up larger than the
input's on either axis.
"""

from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

Image = NDArray[np.generic]

SEAM_RATIO: Final = 1.5
SEAM_FLOOR: Final = 2 / 255
EDGE_BAND_WIDTH: Final = 8
GROSS_SEAM_RATIO: Final = 3.0


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


def seam_wraps(img: Image) -> tuple[float, float]:
    """The normalised wrap seam per axis (0, then 1), as ``is_seamless`` measures it."""
    work = _normalize(img)
    return seam_mad(work, 0), seam_mad(work, 1)


def seam_ratios(img: Image) -> tuple[float, float]:
    """Wrap ÷ ``max(SEAM_RATIO × interior, SEAM_FLOOR)`` per axis; an axis passes at ≤ 1."""
    work = _normalize(img)
    ratios = [
        seam_mad(work, axis) / max(SEAM_RATIO * interior_mad(work, axis), SEAM_FLOOR)
        for axis in (0, 1)
    ]
    return ratios[0], ratios[1]


def failing_axes(img: Image, reference: Image | None = None) -> tuple[int, ...]:
    """Axes that fail ``is_seamless``, or whose wrap exceeds ``reference``'s on that axis."""
    work = _normalize(img)
    limits = seam_wraps(reference) if reference is not None else (np.inf, np.inf)
    failing = []
    for axis in (0, 1):
        wrap = seam_mad(work, axis)
        allowance = max(SEAM_RATIO * interior_mad(work, axis), SEAM_FLOOR)
        if wrap > allowance or wrap > limits[axis]:
            failing.append(axis)
    return tuple(failing)


def edge_band(img: Image, axis: int, width: int = EDGE_BAND_WIDTH) -> NDArray[np.float64]:
    """Cross-fade the lines within ``width`` pixels of both edges along ``axis`` with their mirror
    lines across the wrap, as float64. The weight is 0.5 at the wrap, so the first and last lines
    become identical, and falls linearly toward 0 inward. Lines are read from an unmodified copy."""
    src = img.astype(np.float64)
    out = src.copy()
    n = src.shape[axis]
    band = max(1, min(width, n // 2))
    for k in range(band):
        t = 0.5 * (1.0 - k / band)
        near = np.take(src, k, axis=axis)
        far = np.take(src, n - 1 - k, axis=axis)
        index: list[int | slice] = [slice(None)] * src.ndim
        index[axis] = k
        out[tuple(index)] = (1.0 - t) * near + t * far
        index[axis] = n - 1 - k
        out[tuple(index)] = (1.0 - t) * far + t * near
    return out


def _as_dtype(work: NDArray[np.float64], dtype: np.dtype[np.generic]) -> Image:
    """``work`` in ``dtype``: integer results are rounded and clipped to the dtype's range."""
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(np.dtype(dtype.name))
        return np.clip(np.rint(work), info.min, info.max).astype(dtype)
    return work.astype(dtype)


def repair_seam(img: Image, reference: Image | None = None) -> Image:
    """Edge-band every axis that fails ``is_seamless`` (or, with ``reference``, whose wrap exceeds
    the reference's), recheck, and repeat once for any axis the first pass pushed over. The result
    passes ``is_seamless`` and keeps ``img``'s shape and dtype."""
    work = img.astype(np.float64)
    result: Image = img
    for _ in range(2):
        axes = failing_axes(result, reference)
        if not axes:
            break
        for axis in axes:
            work = edge_band(work, axis)
        result = _as_dtype(work, img.dtype)
    return result


def fix_seam(img: Image) -> Image:
    """Return ``img`` unchanged when it passes; edge-band a narrow failure (every axis within
    ``GROSS_SEAM_RATIO`` of its allowance); otherwise ``make_seamless`` and then edge-band. The
    result passes, and on neither axis is its wrap larger than ``img``'s."""
    if is_seamless(img):
        return img
    if max(seam_ratios(img)) <= GROSS_SEAM_RATIO:
        return repair_seam(img, reference=img)
    return repair_seam(make_seamless(img), reference=img)
