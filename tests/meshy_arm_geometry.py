"""Pure-Python geometry of the #106 box humanoid and the #135 stylized character, for the Blender
fixtures and the BDD steps.

The box humanoid is 1.8 m tall with its feet on z = 0, symmetric about X = 0 and Y = 0. Its
shoulders are the pivot rule's points, (±0.10·H, 0, 0.81·H). Each arm runs from its pivot along
a direction dropped ``drop_deg`` below horizontal, so a hand tip at arm length L sits exactly
that far below its pivot. The elbow is at 0.4 L and the wrist at 0.8 L. Landmark keys follow
``rig_core.skeleton``: ``_l`` is the +X side and ``_r`` the -X side.

The #135 stylized character has its shoulders at 0.6·H on the torso's outboard edge, a head wider
than the torso whose bottom is above the shoulder cap, a wide stance with boots and a skirt, and a
detached box outboard of each arm below its hand tip. Its arms are dropped 55 degrees with their
axes through the true shoulders. ``stylized_parts`` describes every box, and ``fused_right_arm``
adds a web that welds the right arm to the body. Nothing here imports bpy, so pytest can use it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

Point = tuple[float, float, float]

HEIGHT: Final = 1.8
PIVOT_X: Final = 0.10 * HEIGHT
SHOULDER_Z: Final = 0.81 * HEIGHT
HIP_Z: Final = 0.95
ARM_LENGTH: Final = 0.6
ARM_HALF_WIDTH: Final = 0.05
BODY_HALF_DEPTH: Final = 0.08

# #135 stylized character: shoulders at 0.6·H on the torso's outboard edge.
STYLIZED_SHOULDER_Z: Final = 0.6 * HEIGHT
STYLIZED_TORSO_HALF_WIDTH: Final = 0.15
STYLIZED_ARM_LENGTH: Final = 0.6
STYLIZED_ARM_HALF_WIDTH: Final = 0.05
STYLIZED_ARM_DROP_DEG: Final = 55.0
# The parts that are not arms, and the detached boxes that sit outboard of each arm below its tip.
STYLIZED_BODY_PARTS: Final = (
    "torso",
    "neck",
    "head",
    "leg_left",
    "leg_right",
    "boot_left",
    "boot_right",
    "skirt_left",
    "skirt_right",
)
STYLIZED_DETACHED_PARTS: Final = ("detached_left", "detached_right")


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


def _as_point(values: Sequence[float]) -> Point:
    return (values[0], values[1], values[2])


def raise_arm_landmarks(
    points: Mapping[str, list[float]],
    rotations: Mapping[str, float],
    pivots: Mapping[str, Sequence[float]] | None = None,
) -> dict[str, list[float]]:
    """Return ``points`` with each side's elbow, wrist, and hand tip rotated about its shoulder.

    ``rotations`` maps ``left`` and ``right`` to the ``rotation_deg`` the import reported for that
    side. ``pivots`` maps a side to the shoulder to rotate about, which is the import's reported
    shoulder; when a side is absent the true pivot ``side_pivot`` is used. The rotation is the
    import's, applied to the landmarks as the same per-vertex transform.
    """
    raised = {key: list(value) for key, value in points.items()}
    for suffix, sign, side in (("l", 1.0, "left"), ("r", -1.0, "right")):
        if pivots is not None and side in pivots:
            pivot = _as_point(pivots[side])
        else:
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


@dataclass(frozen=True)
class Part:
    """An axis-aligned box of the stylized character, named for the tests."""

    name: str
    low: Point
    high: Point


def stylized_parts(*, fused_right_arm: bool = False) -> tuple[Part, ...]:
    """Return the boxes of the #135 stylized character, arms excluded.

    The torso is the only body part that spans the midline above z = 0.8, and the legs, boots, and
    skirt panels leave the midline open below it. ``fused_right_arm`` adds a web from the right
    arm's base to the torso's side, so the right arm touches the body at every slice that holds the
    torso and has no armpit.
    """
    parts = [
        Part("torso", (-0.15, -0.10, 0.80), (0.15, 0.10, 1.30)),
        Part("neck", (-0.06, -0.06, 1.30), (0.06, 0.06, 1.36)),
        Part("head", (-0.20, -0.15, 1.36), (0.20, 0.15, HEIGHT)),
        Part("leg_left", (0.06, -0.08, 0.14), (0.22, 0.08, 0.80)),
        Part("leg_right", (-0.22, -0.08, 0.14), (-0.06, 0.08, 0.80)),
        Part("boot_left", (0.04, -0.12, 0.00), (0.26, 0.12, 0.14)),
        Part("boot_right", (-0.26, -0.12, 0.00), (-0.04, 0.12, 0.14)),
        Part("skirt_left", (0.05, -0.12, 0.55), (0.20, 0.12, 0.85)),
        Part("skirt_right", (-0.20, -0.12, 0.55), (-0.05, 0.12, 0.85)),
        Part("detached_left", (0.44, -0.05, 0.20), (0.56, 0.05, 0.40)),
        Part("detached_right", (-0.56, -0.05, 0.20), (-0.44, 0.05, 0.40)),
    ]
    if fused_right_arm:
        parts.append(Part("web_right", (-0.30, -0.08, 0.80), (-0.12, 0.08, 1.12)))
    return tuple(parts)


def box_corners(part: Part) -> list[Point]:
    """Return the eight corners of ``part``."""
    (x0, y0, z0), (x1, y1, z1) = part.low, part.high
    return [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]


def stylized_shoulder(sign: float) -> Point:
    """Return the true shoulder on side ``sign``: the torso's outboard edge at 0.6·H."""
    return (sign * STYLIZED_TORSO_HALF_WIDTH, 0.0, STYLIZED_SHOULDER_Z)


def stylized_hand_tip(sign: float) -> Point:
    """Return the true hand tip on side ``sign``: the shoulder plus the arm length on its drop."""
    pivot = stylized_shoulder(sign)
    along, _ = arm_directions(sign, STYLIZED_ARM_DROP_DEG)
    return (
        pivot[0] + STYLIZED_ARM_LENGTH * along[0],
        pivot[1] + STYLIZED_ARM_LENGTH * along[1],
        pivot[2] + STYLIZED_ARM_LENGTH * along[2],
    )


def stylized_body_points() -> list[Point]:
    """Return the corners of every non-arm body box, which are the vertices that must not move."""
    return [
        corner
        for part in stylized_parts()
        if part.name in STYLIZED_BODY_PARTS
        for corner in box_corners(part)
    ]
