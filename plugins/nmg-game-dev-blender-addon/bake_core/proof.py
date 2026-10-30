"""Pre-bake and post-bake three-quarter renders, and the comparison that gates the bake.

The renders run in a temporary scene that links the asset collection, with one camera and one
rig, on a transparent film so the asset's alpha marks the pixels to compare. The scene is removed
afterward. Framing comes from the pre-bake geometry, so both renders use the same camera.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import bpy
import numpy as np
from mathutils import Vector

PROOF_SCENE = "__nmg_bake_proof"
RESOLUTION = 512
SAMPLES = 16
FOCAL_MM = 50.0
SENSOR_MM = 36.0
ELEVATION = math.radians(20.0)
MARGIN = 1.10
MEAN_TOLERANCE = 0.03
OUTLIER_TOLERANCE = 0.02
OUTLIER_DELTA = 0.25
_DIRECTION = Vector((1.0, -1.0, 0.0)).normalized()
_SUNS = (
    (math.radians(50.0), 0.0, math.radians(35.0)),
    (math.radians(60.0), 0.0, math.radians(-120.0)),
    (math.radians(30.0), 0.0, math.radians(160.0)),
)


def frame_for(collection: bpy.types.Collection) -> tuple[Vector, float]:
    """Center and camera distance that fit the mesh bounding sphere with a margin."""
    corners: list[Vector] = []
    for obj in collection.all_objects:
        if obj.type == "MESH":
            corners += [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    low = Vector(tuple(min(corner[axis] for corner in corners) for axis in range(3)))
    high = Vector(tuple(max(corner[axis] for corner in corners) for axis in range(3)))
    radius = (high - low).length / 2
    half_fov = math.atan((SENSOR_MM / 2) / FOCAL_MM)
    return (low + high) / 2, radius * MARGIN / math.sin(half_fov)


def render_three_quarter(
    collection: bpy.types.Collection,
    path: Path,
    frame: tuple[Vector, float],
) -> None:
    """Render the collection's three-quarter view to path on a transparent film."""
    scene = bpy.data.scenes.new(PROOF_SCENE)
    helpers: list[bpy.types.ID] = []
    world = bpy.data.worlds.new(f"{PROOF_SCENE}_world")
    world.color = (0.5, 0.5, 0.5)
    try:
        scene.collection.children.link(collection)
        scene.world = world
        for index, rotation in enumerate(_SUNS):
            light_data = bpy.data.lights.new(f"{PROOF_SCENE}_sun_{index}", type="SUN")
            light_data.energy = 3.0
            light = bpy.data.objects.new(light_data.name, light_data)
            light.rotation_euler = rotation
            scene.collection.objects.link(light)
            helpers.append(light)
        camera_data = bpy.data.cameras.new(f"{PROOF_SCENE}_camera")
        camera_data.lens = FOCAL_MM
        camera_data.sensor_width = SENSOR_MM
        camera = bpy.data.objects.new(f"{PROOF_SCENE}_camera", camera_data)
        scene.collection.objects.link(camera)
        scene.camera = camera
        helpers.append(camera)
        _place_camera(camera, frame)
        _set_render(scene, path)
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            bpy.ops.render.render(write_still=True)
        if not path.is_file():
            raise RuntimeError(f"Blender did not write the proof render {path}")
    finally:
        _teardown(scene, helpers, world)


def compare(pre_bake: Path, baked: Path) -> dict[str, float]:
    """Mean absolute RGB difference and outlier ratio over the asset's pixels (alpha > 0.5)."""
    before = _load(pre_bake)
    after = _load(baked)
    mask = (before[..., 3] > 0.5) | (after[..., 3] > 0.5)
    if not mask.any():
        return {"mean_abs_diff": 0.0, "outlier_ratio": 0.0}
    diff = np.abs(before[..., :3] - after[..., :3])
    mean = float(diff[mask].mean())
    outlier = float((diff[mask].max(axis=-1) > OUTLIER_DELTA).mean())
    return {"mean_abs_diff": mean, "outlier_ratio": outlier}


def within_tolerance(metrics: dict[str, float]) -> bool:
    return (
        metrics["mean_abs_diff"] <= MEAN_TOLERANCE and metrics["outlier_ratio"] <= OUTLIER_TOLERANCE
    )


def _load(path: Path) -> np.ndarray:
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        width, height = image.size
        flat = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(flat)
        return flat.reshape(height, width, 4)
    finally:
        bpy.data.images.remove(image)


def _place_camera(camera: bpy.types.Object, frame: tuple[Vector, float]) -> None:
    center, distance = frame
    offset = _DIRECTION * math.cos(ELEVATION) + Vector((0.0, 0.0, math.sin(ELEVATION)))
    camera.location = center + offset * distance
    camera.rotation_mode = "QUATERNION"
    camera.rotation_quaternion = (center - camera.location).to_track_quat("-Z", "Y")
    camera.data.clip_end = max(100.0, distance * 4.0)


def _set_render(scene: bpy.types.Scene, path: Path) -> None:
    scene.render.engine = _eevee_identifier()
    scene.render.resolution_x = RESOLUTION
    scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.render.filepath = str(path)
    scene.view_settings.view_transform = "Standard"
    scene.eevee.taa_render_samples = SAMPLES


def _eevee_identifier() -> str:
    items = bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
    matches = [item.identifier for item in items if item.identifier.startswith("BLENDER_EEVEE")]
    if not matches:
        raise RuntimeError("This Blender build has no EEVEE render engine for the bake proof.")
    return matches[-1]


def _teardown(scene: bpy.types.Scene, helpers: list[bpy.types.ID], world: Any) -> None:
    scene.camera = None
    for item in helpers:
        if isinstance(item, bpy.types.Object):
            data = item.data
            bpy.data.objects.remove(item)
            if isinstance(data, bpy.types.Light):
                bpy.data.lights.remove(data)
            elif isinstance(data, bpy.types.Camera):
                bpy.data.cameras.remove(data)
    scene.world = None
    bpy.data.scenes.remove(scene)
    bpy.data.worlds.remove(world)
