"""Landmark estimation by horizontal slicing (pure Python, no bpy).

``propose`` takes world-space vertex positions and returns the 19 ``LANDMARK_KEYS`` that
``rig_humanoid`` checks. It cuts the mesh into 200 horizontal slices, splits each slice's x
values into intervals wherever the gap exceeds 0.012 of the height, and reads the crotch, the
armpits, and the arm and leg chains from those intervals. Each side is measured on its own.
An asymmetric left/right pair lowers confidence to ``low``; landmarks are never mirror-averaged.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from .outcome import STATUS_FALLBACK, RigError
from .skeleton import LANDMARK_KEYS, Vec3, vec_lerp

SLICE_COUNT = 200
GAP_FRACTION = 0.012
CROTCH_BAND = (0.15, 0.70)
CROTCH_HOLD = 6
ARMPIT_CEILING = 0.92
ARM_CHAIN_FRACTION = 0.12
ARM_FIT_TRIM = 0.2
SHOULDER_RISE = 0.035
NECK_CEILING = 0.95
HEAD_TOP_FRACTION = 0.995
PELVIS_RISE = 0.075
HIP_RISE = 0.03
ANKLE_RISE = 0.075
TOE_BAND = 0.05
TOE_LIFT = 0.012
TOE_DEPTH = 0.025
KNEE_LINE_WEIGHT = 0.6
ELBOW_FRACTION = 0.47
WRIST_FRACTION = 0.80
HAND_TIP_FRACTION = 0.985
MIRROR_TOLERANCE = 0.05

_SIDES: tuple[tuple[str, float], ...] = (("l", 1.0), ("r", -1.0))
_PAIRED_BASES = ("shoulder", "elbow", "wrist", "hand_tip", "hip", "knee", "ankle", "toe")
_CROTCH_MESSAGE = (
    "No crotch was found: the legs do not split below a torso that crosses the midline."
)
_CROTCH_REMEDIATION = (
    "Pose the character in an A-pose with the legs apart, then rerun, or supply the 19 "
    "landmarks by hand. See docs/rigging-and-animation.md."
)
_ARMS_MESSAGE = (
    "No A-pose arms were found: no armpit has an arm on each side that can be followed down "
    "to a hand. The arms may be in a T-pose or fused to the torso."
)
_ARMS_REMEDIATION = (
    "Pose the character in an A-pose with arms clear of the torso and legs apart, then rerun, "
    "or supply the 19 landmarks by hand. See docs/rigging-and-animation.md."
)

_T = TypeVar("_T")


@dataclass
class _Interval:
    """A run of one slice's vertices whose x values never gap wider than the threshold."""

    low: float
    high: float
    y_sum: float
    count: int

    @property
    def centre(self) -> float:
        return (self.low + self.high) / 2.0

    @property
    def width(self) -> float:
        return self.high - self.low

    @property
    def mean_y(self) -> float:
        return self.y_sum / self.count

    @property
    def spans_midline(self) -> bool:
        return self.low <= 0.0 <= self.high


Chain = list[tuple[int, _Interval]]


@dataclass(frozen=True)
class _Grid:
    """Maps heights to slice indices. Slice i starts at z_low + i * height / SLICE_COUNT."""

    z_low: float
    height: float

    def index(self, z: float) -> int:
        slot = math.floor((z - self.z_low) * SLICE_COUNT / self.height)
        return min(SLICE_COUNT - 1, max(0, slot))

    def z_of(self, index: int) -> float:
        return self.z_low + index * self.height / SLICE_COUNT


def propose(points: Sequence[Vec3]) -> dict[str, Any]:
    """Return {"landmarks": 19 keys of [x, y, z], "confidence": high or low, "warnings": [...]}.

    Raises RigError with rig.crotch_not_found or rig.arms_not_found when the points are not an
    A-pose humanoid. No landmarks are returned for those cases.
    """
    pts = [(float(x), float(y), float(z)) for x, y, z in points]
    if not pts:
        raise _crotch_missing()
    z_low = min(z for _, _, z in pts)
    height = max(z for _, _, z in pts) - z_low
    if height <= 0.0:
        raise _crotch_missing()

    grid = _Grid(z_low, height)
    rows = _slice_rows(pts, grid, GAP_FRACTION * height)
    crotch = _find_crotch(rows)
    legs = {side: _leg_landmarks(pts, rows, grid, height, crotch, sign) for side, sign in _SIDES}
    armpit, left_chain, right_chain = _find_armpit(rows, crotch)
    arms = {
        "l": _arm_landmarks(left_chain, grid, height),
        "r": _arm_landmarks(right_chain, grid, height),
    }

    shoulder_z = grid.z_of(armpit) + SHOULDER_RISE * height
    out: dict[str, Vec3] = {
        "neck": _neck(rows, grid, shoulder_z, height),
        "head_top": _head_top(rows, grid, height),
        "pelvis": _pelvis(rows, grid.z_of(crotch), crotch, height),
    }
    for side in ("l", "r"):
        for joint, point in {**arms[side], **legs[side]}.items():
            out[f"{joint}_{side}"] = point

    warnings = _mirror_warnings(out, height)
    return {
        "landmarks": {key: [float(c) for c in out[key]] for key in LANDMARK_KEYS},
        "confidence": "low" if warnings else "high",
        "warnings": warnings,
    }


def _slice_at(fraction: float) -> int:
    """Return the slice index at a fraction of the slice count."""
    return round(fraction * SLICE_COUNT)


def _crotch_missing() -> RigError:
    return RigError(STATUS_FALLBACK, "rig.crotch_not_found", _CROTCH_MESSAGE, _CROTCH_REMEDIATION)


def _arms_missing() -> RigError:
    return RigError(STATUS_FALLBACK, "rig.arms_not_found", _ARMS_MESSAGE, _ARMS_REMEDIATION)


def _intervals(samples: list[tuple[float, float]], gap: float) -> list[_Interval]:
    """Split one slice's (x, y) samples into runs that never gap wider than the threshold."""
    intervals: list[_Interval] = []
    for x, y in sorted(samples):
        if intervals and x - intervals[-1].high <= gap:
            current = intervals[-1]
            current.high = x
            current.y_sum += y
            current.count += 1
        else:
            intervals.append(_Interval(low=x, high=x, y_sum=y, count=1))
    return intervals


def _slice_rows(
    points: list[tuple[float, float, float]], grid: _Grid, gap: float
) -> list[list[_Interval]]:
    buckets: list[list[tuple[float, float]]] = [[] for _ in range(SLICE_COUNT)]
    for x, y, z in points:
        buckets[grid.index(z)].append((x, y))
    return [_intervals(bucket, gap) for bucket in buckets]


def _side_intervals(row: list[_Interval], sign: float) -> list[_Interval]:
    """Intervals wholly on one side of the midline: +1 for +X (left), -1 for -X (right)."""
    if sign > 0:
        return [iv for iv in row if iv.low > 0.0]
    return [iv for iv in row if iv.high < 0.0]


def _central(row: list[_Interval]) -> _Interval | None:
    for interval in row:
        if interval.spans_midline:
            return interval
    return None


def _leg(row: list[_Interval], sign: float) -> _Interval | None:
    """A side's leg in a slice below the arms is its side interval nearest the midline."""
    sides = _side_intervals(row, sign)
    return min(sides, key=lambda iv: abs(iv.centre)) if sides else None


def _nearest(
    rows: list[list[_Interval]], index: int, pick: Callable[[list[_Interval]], _T | None]
) -> tuple[int, _T] | None:
    """Return the first match for pick, searching outward from index, upward first."""
    for offset in range(len(rows)):
        candidates = (index,) if offset == 0 else (index + offset, index - offset)
        for candidate in candidates:
            if 0 <= candidate < len(rows):
                found = pick(rows[candidate])
                if found is not None:
                    return candidate, found
    return None


def _find_crotch(rows: list[list[_Interval]]) -> int:
    """The lowest slice in the band with the torso across the midline for the next six slices."""
    first, last = _slice_at(CROTCH_BAND[0]), _slice_at(CROTCH_BAND[1])
    for index in range(first, last + 1):
        if all(_central(rows[k]) is not None for k in range(index, index + CROTCH_HOLD)):
            return index
    raise _crotch_missing()


def _leg_landmarks(
    points: list[tuple[float, float, float]],
    rows: list[list[_Interval]],
    grid: _Grid,
    height: float,
    crotch: int,
    sign: float,
) -> dict[str, Vec3]:
    """Hip, knee, ankle, and toe for one side. A leg that cannot be followed means no crotch."""
    hip_z = grid.z_of(crotch) + HIP_RISE * height
    ankle_index = _slice_at(ANKLE_RISE)
    ankle_z = grid.z_of(ankle_index)
    hip_interval = _leg(rows[crotch - 1], sign)
    ankle_interval = _leg(rows[ankle_index], sign)
    if hip_interval is None or ankle_interval is None:
        raise _crotch_missing()
    hip: Vec3 = (hip_interval.centre, hip_interval.mean_y, hip_z)
    ankle: Vec3 = (ankle_interval.centre, ankle_interval.mean_y, ankle_z)

    mid_z = (hip_z + ankle_z) / 2.0
    measured = _nearest(rows, grid.index(mid_z), lambda row: _leg(row, sign))
    if measured is None:
        raise _crotch_missing()
    _, knee_interval = measured
    knee_measured: Vec3 = (knee_interval.centre, knee_interval.mean_y, mid_z)
    knee = vec_lerp(knee_measured, vec_lerp(hip, ankle, 0.5), KNEE_LINE_WEIGHT)

    return {
        "hip": hip,
        "knee": knee,
        "ankle": ankle,
        "toe": _toe(points, grid, height, ankle, sign),
    }


def _toe(
    points: list[tuple[float, float, float]],
    grid: _Grid,
    height: float,
    ankle: Vec3,
    sign: float,
) -> Vec3:
    """The toe sits at the front of one side's foot, one gap inside its lowest vertex."""
    foot_top = grid.z_low + TOE_BAND * height
    front = [y for x, y, z in points if z < foot_top and x * sign > 0.0]
    front_y = (min(front) if front else ankle[1]) + TOE_LIFT * height
    return (ankle[0], front_y, grid.z_low + TOE_DEPTH * height)


def _find_armpit(rows: list[list[_Interval]], crotch: int) -> tuple[int, Chain, Chain]:
    """The highest slice below 92% of the height with the torso and an arm on each side."""
    for index in range(_slice_at(ARMPIT_CEILING) - 1, crotch, -1):
        if _central(rows[index]) is None:
            continue
        left = _arm_chain(rows, index, 1.0)
        if left is None:
            continue
        right = _arm_chain(rows, index, -1.0)
        if right is None:
            continue
        return index, left, right
    raise _arms_missing()


def _arm_chain(rows: list[list[_Interval]], start: int, sign: float) -> Chain | None:
    """The longest chain from a side interval at start that lasts at least 12% of the slices."""
    minimum = round(ARM_CHAIN_FRACTION * SLICE_COUNT)
    best: Chain | None = None
    for interval in _side_intervals(rows[start], sign):
        chain = _follow(rows, start, interval)
        if len(chain) >= minimum and (best is None or len(chain) > len(best)):
            best = chain
    return best


def _follow(rows: list[list[_Interval]], start: int, interval: _Interval) -> Chain:
    """Follow an arm downward, taking the outermost non-central overlap in each lower slice."""
    chain: Chain = [(start, interval)]
    current = interval
    for index in range(start - 1, -1, -1):
        reach = [
            iv
            for iv in rows[index]
            if not iv.spans_midline and iv.low <= current.high and iv.high >= current.low
        ]
        if not reach:
            break
        current = max(reach, key=lambda iv: abs(iv.centre))
        chain.append((index, current))
    return chain


def _fit_line(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Least-squares x = slope * z + intercept through (z, x) pairs."""
    count = len(points)
    mean_z = sum(z for z, _ in points) / count
    mean_x = sum(x for _, x in points) / count
    spread = sum((z - mean_z) ** 2 for z, _ in points)
    slope = sum((z - mean_z) * (x - mean_x) for z, x in points) / spread
    return slope, mean_x - slope * mean_z


def _arm_landmarks(chain: Chain, grid: _Grid, height: float) -> dict[str, Vec3]:
    """Shoulder, elbow, wrist, and hand tip for one arm, on a line fitted through its chain."""
    trim = round(ARM_FIT_TRIM * len(chain))
    middle = chain[trim : len(chain) - trim]
    slope, intercept = _fit_line([(grid.z_of(i), iv.centre) for i, iv in middle])
    count = sum(iv.count for _, iv in chain)
    mean_y = sum(iv.y_sum for _, iv in chain) / count

    shoulder_z = grid.z_of(chain[0][0]) + SHOULDER_RISE * height
    end_z = grid.z_of(chain[-1][0])
    shoulder: Vec3 = (slope * shoulder_z + intercept, mean_y, shoulder_z)
    end: Vec3 = (slope * end_z + intercept, mean_y, end_z)
    return {
        "shoulder": shoulder,
        "elbow": vec_lerp(shoulder, end, ELBOW_FRACTION),
        "wrist": vec_lerp(shoulder, end, WRIST_FRACTION),
        "hand_tip": vec_lerp(shoulder, end, HAND_TIP_FRACTION),
    }


def _neck(rows: list[list[_Interval]], grid: _Grid, shoulder_z: float, height: float) -> Vec3:
    """The narrowest central interval from the shoulder slice up to 95% of the height.

    Widths within one gap of the narrowest count as equal, so the lowest of them is the neck base.
    """
    candidates: list[tuple[int, _Interval]] = []
    for index in range(grid.index(shoulder_z), _slice_at(NECK_CEILING) + 1):
        interval = _central(rows[index])
        if interval is not None:
            candidates.append((index, interval))
    if not candidates:
        raise _arms_missing()
    narrowest = min(interval.width for _, interval in candidates)
    index, neck = next(
        (i, iv) for i, iv in candidates if iv.width <= narrowest + GAP_FRACTION * height
    )
    return (neck.centre, neck.mean_y, grid.z_of(index))


def _head_top(rows: list[list[_Interval]], grid: _Grid, height: float) -> Vec3:
    """The highest slice with a central interval gives the head's x and y."""
    found = _nearest(rows, SLICE_COUNT - 1, _central)
    if found is None:
        raise _crotch_missing()
    _, top = found
    return (top.centre, top.mean_y, grid.z_low + HEAD_TOP_FRACTION * height)


def _pelvis(rows: list[list[_Interval]], crotch_z: float, crotch: int, height: float) -> Vec3:
    """The central interval 7.5% of the height above the crotch gives the pelvis."""
    found = _nearest(rows, crotch + _slice_at(PELVIS_RISE), _central)
    if found is None:
        raise _crotch_missing()
    _, pelvis = found
    return (pelvis.centre, pelvis.mean_y, crotch_z + PELVIS_RISE * height)


def _mirror_warnings(out: dict[str, Vec3], height: float) -> list[str]:
    warnings: list[str] = []
    for base in _PAIRED_BASES:
        left = out[f"{base}_l"]
        right = out[f"{base}_r"]
        mirrored = (-right[0], right[1], right[2])
        if math.dist(left, mirrored) > MIRROR_TOLERANCE * height:
            warnings.append(f"{base}_l/{base}_r are not mirrored across X within 5% of the height")
    return warnings
