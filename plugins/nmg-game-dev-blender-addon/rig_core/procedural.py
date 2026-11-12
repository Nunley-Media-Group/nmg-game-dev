"""Pure pose solver for built-in clips: stick-figure targets to local bone quaternions.

No bpy or mathutils import, so it runs under plain CPython. Matrices are 3x3 tuples of rows and
quaternions are (w, x, y, z). A bone's armature rotation is parent_pose · rest_relative · local,
which is Blender's pose composition, so the quaternions returned here are the values to store on
pose_bone.rotation_quaternion.

Accumulated rotations A are armature-space deltas from rest. A bone's armature rotation is
A_b · R_b, where R_b is its rest rotation, so its local quaternion is
R_b⁻¹ · A_parent⁻¹ · A_b · R_b.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .skeleton import MANNY_BONES, Vec3, vec_length, vec_sub

Mat3 = tuple[Vec3, Vec3, Vec3]
Quat = tuple[float, float, float, float]

_IDENTITY: Mat3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
_Y_AXIS: Vec3 = (0.0, 1.0, 0.0)
_EPSILON = 1e-12


@dataclass(frozen=True)
class RestSkeleton:
    """Each Manny bone's armature-space rest rotation and head, plus the leg length."""

    rotations: Mapping[str, Mat3]
    heads: Mapping[str, Vec3]
    leg_length: float

    @classmethod
    def from_bones(cls, rotations: Mapping[str, Mat3], heads: Mapping[str, Vec3]) -> RestSkeleton:
        """Leg length is the mean over both sides of |hip→knee| + |knee→ankle|."""
        lengths = [
            vec_length(vec_sub(heads[f"calf_{side}"], heads[f"thigh_{side}"]))
            + vec_length(vec_sub(heads[f"foot_{side}"], heads[f"calf_{side}"]))
            for side in ("l", "r")
        ]
        return cls(
            rotations=dict(rotations),
            heads=dict(heads),
            leg_length=sum(lengths) / len(lengths),
        )


def solve(rest: RestSkeleton, pose: Mapping[str, Any]) -> tuple[dict[str, Quat], Vec3]:
    """Return each Manny bone's local quaternion and the pelvis location for one pose.

    Bones are walked parent first. A bone with an Euler target is rotated in character space,
    then a bone with a direction target is rotated by the minimal rotation that points its Y
    axis along that direction. Every other bone inherits its parent's rotation.
    """
    directions: Mapping[str, Vec3] = pose["dir"]
    euler: Mapping[str, Vec3] = pose["rot"]
    accumulated: dict[str, Mat3] = {}
    quats: dict[str, Quat] = {}
    for bone, parent in MANNY_BONES:
        rest_rot = rest.rotations[bone]
        parent_acc = accumulated[parent] if parent is not None else _IDENTITY
        acc = parent_acc
        if bone in euler:
            acc = mat_mul(euler_xyz_matrix(euler[bone]), acc)
        if bone in directions:
            current = _apply(mat_mul(acc, rest_rot), _Y_AXIS)
            acc = mat_mul(rotation_between(current, directions[bone]), acc)
        accumulated[bone] = acc
        local = mat_mul(
            transpose(rest_rot),
            mat_mul(transpose(parent_acc), mat_mul(acc, rest_rot)),
        )
        quats[bone] = matrix_to_quat(local)
    pelvis_offset = _scale(tuple(pose["off"]), rest.leg_length)
    location = _apply(transpose(rest.rotations["pelvis"]), pelvis_offset)
    return quats, location


def continuous(previous: Quat | None, current: Quat) -> Quat:
    """Flip current's sign when it lies on the opposite side of previous, keeping keys smooth."""
    if previous is None or _quat_dot(previous, current) >= 0.0:
        return current
    return (-current[0], -current[1], -current[2], -current[3])


def euler_xyz_matrix(degrees: Vec3) -> Mat3:
    """Rotation for Euler angles in degrees, applied X first (Rz · Ry · Rx)."""
    rx, ry, rz = (math.radians(value) for value in degrees)
    return mat_mul(
        _axis_angle((0.0, 0.0, 1.0), rz),
        mat_mul(_axis_angle((0.0, 1.0, 0.0), ry), _axis_angle((1.0, 0.0, 0.0), rx)),
    )


def rotation_between(source: Vec3, target: Vec3) -> Mat3:
    """Minimal rotation that takes the direction source onto the direction target."""
    src = normalize(source)
    dst = normalize(target)
    cosine = max(-1.0, min(1.0, _dot(src, dst)))
    if cosine >= 1.0 - _EPSILON:
        return _IDENTITY
    if cosine <= -1.0 + _EPSILON:
        reference = (1.0, 0.0, 0.0) if abs(src[0]) < 0.9 else (0.0, 1.0, 0.0)
        return _axis_angle(normalize(_cross(src, reference)), math.pi)
    return _axis_angle(normalize(_cross(src, dst)), math.acos(cosine))


def normalize(vector: Vec3) -> Vec3:
    length = vec_length(vector)
    if length < _EPSILON:
        raise ValueError("A zero-length direction has no orientation.")
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def mat_mul(a: Mat3, b: Mat3) -> Mat3:
    columns = transpose(b)
    return _mat([[_dot(row, column) for column in columns] for row in a])


def transpose(m: Mat3) -> Mat3:
    return _mat([[m[0][c], m[1][c], m[2][c]] for c in range(3)])


def matrix_to_quat(m: Mat3) -> Quat:
    """Unit quaternion for a rotation matrix, with w >= 0."""
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        quat = (0.25 * s, (m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s)
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2.0
        quat = ((m[2][1] - m[1][2]) / s, 0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s)
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2.0
        quat = ((m[0][2] - m[2][0]) / s, (m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s)
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2.0
        quat = ((m[1][0] - m[0][1]) / s, (m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s)
    norm = math.sqrt(sum(value * value for value in quat))
    w, x, y, z = (value / norm for value in quat)
    if w < 0.0:
        return (-w, -x, -y, -z)
    return (w, x, y, z)


def quat_to_matrix(q: Quat) -> Mat3:
    w, x, y, z = q
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
        (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
        (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)),
    )


def _axis_angle(axis: Vec3, angle: float) -> Mat3:
    x, y, z = axis
    c = math.cos(angle)
    s = math.sin(angle)
    t = 1.0 - c
    return (
        (t * x * x + c, t * x * y - s * z, t * x * z + s * y),
        (t * x * y + s * z, t * y * y + c, t * y * z - s * x),
        (t * x * z - s * y, t * y * z + s * x, t * z * z + c),
    )


def _mat(rows: list[list[float]]) -> Mat3:
    return (
        (rows[0][0], rows[0][1], rows[0][2]),
        (rows[1][0], rows[1][1], rows[1][2]),
        (rows[2][0], rows[2][1], rows[2][2]),
    )


def _apply(m: Mat3, v: Vec3) -> Vec3:
    return (_dot(m[0], v), _dot(m[1], v), _dot(m[2], v))


def _scale(v: Vec3, factor: float) -> Vec3:
    return (v[0] * factor, v[1] * factor, v[2] * factor)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _quat_dot(a: Quat, b: Quat) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]
