"""Humanoid fixtures for the estimate_landmarks tests.

build_a_pose(name, ...) builds collection <name> holding one voxel-remeshed mesh SM_<name>, posed
like rig_fixtures.build_hero but with an A-pose: arms about 40 degrees below horizontal, straight
elbows and knees, and legs apart. It returns the joint positions the mesh was built from, as 19
landmarks in meters, world space. The figure faces -Y, its left side is +X, and it stands on z=0.

Variants:
- stylized: a large head, with the shoulders at about 0.6 of the height.
- accessory: hat_brim, earrings, or glasses, sticking out sideways above the shoulders.
- asymmetric: "arm" drops the right arm to 30 degrees, which still leaves a long enough arm chain;
  "leg" moves the right leg 0.1 m outward.
  The known joints show each offset, so the test can name the pairs that must be flagged.
- fused_arms: a web of solid body joins the arms to the torso, so no arm can be followed down.
- no_crotch: the legs are one solid column, so the legs never split.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

Vec3 = tuple[float, float, float]

# Slices are 0.0088 m tall on a 1.76 m figure, so the remesh must leave vertices in every slice.
_VOXEL_SIZE = 0.005
_SHOULDER_X = 0.2
_HIP_X = 0.1
_ANKLE_Z = 0.08
_UPPER_ARM = 0.30
_FOREARM = 0.25
_HAND = 0.10
_ARM_RADIUS = 0.045
_THIGH_RADIUS = 0.07
_CALF_RADIUS = 0.055
_TOE_Y = -0.17
_TOE_Z = 0.04
_ASYMMETRIC_ARM_DEG = 30.0
_ASYMMETRIC_LEG_OFFSET = -0.1
_VALID_ACCESSORIES = ("hat_brim", "earrings", "glasses")
_VALID_ASYMMETRY = ("arm", "leg")


@dataclass(frozen=True)
class _Proportions:
    head_radius: float
    head_centre_z: float
    neck_base_z: float
    shoulder_z: float
    torso_bottom_z: float
    torso_top_z: float
    pelvis_z: float
    hip_z: float
    knee_z: float
    arm_drop_deg: float

    @property
    def head_top_z(self) -> float:
        return self.head_centre_z + self.head_radius


_REALISTIC = _Proportions(
    head_radius=0.11,
    head_centre_z=1.65,
    neck_base_z=1.44,
    shoulder_z=1.44,
    torso_bottom_z=0.95,
    torso_top_z=1.46,
    pelvis_z=0.98,
    hip_z=0.95,
    knee_z=0.50,
    arm_drop_deg=40.0,
)

_STYLIZED = _Proportions(
    head_radius=0.22,
    head_centre_z=1.54,
    neck_base_z=1.06,
    shoulder_z=1.06,
    torso_bottom_z=0.80,
    torso_top_z=1.08,
    pelvis_z=0.86,
    hip_z=0.82,
    knee_z=0.45,
    arm_drop_deg=40.0,
)


def build_a_pose(
    name: str,
    *,
    stylized: bool = False,
    accessory: str | None = None,
    asymmetric: str | None = None,
    fused_arms: bool = False,
    no_crotch: bool = False,
) -> dict[str, list[float]]:
    """Build collection <name> with mesh SM_<name> and return its 19 known joint positions."""
    import bmesh  # noqa: PLC0415
    import bpy  # noqa: PLC0415

    if accessory is not None and accessory not in _VALID_ACCESSORIES:
        raise ValueError(f"accessory must be one of {_VALID_ACCESSORIES}, not {accessory!r}")
    if asymmetric is not None and asymmetric not in _VALID_ASYMMETRY:
        raise ValueError(f"asymmetric must be one of {_VALID_ASYMMETRY}, not {asymmetric!r}")

    proportions = _STYLIZED if stylized else _REALISTIC
    joints = _joints(proportions, asymmetric)

    bm = bmesh.new()
    _add_body(bm, proportions, asymmetric)
    if accessory is not None:
        _add_accessory(bm, proportions, accessory)
    if fused_arms:
        _add_box(bm, (0.0, 0.0, 1.2), (1.6, 0.2, 0.6))
    if no_crotch:
        _add_box(bm, (0.0, 0.0, 0.5), (2 * 0.17, 0.2, 0.9))
    mesh = bpy.data.meshes.new(f"SM_{name}")
    bm.to_mesh(mesh)
    bm.free()

    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    obj = bpy.data.objects.new(f"SM_{name}", mesh)
    collection.objects.link(obj)
    _select_only([obj])
    mesh.remesh_voxel_size = _VOXEL_SIZE
    bpy.ops.object.voxel_remesh()
    return {key: list(value) for key, value in joints.items()}


def _joints(proportions: _Proportions, asymmetric: str | None) -> dict[str, Vec3]:
    p = proportions
    joints: dict[str, Vec3] = {
        "pelvis": (0.0, 0.0, p.pelvis_z),
        "neck": (0.0, 0.0, p.neck_base_z),
        "head_top": (0.0, 0.0, p.head_top_z),
    }
    for side, sign in (("l", 1.0), ("r", -1.0)):
        drop = _ASYMMETRIC_ARM_DEG if asymmetric == "arm" and side == "r" else p.arm_drop_deg
        shoulder, elbow, wrist, tip = _arm_joints(p, sign, drop)
        leg_x = sign * _HIP_X
        if asymmetric == "leg" and side == "r":
            leg_x += _ASYMMETRIC_LEG_OFFSET
        joints[f"shoulder_{side}"] = shoulder
        joints[f"elbow_{side}"] = elbow
        joints[f"wrist_{side}"] = wrist
        joints[f"hand_tip_{side}"] = tip
        joints[f"hip_{side}"] = (leg_x, 0.0, p.hip_z)
        joints[f"knee_{side}"] = (leg_x, 0.0, p.knee_z)
        joints[f"ankle_{side}"] = (leg_x, 0.0, _ANKLE_Z)
        joints[f"toe_{side}"] = (leg_x, _TOE_Y, _TOE_Z)
    return joints


def _arm_joints(proportions: _Proportions, sign: float, drop_deg: float) -> tuple[Vec3, ...]:
    """Shoulder, elbow, wrist, and hand tip for one arm: straight segments at drop_deg."""
    angle = math.radians(drop_deg)
    direction = (sign * math.cos(angle), 0.0, -math.sin(angle))
    shoulder = (sign * _SHOULDER_X, 0.0, proportions.shoulder_z)
    elbow = _along(shoulder, direction, _UPPER_ARM)
    wrist = _along(elbow, direction, _FOREARM)
    tip = _along(wrist, direction, _HAND)
    return shoulder, elbow, wrist, tip


def _along(start: Vec3, direction: Vec3, length: float) -> Vec3:
    return (
        start[0] + direction[0] * length,
        start[1] + direction[1] * length,
        start[2] + direction[2] * length,
    )


def _add_body(bm: Any, p: _Proportions, asymmetric: str | None) -> None:
    _add_box(
        bm,
        (0.0, 0.0, (p.torso_bottom_z + p.torso_top_z) / 2.0),
        (0.36, 0.2, p.torso_top_z - p.torso_bottom_z),
    )
    _add_box(bm, (0.0, 0.0, p.pelvis_z), (0.44, 0.2, 0.16))
    _add_box(
        bm,
        (0.0, 0.0, (p.neck_base_z + p.head_centre_z) / 2.0),
        (0.10, 0.10, p.head_centre_z - p.neck_base_z),
    )
    _add_sphere(bm, (0.0, 0.0, p.head_centre_z), p.head_radius)
    for side, sign in (("l", 1.0), ("r", -1.0)):
        drop = _ASYMMETRIC_ARM_DEG if asymmetric == "arm" and side == "r" else p.arm_drop_deg
        shoulder, elbow, wrist, tip = _arm_joints(p, sign, drop)
        _add_segment(bm, shoulder, elbow, _ARM_RADIUS)
        _add_segment(bm, elbow, wrist, _ARM_RADIUS)
        _add_segment(bm, wrist, tip, _ARM_RADIUS)

        leg_x = sign * _HIP_X
        if asymmetric == "leg" and side == "r":
            leg_x += _ASYMMETRIC_LEG_OFFSET
        hip = (leg_x, 0.0, p.hip_z)
        knee = (leg_x, 0.0, p.knee_z)
        ankle = (leg_x, 0.0, _ANKLE_Z)
        _add_segment(bm, hip, knee, _THIGH_RADIUS)
        _add_segment(bm, knee, ankle, _CALF_RADIUS)
        _add_box(bm, (leg_x, -0.05, 0.04), (0.10, 0.26, 0.08))


def _add_accessory(bm: Any, p: _Proportions, accessory: str) -> None:
    """Sideways pieces above the shoulders, each clear of the head by more than one gap."""
    for sign in (1.0, -1.0):
        if accessory == "hat_brim":
            _add_box(bm, (sign * 0.34, 0.0, p.head_centre_z + 0.02), (0.16, 0.2, 0.03))
        elif accessory == "glasses":
            _add_box(bm, (sign * 0.31, 0.0, p.head_centre_z + 0.04), (0.10, 0.04, 0.03))
        else:
            _add_sphere(bm, (sign * 0.28, 0.0, p.head_centre_z - 0.09), 0.03)


def _add_box(bm: Any, centre: Vec3, size: Vec3) -> None:
    import bmesh  # noqa: PLC0415
    from mathutils import Matrix  # noqa: PLC0415

    cube = bmesh.ops.create_cube(bm, size=1.0)
    matrix = Matrix.Translation(centre) @ Matrix.Diagonal((size[0], size[1], size[2], 1.0))
    bmesh.ops.transform(bm, matrix=matrix, verts=cube["verts"])


def _add_sphere(bm: Any, centre: Vec3, radius: float) -> None:
    import bmesh  # noqa: PLC0415
    from mathutils import Matrix  # noqa: PLC0415

    sphere = bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=12, radius=radius)
    bmesh.ops.transform(bm, matrix=Matrix.Translation(centre), verts=sphere["verts"])


def _add_segment(bm: Any, start: Vec3, end: Vec3, radius: float) -> None:
    """A square-section limb from start to end, with side 2 * radius."""
    import bmesh  # noqa: PLC0415
    from mathutils import Matrix, Vector  # noqa: PLC0415

    a = Vector(start)
    b = Vector(end)
    axis = b - a
    turn = Vector((1.0, 0.0, 0.0)).rotation_difference(axis).to_matrix().to_4x4()
    scale = Matrix.Diagonal((axis.length, 2.0 * radius, 2.0 * radius, 1.0))
    matrix = Matrix.Translation((a + b) / 2.0) @ turn @ scale
    cube = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.transform(bm, matrix=matrix, verts=cube["verts"])


def _select_only(objects: list[Any]) -> None:
    import bpy  # noqa: PLC0415

    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
