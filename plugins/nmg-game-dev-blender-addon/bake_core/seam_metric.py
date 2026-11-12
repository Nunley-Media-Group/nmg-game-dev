"""The bake seam measure (#147): a tiling texture's wrap judged against its own interior.

For an image normalised to 0 to 1, an axis passes when the mean absolute difference between its
last and first pixel (the wrap) is at most max(SEAM_RATIO x interior, SEAM_FLOOR). The interior is
the mean absolute difference between adjacent pixels on that axis. The floor is the only absolute
term, so a flat or near-flat image is judged without dividing by a zero interior.

Numpy-only and free of bpy, so the add-on, the texture-gen package, and plain pytest can load it by
file path. nmg_game_dev.texture.seamless.is_seamless uses the same definition; a parity test keeps
the two in step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

SEAM_RATIO: Final = 1.5
SEAM_FLOOR: Final = 2 / 255


@dataclass(frozen=True)
class AxisSeam:
    """One axis measurement: the wrap, the interior step, the allowance, and the verdict."""

    axis: int
    wrap: float
    interior: float
    allowed: float
    passes: bool


def normalize(img: NDArray[np.generic]) -> NDArray[np.float64]:
    """Integer images divided by their dtype maximum; float images as float64."""
    work: NDArray[np.float64] = img.astype(np.float64)
    if np.issubdtype(img.dtype, np.integer):
        work = work / float(np.iinfo(np.dtype(img.dtype.name)).max)
    return work


def _axis(work: NDArray[np.float64], axis: int) -> AxisSeam:
    wrap = float(np.abs(np.take(work, [-1], axis=axis) - np.take(work, [0], axis=axis)).mean())
    interior = float(np.abs(np.diff(work, axis=axis)).mean())
    allowed = max(SEAM_RATIO * interior, SEAM_FLOOR)
    return AxisSeam(axis, wrap, interior, allowed, wrap <= allowed)


def measure(img: NDArray[np.generic]) -> tuple[AxisSeam, AxisSeam]:
    """Measurements for axis 0 (rows, V) and axis 1 (columns, U) of an H x W or H x W x C image."""
    work = normalize(img)
    return _axis(work, 0), _axis(work, 1)


def passes(img: NDArray[np.generic]) -> bool:
    """True when both axes pass."""
    return all(seam.passes for seam in measure(img))


def failure_detail(kind: str, seams: tuple[AxisSeam, AxisSeam]) -> str:
    """Name the channel and its worst axis: the largest wrap relative to that axis's allowance."""
    worst = max(seams, key=lambda seam: seam.wrap / seam.allowed)
    return f"{kind} wrap {worst.wrap:.3f} vs interior {worst.interior:.3f}"
