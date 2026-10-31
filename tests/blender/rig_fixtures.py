"""Fixtures for the rigging and animation tests.

Builds three things inside Blender: Hero (a T-pose humanoid of joined primitives, voxel
remeshed into one manifold mesh, with matching landmarks), a Mixamo-named source armature
keyed with Idle and Walk, and a temporary animation library exported from that source.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

HERO_LANDMARKS: dict[str, list[float]] = {
    "pelvis": [0.0, 0.0, 1.0],
    "neck": [0.0, 0.0, 1.42],
    "head_top": [0.0, 0.0, 1.76],
    "shoulder_l": [0.2, 0.0, 1.45],
    "elbow_l": [0.5, 0.0, 1.45],
    "wrist_l": [0.8, 0.0, 1.45],
    "hand_tip_l": [0.9, 0.0, 1.45],
    "hip_l": [0.1, 0.0, 0.95],
    "knee_l": [0.1, 0.0, 0.5],
    "ankle_l": [0.1, 0.0, 0.08],
    "toe_l": [0.1, -0.15, 0.03],
    "shoulder_r": [-0.2, 0.0, 1.45],
    "elbow_r": [-0.5, 0.0, 1.45],
    "wrist_r": [-0.8, 0.0, 1.45],
    "hand_tip_r": [-0.9, 0.0, 1.45],
    "hip_r": [-0.1, 0.0, 0.95],
    "knee_r": [-0.1, 0.0, 0.5],
    "ankle_r": [-0.1, 0.0, 0.08],
    "toe_r": [-0.1, -0.15, 0.03],
}

# The 26 UE5 Mannequin deform bones, in hierarchy order.
MANNY_BONE_NAMES: tuple[str, ...] = (
    "root",
    "pelvis",
    "spine_01",
    "spine_02",
    "spine_03",
    "spine_04",
    "spine_05",
    "neck_01",
    "neck_02",
    "head",
    "clavicle_l",
    "upperarm_l",
    "lowerarm_l",
    "hand_l",
    "clavicle_r",
    "upperarm_r",
    "lowerarm_r",
    "hand_r",
    "thigh_l",
    "calf_l",
    "foot_l",
    "ball_l",
    "thigh_r",
    "calf_r",
    "foot_r",
    "ball_r",
)

# (name, parent, head, tail) for the Mixamo-named source skeleton, in meters.
_MIXAMO_BONES: tuple[
    tuple[str, str | None, tuple[float, float, float], tuple[float, float, float]], ...
] = (
    ("mixamorig:Hips", None, (0.0, 0.0, 1.0), (0.0, 0.0, 1.1)),
    ("mixamorig:Spine", "mixamorig:Hips", (0.0, 0.0, 1.1), (0.0, 0.0, 1.2)),
    ("mixamorig:Spine1", "mixamorig:Spine", (0.0, 0.0, 1.2), (0.0, 0.0, 1.3)),
    ("mixamorig:Spine2", "mixamorig:Spine1", (0.0, 0.0, 1.3), (0.0, 0.0, 1.42)),
    ("mixamorig:Neck", "mixamorig:Spine2", (0.0, 0.0, 1.42), (0.0, 0.0, 1.55)),
    ("mixamorig:Head", "mixamorig:Neck", (0.0, 0.0, 1.55), (0.0, 0.0, 1.76)),
    ("mixamorig:LeftShoulder", "mixamorig:Spine2", (0.0, 0.0, 1.42), (0.2, 0.0, 1.45)),
    ("mixamorig:LeftArm", "mixamorig:LeftShoulder", (0.2, 0.0, 1.45), (0.5, 0.0, 1.45)),
    ("mixamorig:LeftForeArm", "mixamorig:LeftArm", (0.5, 0.0, 1.45), (0.8, 0.0, 1.45)),
    ("mixamorig:LeftHand", "mixamorig:LeftForeArm", (0.8, 0.0, 1.45), (0.9, 0.0, 1.45)),
    ("mixamorig:RightShoulder", "mixamorig:Spine2", (0.0, 0.0, 1.42), (-0.2, 0.0, 1.45)),
    ("mixamorig:RightArm", "mixamorig:RightShoulder", (-0.2, 0.0, 1.45), (-0.5, 0.0, 1.45)),
    (
        "mixamorig:RightForeArm",
        "mixamorig:RightArm",
        (-0.5, 0.0, 1.45),
        (-0.8, 0.0, 1.45),
    ),
    ("mixamorig:RightHand", "mixamorig:RightForeArm", (-0.8, 0.0, 1.45), (-0.9, 0.0, 1.45)),
    ("mixamorig:LeftUpLeg", "mixamorig:Hips", (0.1, 0.0, 0.95), (0.1, 0.0, 0.5)),
    ("mixamorig:LeftLeg", "mixamorig:LeftUpLeg", (0.1, 0.0, 0.5), (0.1, 0.0, 0.08)),
    ("mixamorig:LeftFoot", "mixamorig:LeftLeg", (0.1, 0.0, 0.08), (0.1, -0.15, 0.03)),
    ("mixamorig:LeftToeBase", "mixamorig:LeftFoot", (0.1, -0.15, 0.03), (0.1, -0.2, 0.0)),
    ("mixamorig:RightUpLeg", "mixamorig:Hips", (-0.1, 0.0, 0.95), (-0.1, 0.0, 0.5)),
    ("mixamorig:RightLeg", "mixamorig:RightUpLeg", (-0.1, 0.0, 0.5), (-0.1, 0.0, 0.08)),
    ("mixamorig:RightFoot", "mixamorig:RightLeg", (-0.1, 0.0, 0.08), (-0.1, -0.15, 0.03)),
    (
        "mixamorig:RightToeBase",
        "mixamorig:RightFoot",
        (-0.1, -0.15, 0.03),
        (-0.1, -0.2, 0.0),
    ),
)

# Boxes that make up Hero: (center, size). Overlaps are fused by the voxel remesh.
_HERO_BOXES: tuple[tuple[tuple[float, float, float], tuple[float, float, float]], ...] = (
    ((0.0, 0.0, 1.2), (0.36, 0.2, 0.6)),  # torso
    ((0.0, 0.0, 0.98), (0.3, 0.2, 0.16)),  # hips
    ((0.0, 0.0, 1.48), (0.1, 0.1, 0.1)),  # neck
    ((0.575, 0.0, 1.45), (0.75, 0.1, 0.1)),  # left arm
    ((-0.575, 0.0, 1.45), (0.75, 0.1, 0.1)),  # right arm
    ((0.1, 0.0, 0.725), (0.14, 0.14, 0.45)),  # left thigh
    ((-0.1, 0.0, 0.725), (0.14, 0.14, 0.45)),  # right thigh
    ((0.1, 0.0, 0.29), (0.12, 0.12, 0.42)),  # left calf
    ((-0.1, 0.0, 0.29), (0.12, 0.12, 0.42)),  # right calf
    ((0.1, -0.08, 0.05), (0.1, 0.3, 0.1)),  # left foot
    ((-0.1, -0.08, 0.05), (0.1, 0.3, 0.1)),  # right foot
)
_HEAD_CENTER = (0.0, 0.0, 1.65)
_HEAD_RADIUS = 0.12
_VOXEL_SIZE = 0.02


def reset_scene() -> None:
    """Remove every object, collection, mesh, material, image, and action."""
    import bpy  # noqa: PLC0415

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for armature in list(bpy.data.armatures):
        bpy.data.armatures.remove(armature)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def build_hero() -> dict[str, list[float]]:
    """Build collection Hero with mesh SM_Hero and return its landmarks."""
    import bmesh  # noqa: PLC0415
    import bpy  # noqa: PLC0415

    bm = bmesh.new()
    for center, size in _HERO_BOXES:
        _add_box(bm, center, size)
    head = bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=12, radius=_HEAD_RADIUS)
    bmesh.ops.translate(bm, vec=_HEAD_CENTER, verts=head["verts"])
    mesh = bpy.data.meshes.new("SM_Hero")
    bm.to_mesh(mesh)
    bm.free()

    collection = bpy.data.collections.new("Hero")
    bpy.context.scene.collection.children.link(collection)
    obj = bpy.data.objects.new("SM_Hero", mesh)
    collection.objects.link(obj)
    _select_only([obj])
    mesh.remesh_voxel_size = _VOXEL_SIZE
    bpy.ops.object.voxel_remesh()
    return {key: list(value) for key, value in HERO_LANDMARKS.items()}


def build_library(library_dir: Path) -> Path:
    """Build a Mixamo-named source, export Idle (FBX) and Walk (BVH), and write library.json."""
    import bpy  # noqa: PLC0415

    library_dir.mkdir(parents=True, exist_ok=True)
    source = _build_mixamo_source()
    scene = bpy.context.scene

    idle = bpy.data.actions.new("Idle")
    source.animation_data_create().action = idle
    _key_leg_and_spine(source, "Idle", frames=(1, 15, 30))
    scene.frame_start, scene.frame_end = 1, 30
    _select_only([source])
    bpy.ops.export_scene.fbx(
        filepath=str(library_dir / "idle.fbx"),
        use_selection=True,
        object_types={"ARMATURE"},
        bake_anim=True,
        bake_anim_use_all_actions=False,
        bake_anim_use_nla_strips=False,
        bake_anim_force_startend_keying=True,
        add_leaf_bones=False,
    )

    walk = bpy.data.actions.new("Walk")
    source.animation_data.action = walk
    _key_leg_and_spine(source, "Walk", frames=(1, 20, 40))
    scene.frame_start, scene.frame_end = 1, 40
    _select_only([source])
    bpy.ops.export_anim.bvh(filepath=str(library_dir / "walk.bvh"), frame_start=1, frame_end=40)

    manifest: dict[str, Any] = {
        "name": "fixture-lib",
        "skeleton": "mixamo",
        "clips": [
            {"name": "Idle", "file": "idle.fbx", "frame_start": 1, "frame_end": 30},
            {"name": "Walk", "file": "walk.bvh"},
        ],
    }
    (library_dir / "library.json").write_text(json.dumps(manifest, indent=2) + "\n")

    source.animation_data.action = None
    _remove_object(source)
    bpy.data.actions.remove(idle)
    bpy.data.actions.remove(walk)
    return library_dir


def _build_mixamo_source() -> Any:
    import bpy  # noqa: PLC0415

    data = bpy.data.armatures.new("Mixamo")
    armature = bpy.data.objects.new("Mixamo", data)
    bpy.context.scene.collection.objects.link(armature)
    _select_only([armature])
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        for name, parent, head, tail in _MIXAMO_BONES:
            bone = data.edit_bones.new(name)
            bone.head = head
            bone.tail = tail
            if parent is not None:
                bone.parent = data.edit_bones[parent]
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def _key_leg_and_spine(armature: Any, clip: str, frames: tuple[int, int, int]) -> None:
    """Key the swing of both thighs and a small spine bend so the clip has real motion."""
    swing = 0.45 if clip == "Walk" else 0.0
    spine = 0.06 if clip == "Idle" else 0.0
    for frame, sign in zip(frames, (1.0, -1.0, 1.0), strict=True):
        for bone, direction in (("mixamorig:LeftUpLeg", 1.0), ("mixamorig:RightUpLeg", -1.0)):
            pose_bone = armature.pose.bones[bone]
            pose_bone.rotation_mode = "XYZ"
            pose_bone.rotation_euler = (swing * sign * direction, 0.0, 0.0)
            pose_bone.keyframe_insert("rotation_euler", frame=frame)
        spine_bone = armature.pose.bones["mixamorig:Spine1"]
        spine_bone.rotation_mode = "XYZ"
        spine_bone.rotation_euler = (spine * math.sin(sign * math.pi / 2), 0.0, 0.0)
        spine_bone.keyframe_insert("rotation_euler", frame=frame)


def _add_box(bm: Any, center: tuple[float, float, float], size: tuple[float, float, float]) -> None:
    import bmesh  # noqa: PLC0415

    cube = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=cube["verts"])
    bmesh.ops.translate(bm, vec=center, verts=cube["verts"])


def _select_only(objects: list[Any]) -> None:
    import bpy  # noqa: PLC0415

    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def add_baked_hero_material() -> None:
    """Give SM_Hero a UV map and a baked surface, M_Hero_Body, with T_Hero_Body_{BC,N,ORM} images.

    The variant and re-import checks need a UV map, a baked material, and each texture the
    material names, so the fixture supplies all of them.
    """
    import bpy  # noqa: PLC0415

    mesh = bpy.data.objects["SM_Hero"].data
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for loop in mesh.loops:
        co = mesh.vertices[loop.vertex_index].co
        uv_layer.data[loop.index].uv = ((co.x + 1.0) / 2.0, (co.z + 0.5) / 2.0)

    for image in list(bpy.data.images):
        if image.name.startswith("T_Hero_Body_"):
            bpy.data.images.remove(image)
    material = bpy.data.materials.new("M_Hero_Body")
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"

    def texture(suffix: str, colorspace: str) -> Any:
        image = bpy.data.images.new(f"T_Hero_Body_{suffix}", 64, 64)
        image.colorspace_settings.name = colorspace
        node = nodes.new("ShaderNodeTexImage")
        node.image = image
        links.new(uv.outputs["UV"], node.inputs["Vector"])
        return node

    base = texture("BC", "sRGB")
    normal = texture("N", "Non-Color")
    orm = texture("ORM", "Non-Color")
    normal_map = nodes.new("ShaderNodeNormalMap")
    split = nodes.new("ShaderNodeSeparateColor")
    links.new(base.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(normal.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(orm.outputs["Color"], split.inputs["Color"])
    links.new(split.outputs["Green"], bsdf.inputs["Roughness"])
    links.new(split.outputs["Blue"], bsdf.inputs["Metallic"])
    mesh.materials.append(material)


def _remove_object(obj: Any) -> None:
    import bpy  # noqa: PLC0415

    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if data is not None and data.users == 0:
        bpy.data.armatures.remove(data)
