"""Rigged GLB, material PNGs, and nmg-animations.json for one SK_<Name> rig (touches Blender)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import bpy

from ..variants_core.export import RIG_GLB_OPTIONS, glb_name
from ..variants_core.textures import source_images, write_png
from .outcome import STATUS_FALLBACK, RigError, fail, ok
from .skeleton import MANNY_BONE_NAMES

SIDECAR_NAME = "nmg-animations.json"
_EXPORT_ARMATURE_NAME = "Armature"
_PROVENANCE_KEY = "nmg_animations"
# The variant export's skeleton settings plus every clip the rig can play, each sampled per frame.
_GLB_OPTIONS: dict[str, Any] = {
    **RIG_GLB_OPTIONS,
    "export_animations": True,
    "export_animation_mode": "ACTIONS",
    "export_force_sampling": True,
    "export_optimize_animation_size": False,
}


def export_rigged(collection_name: str, out_dir: str) -> dict[str, Any]:
    """Write <Name>.glb, its material PNGs, and nmg-animations.json into out_dir."""
    armature = bpy.data.objects.get(f"SK_{collection_name}")
    collection = bpy.data.collections.get(collection_name)
    if armature is None or armature.type != "ARMATURE" or collection is None:
        return fail(
            STATUS_FALLBACK,
            "export.rig_missing",
            f"SK_{collection_name} does not exist.",
            f"Run rig_humanoid for collection {collection_name} before exporting.",
        )
    try:
        return _write(collection, armature, Path(out_dir))
    except RigError as error:
        return error.result


def _write(
    collection: bpy.types.Collection, armature: bpy.types.Object, out_dir: Path
) -> dict[str, Any]:
    clash = bpy.data.objects.get(_EXPORT_ARMATURE_NAME)
    if clash is not None and clash is not armature:
        raise RigError(
            STATUS_FALLBACK,
            "export.name_taken",
            f"An object named '{_EXPORT_ARMATURE_NAME}' already exists, so the armature "
            "cannot be renamed for export.",
            "Rename or delete the object named Armature, then rerun.",
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    meshes = sorted(
        (obj for obj in collection.objects if obj.type == "MESH"), key=lambda obj: obj.name
    )
    textures = _write_textures(meshes, out_dir)

    glb_path = out_dir / glb_name(collection.name)
    original_name = armature.name
    armature.name = _EXPORT_ARMATURE_NAME
    try:
        _select_only([armature, *meshes], armature)
        bpy.ops.export_scene.gltf(filepath=str(glb_path), **_GLB_OPTIONS)
    finally:
        armature.name = original_name

    clips = json.loads(armature.get(_PROVENANCE_KEY, "{}"))
    sidecar_path = out_dir / SIDECAR_NAME
    sidecar = {
        "asset": collection.name,
        "armature": armature.name,
        "skeleton": "humanoid",
        "glb": glb_path.name,
        "bones": list(MANNY_BONE_NAMES),
        "clips": [clips[name] for name in sorted(clips)],
    }
    sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ok(
        asset=collection.name,
        armature=armature.name,
        glb=str(glb_path),
        sidecar=str(sidecar_path),
        textures=[str(path) for path in textures],
        clips=sorted(clips),
    )


def _write_textures(meshes: list[bpy.types.Object], out_dir: Path) -> list[Path]:
    """Save each image used by the meshes' materials as a PNG under its own name."""
    materials = [slot.material for mesh in meshes for slot in mesh.material_slots if slot.material]
    images = sorted(source_images(materials).values(), key=lambda image: image.name)
    originals = [(image, image.filepath_raw, image.file_format) for image in images]
    paths: list[Path] = []
    try:
        for image in images:
            path = out_dir / f"{image.name}.png"
            write_png(image, path)
            paths.append(path)
    finally:
        for image, filepath, file_format in originals:
            image.filepath_raw = filepath
            image.file_format = file_format
    return paths


def _select_only(objects: list[bpy.types.Object], active: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active
