"""Humanoid landmark validation. Runs the design check table in order (pure Python)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .outcome import STATUS_FALLBACK, STATUS_SPIKE, fail
from .skeleton import LANDMARK_KEYS, Vec3, vec_length, vec_sub

BBox = tuple[Vec3, Vec3]

_SIDED_BASES = ("shoulder", "elbow", "wrist", "hand_tip", "hip", "knee", "ankle", "toe")
_MAX_ARM_RAISE_DEG = 5.0
_MAX_ARM_DROP_DEG = 50.0
_MAX_JOINT_BEND_DEG = 15.0
_MAX_HIP_TILT_DEG = 15.0


def validate(
    body_type: str, landmarks: Mapping[str, Any], bbox: BBox | None
) -> dict[str, Any] | None:
    """Return the first failure result, or None when the landmarks are usable.

    bbox is the world bounding box of SM_<Name>, or None when that mesh is missing.
    """
    if body_type != "humanoid":
        return fail(
            STATUS_SPIKE,
            "rig.unsupported_body",
            f"Body type '{body_type}' cannot be auto-rigged.",
            "Only humanoid bodies are auto-rigged. Quadruped and non-biped rigs need a "
            "follow-up spike.",
        )
    if bbox is None:
        return fail(
            STATUS_FALLBACK,
            "rig.asset_not_found",
            "The collection has no root mesh SM_<Name>.",
            "Model the character in a collection named <Name> with a root mesh SM_<Name>, "
            "then rerun.",
        )

    points: dict[str, Vec3] = {}
    for key in LANDMARK_KEYS:
        value = landmarks.get(key)
        if not _is_point(value):
            return fail(
                STATUS_FALLBACK,
                "rig.landmarks_missing",
                f"Landmark '{key}' is missing or is not a finite [x, y, z].",
                "Supply every landmark key as [x, y, z] in meters, world space. See "
                "docs/rigging-and-animation.md for the landmark keys.",
            )
        points[key] = (float(value[0]), float(value[1]), float(value[2]))

    height = points["head_top"][2] - min(points["ankle_l"][2], points["ankle_r"][2])
    margin = 0.02 * max(height, 0.0)
    low, high = bbox
    for key, point in points.items():
        if any(point[i] < low[i] - margin or point[i] > high[i] + margin for i in range(3)):
            return fail(
                STATUS_FALLBACK,
                "rig.landmarks_outside_mesh",
                f"Landmark '{key}' lies outside the bounding box of SM_<Name>.",
                "Move the landmark onto the character, in world space and in meters, or fix "
                "the mesh's scale and placement, then rerun.",
            )

    unclear = _unclear_reason(points, height)
    if unclear is not None:
        return fail(
            STATUS_FALLBACK,
            "rig.unclear_humanoid",
            unclear,
            "Make the landmarks symmetric, put them in vertical order, and put each _l "
            "landmark on the +X side and each _r landmark on the -X side, then rerun.",
        )

    pose = _pose_reason(points)
    if pose is not None:
        return fail(
            STATUS_FALLBACK,
            "rig.pose_not_neutral",
            pose,
            "Pose the character in a neutral T or A pose: arms out level or down to 50 "
            "degrees, elbows and knees straight, and legs under the hips, then rerun.",
        )
    return None


def _is_point(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return False
    return all(
        isinstance(coord, (int, float)) and not isinstance(coord, bool) and math.isfinite(coord)
        for coord in value
    )


def _unclear_reason(points: Mapping[str, Vec3], height: float) -> str | None:
    for base in _SIDED_BASES:
        left = points[f"{base}_l"]
        right = points[f"{base}_r"]
        if left[0] <= 0 or right[0] >= 0:
            return f"The {base} landmarks are on the wrong side of the body."
        mirrored_right = (-right[0], right[1], right[2])
        if vec_length(vec_sub(left, mirrored_right)) > 0.05 * height:
            return f"The {base} landmarks are not symmetric about the X axis."

    head_top, neck, pelvis = points["head_top"], points["neck"], points["pelvis"]
    for side in ("l", "r"):
        hip = points[f"hip_{side}"]
        knee = points[f"knee_{side}"]
        ankle = points[f"ankle_{side}"]
        ordered = (
            head_top[2] > neck[2] > pelvis[2] > knee[2] > ankle[2] and pelvis[2] > hip[2] > knee[2]
        )
        if not ordered:
            return "The landmarks are not in vertical order (head, neck, pelvis, hip, knee, ankle)."
    return None


def _pose_reason(points: Mapping[str, Vec3]) -> str | None:
    for side in ("l", "r"):
        shoulder = points[f"shoulder_{side}"]
        elbow = points[f"elbow_{side}"]
        wrist = points[f"wrist_{side}"]
        hip = points[f"hip_{side}"]
        knee = points[f"knee_{side}"]
        ankle = points[f"ankle_{side}"]

        arm = vec_sub(wrist, shoulder)
        elevation = math.degrees(math.atan2(arm[2], math.hypot(arm[0], arm[1])))
        if elevation > _MAX_ARM_RAISE_DEG or elevation < -_MAX_ARM_DROP_DEG:
            return "An arm is raised above horizontal or dropped more than 50 degrees."

        elbow_angle = _angle_deg(vec_sub(shoulder, elbow), vec_sub(wrist, elbow))
        if elbow_angle is None or 180.0 - elbow_angle > _MAX_JOINT_BEND_DEG:
            return "An elbow is bent more than 15 degrees."

        knee_angle = _angle_deg(vec_sub(hip, knee), vec_sub(ankle, knee))
        if knee_angle is None or 180.0 - knee_angle > _MAX_JOINT_BEND_DEG:
            return "A knee is bent more than 15 degrees."

        leg = vec_sub(ankle, hip)
        tilt = math.degrees(math.atan2(math.hypot(leg[0], leg[1]), abs(leg[2])))
        if tilt > _MAX_HIP_TILT_DEG:
            return "A leg is more than 15 degrees from vertical under the hips."
    return None


def _angle_deg(a: Vec3, b: Vec3) -> float | None:
    length = vec_length(a) * vec_length(b)
    if length == 0.0:
        return None
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / length))))
