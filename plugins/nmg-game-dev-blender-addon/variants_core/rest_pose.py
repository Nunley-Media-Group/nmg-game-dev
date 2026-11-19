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

    With no deforming armature this changes nothing. Armature data that cannot be written, such as
    library-linked data, is skipped and left as it is. Only the armatures set to REST are restored,
    so the restore never fails over an error raised inside the block. The view layer is updated on
    entry and exit, so bounds and evaluated meshes read inside the block are at rest.
    """
    saved: list[tuple[bpy.types.Armature, str]] = []
    try:
        for armature in deforming_armatures(objects):
            data = armature.data
            position = data.pose_position
            try:
                data.pose_position = "REST"
            except (AttributeError, TypeError):
                # Library-linked armature data is read-only: it keeps its pose, as before #236.
                continue
            saved.append((data, position))
        if saved:
            bpy.context.view_layer.update()
        yield
    finally:
        for data, position in saved:
            data.pose_position = position
        if saved:
            bpy.context.view_layer.update()
