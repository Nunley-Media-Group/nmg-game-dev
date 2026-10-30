"""UE5 Mannequin deform skeleton and landmark-driven bone layout (pure Python)."""

from __future__ import annotations

import math
from collections.abc import Mapping

Vec3 = tuple[float, float, float]

# (bone, parent) in hierarchy order. The root has no parent.
MANNY_BONES: tuple[tuple[str, str | None], ...] = (
    ("root", None),
    ("pelvis", "root"),
    ("spine_01", "pelvis"),
    ("spine_02", "spine_01"),
    ("spine_03", "spine_02"),
    ("spine_04", "spine_03"),
    ("spine_05", "spine_04"),
    ("neck_01", "spine_05"),
    ("neck_02", "neck_01"),
    ("head", "neck_02"),
    ("clavicle_l", "spine_05"),
    ("upperarm_l", "clavicle_l"),
    ("lowerarm_l", "upperarm_l"),
    ("hand_l", "lowerarm_l"),
    ("clavicle_r", "spine_05"),
    ("upperarm_r", "clavicle_r"),
    ("lowerarm_r", "upperarm_r"),
    ("hand_r", "lowerarm_r"),
    ("thigh_l", "pelvis"),
    ("calf_l", "thigh_l"),
    ("foot_l", "calf_l"),
    ("ball_l", "foot_l"),
    ("thigh_r", "pelvis"),
    ("calf_r", "thigh_r"),
    ("foot_r", "calf_r"),
    ("ball_r", "foot_r"),
)

MANNY_BONE_NAMES: tuple[str, ...] = tuple(name for name, _ in MANNY_BONES)

_SIDED_LANDMARKS = ("shoulder", "elbow", "wrist", "hand_tip", "hip", "knee", "ankle", "toe")

LANDMARK_KEYS: tuple[str, ...] = ("pelvis", "neck", "head_top") + tuple(
    f"{base}_{side}" for base in _SIDED_LANDMARKS for side in ("l", "r")
)


def vec_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec_lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def vec_length(a: Vec3) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def bone_layout(landmarks: Mapping[str, Vec3]) -> dict[str, tuple[Vec3, Vec3]]:
    """Return {bone: (head, tail)} in MANNY_BONES order, from validated landmarks."""
    height = landmarks["head_top"][2] - min(landmarks["ankle_l"][2], landmarks["ankle_r"][2])
    pelvis = landmarks["pelvis"]
    neck = landmarks["neck"]
    head_top = landmarks["head_top"]

    layout: dict[str, tuple[Vec3, Vec3]] = {
        "root": ((0.0, 0.0, 0.0), (0.0, 0.0, 0.1 * height)),
        "pelvis": (pelvis, vec_lerp(pelvis, neck, 0.1)),
    }
    for index in range(1, 6):
        layout[f"spine_0{index}"] = (
            vec_lerp(pelvis, neck, (index - 1) / 5),
            vec_lerp(pelvis, neck, index / 5),
        )

    head_base = vec_lerp(neck, head_top, 0.85)
    neck_mid = vec_lerp(neck, head_base, 0.5)
    layout["neck_01"] = (neck, neck_mid)
    layout["neck_02"] = (neck_mid, head_base)
    layout["head"] = (head_base, head_top)

    lowered = (0.0, 0.0, -0.05 * height)
    for side in ("l", "r"):
        shoulder = landmarks[f"shoulder_{side}"]
        elbow = landmarks[f"elbow_{side}"]
        wrist = landmarks[f"wrist_{side}"]
        hand_tip = landmarks[f"hand_tip_{side}"]
        layout[f"clavicle_{side}"] = (
            vec_add(vec_lerp(neck, shoulder, 0.2), lowered),
            shoulder,
        )
        layout[f"upperarm_{side}"] = (shoulder, elbow)
        layout[f"lowerarm_{side}"] = (elbow, wrist)
        layout[f"hand_{side}"] = (wrist, hand_tip)

        hip = landmarks[f"hip_{side}"]
        knee = landmarks[f"knee_{side}"]
        ankle = landmarks[f"ankle_{side}"]
        toe = landmarks[f"toe_{side}"]
        ball = vec_lerp(ankle, toe, 0.7)
        layout[f"thigh_{side}"] = (hip, knee)
        layout[f"calf_{side}"] = (knee, ankle)
        layout[f"foot_{side}"] = (ankle, ball)
        layout[f"ball_{side}"] = (ball, toe)

    return {name: layout[name] for name, _ in MANNY_BONES}
