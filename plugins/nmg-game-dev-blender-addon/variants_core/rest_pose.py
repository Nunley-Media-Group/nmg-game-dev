"""Evaluate rigged meshes in their rest pose, so a leftover pose never reaches a measure.

A skinned mesh deforms to its rig's current pose. With no action assigned, that pose is whatever the
pose bones hold, so validation, reduction, and export would read deformed geometry (#236).
rest_pose sets each armature that deforms the given objects to REST for the duration of a block and
restores each previous pose_position on exit, also on error. It never writes pose-bone transforms or
the action assignment, so the scene's pose is left as it was found.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager

import bpy


def deforming_armatures(objects: Iterable[bpy.types.Object]) -> list[bpy.types.Object]:
    """The armatures that deform objects: named by each Armature modifier, plus an ARMATURE parent.

    Each armature appears once, in first-seen order.
    """
    found: list[bpy.types.Object] = []
    seen: set[int] = set()
    for obj in objects:
        candidates = [modifier.object for modifier in obj.modifiers if modifier.type == "ARMATURE"]
        if obj.parent is not None:
            candidates.append(obj.parent)
        for armature in candidates:
            if armature is None or armature.type != "ARMATURE":
                continue
            key = armature.as_pointer()
            if key not in seen:
                seen.add(key)
                found.append(armature)
    return found


@contextmanager
def rest_pose(objects: Iterable[bpy.types.Object]) -> Iterator[None]:
    """Put every armature that deforms objects into REST for the block, then restore each one.

    With no deforming armature this changes nothing. The view layer is updated on entry and exit,
    so bounds and evaluated meshes read inside the block are at rest.
    """
    armatures = deforming_armatures(objects)
    saved = [(armature.data, armature.data.pose_position) for armature in armatures]
    try:
        for data, _position in saved:
            data.pose_position = "REST"
        if armatures:
            bpy.context.view_layer.update()
        yield
    finally:
        for data, position in saved:
            data.pose_position = position
        if armatures:
            bpy.context.view_layer.update()
