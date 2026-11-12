"""estimate_landmarks: propose rig_humanoid landmarks from SM_<Name>, without editing the scene.

The wrapper reads world-space evaluated vertices of every mesh in the collection and hands them
to the pure-Python slicing core. It changes no object, mesh data, transform, selection, active
object, or mode. view_layer.update() only re-evaluates the depsgraph.
"""

from __future__ import annotations

from typing import Any

import bpy

from .landmarks import asset_not_found
from .outcome import RigError, ok
from .skeleton import Vec3
from .slicing import propose


def estimate_landmarks(collection_name: str) -> dict[str, Any]:
    """Return ok with landmarks, confidence, and warnings, or the failure from the slicing core."""
    collection = bpy.data.collections.get(collection_name)
    root = bpy.data.objects.get(f"SM_{collection_name}")
    if (
        collection is None
        or root is None
        or root.type != "MESH"
        or root.name not in collection.objects
    ):
        return asset_not_found(collection_name)

    try:
        proposal = propose(_world_vertices(collection))
    except RigError as error:
        return error.result
    return ok(
        asset=collection_name,
        landmarks=proposal["landmarks"],
        confidence=proposal["confidence"],
        warnings=proposal["warnings"],
    )


def _world_vertices(collection: bpy.types.Collection) -> list[Vec3]:
    """Every vertex of every mesh in the collection, in world space, with modifiers applied."""
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points: list[Vec3] = []
    for obj in sorted(collection.objects, key=lambda item: item.name):
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            matrix = obj.matrix_world
            for vertex in mesh.vertices:
                world = matrix @ vertex.co
                points.append((float(world.x), float(world.y), float(world.z)))
        finally:
            evaluated.to_mesh_clear()
    return points
