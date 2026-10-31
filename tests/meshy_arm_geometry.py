"""Pure-Python geometry of the #106 box humanoid, for the Blender fixture and the BDD steps.

The humanoid is 1.8 m tall with its feet on z = 0, symmetric about X = 0 and Y = 0. Its
shoulders are the pivot rule's points, (±0.10·H, 0, 0.81·H). Each arm runs from its pivot along
a direction dropped ``drop_deg`` below horizontal, so a hand tip at arm length L sits exactly
that far below its pivot. The elbow is at 0.4 L and the wrist at 0.8 L. Landmark keys follow
``rig_core.skeleton``: ``_l`` is the +X side and ``_r`` the -X side. Nothing here imports bpy,
so pytest can use it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Final

Point = tuple[float, float, float]

HEIGHT: Final = 1.8
PIVOT_X: Final = 0.10 * HEIGHT
SHOULDER_Z: Final = 0.81 * HEIGHT
HIP_Z: Final = 0.95
ARM_LENGTH: Final = 0.6
ARM_HALF_WIDTH: Final = 0.05
BODY_HALF_DEPTH: Final = 0.08


def side_pivot(sign: float) -> Point:
    """Return the shoulder pivot on side ``sign`` (+1 is the +X, left side)."""
    return (sign * PIVOT_X, 0.0, SHOULDER_Z)


def arm_directions(sign: float, drop_deg: float) -> tuple[Point, Point]:
    """Return the arm's unit direction and its outward-up normal, both in the X-Z plane."""
    down = math.radians(drop_deg)
    along = (sign * math.cos(down), 0.0, -math.sin(down))
    across = (sign * math.sin(down), 0.0, math.cos(down))
    return along, across


def along_arm(pivot: Point, along: Point, fraction: float) -> Point:
    """Return the point ``fraction`` of the arm length from ``pivot`` along ``along``."""
    return (
        pivot[0] + fraction * ARM_LENGTH * along[0],
        pivot[1] + fraction * ARM_LENGTH * along[1],
        pivot[2] + fraction * ARM_LENGTH * along[2],
    )


def raise_about_pivot(point: Point, pivot: Point, angle: float) -> Point:
    """Rotate ``point`` about the Y axis through ``pivot`` by ``angle`` radians."""
    dx = point[0] - pivot[0]
    dz = point[2] - pivot[2]
    return (
        pivot[0] + math.cos(angle) * dx + math.sin(angle) * dz,
        point[1],
        pivot[2] - math.sin(angle) * dx + math.cos(angle) * dz,
    )


def landmarks(drop_deg: float) -> dict[str, list[float]]:
    """Return every rig landmark of the humanoid whose arms drop ``drop_deg`` below horizontal."""
    points: dict[str, list[float]] = {
        "pelvis": [0.0, 0.0, 1.0],
        "neck": [0.0, 0.0, 1.5],
        "head_top": [0.0, 0.0, HEIGHT],
    }
    for sign, suffix in ((1.0, "l"), (-1.0, "r")):
        pivot = side_pivot(sign)
        along, _ = arm_directions(sign, drop_deg)
        points[f"shoulder_{suffix}"] = list(pivot)
        points[f"elbow_{suffix}"] = list(along_arm(pivot, along, 0.4))
        points[f"wrist_{suffix}"] = list(along_arm(pivot, along, 0.8))
        points[f"hand_tip_{suffix}"] = list(along_arm(pivot, along, 1.0))
        points[f"hip_{suffix}"] = [sign * 0.1, 0.0, HIP_Z]
        points[f"knee_{suffix}"] = [sign * 0.1, 0.0, 0.5]
        points[f"ankle_{suffix}"] = [sign * 0.1, 0.0, 0.08]
        points[f"toe_{suffix}"] = [sign * 0.1, -0.08, 0.03]
    return points


def drop_deg_from(pivot: Sequence[float], point: Sequence[float]) -> float:
    """Return how many degrees the line from ``pivot`` to ``point`` falls below horizontal."""
    horizontal = math.hypot(point[0] - pivot[0], point[1] - pivot[1])
    return math.degrees(math.atan2(pivot[2] - point[2], horizontal))


def _as_point(values: list[float]) -> Point:
    return (values[0], values[1], values[2])


def raise_arm_landmarks(
    points: Mapping[str, list[float]], rotations: Mapping[str, float]
) -> dict[str, list[float]]:
    """Return ``points`` with each side's elbow, wrist, and hand tip rotated about its shoulder.

    ``rotations`` maps ``left`` and ``right`` to the ``rotation_deg`` the import reported for that
    side. The rotation is the import's, applied to the landmarks as the same per-vertex transform.
    """
    raised = {key: list(value) for key, value in points.items()}
    for suffix, sign, side in (("l", 1.0, "left"), ("r", -1.0, "right")):
        pivot = side_pivot(sign)
        angle = math.radians(-sign * rotations[side])
        for base in ("elbow", "wrist", "hand_tip"):
            key = f"{base}_{suffix}"
            raised[key] = list(raise_about_pivot(_as_point(points[key]), pivot, angle))
    return raised


def bounding_box(drop_deg: float) -> tuple[Point, Point]:
    """Return the humanoid's world bounding box, with its arms dropped ``drop_deg``."""
    reach = PIVOT_X + ARM_LENGTH * math.cos(math.radians(drop_deg))
    return ((-reach, -BODY_HALF_DEPTH, 0.0), (reach, BODY_HALF_DEPTH, HEIGHT))
