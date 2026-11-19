"""GLB and PNG export for both variants, with identical object, material, and texture names.

Each variant folder gets ``<Name>.glb`` and the baked ``T_<Name>_<Part>_{BC,N,ORM}.png`` set. The
export also measures every exported mesh the way the engine import will see it (triangles,
surfaces, and bounds in engine axes), so the import step can verify the result.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import bpy
from mathutils import Vector

from .assets import (
    ARMATURE_EXPORT_NAME,
    asset_armature,
    desktop_export_objects,
    distinct_materials,
    mobile_collection_name,
    require_armature_name_free,
)
from .meshes import evaluated_mesh
from .rest_pose import rest_pose
from .textures import source_images, write_png

_TEMP_PREFIX = "__nmg_tmp_"
_MOBILE_SUFFIX = "_Mobile"
#: Rounding for the recorded bounds, in metres.
BOUNDS_DECIMALS: Final = 6

#: Shared by every GLB the add-on writes: binary glTF, +Y up, modifiers applied, selection only.
GLB_OPTIONS: Final[dict[str, Any]] = {
    "export_format": "GLB",
    "export_yup": True,
    "export_apply": True,
    "use_selection": True,
}
#: A static variant carries no skin and no animation.
STATIC_GLB_OPTIONS: Final[dict[str, Any]] = {
    **GLB_OPTIONS,
    "export_skins": False,
    "export_animations": False,
}
#: A rigged variant carries the deform skeleton and its skin, but no clips: each clip is its own
#: file (finalize_core.anims).
RIG_GLB_OPTIONS: Final[dict[str, Any]] = {
    **GLB_OPTIONS,
    "export_skins": True,
    "export_def_bones": True,
    "export_leaf_bone": False,
    "export_animations": False,
}


def glb_name(collection_name: str) -> str:
    """The file name of an asset's variant GLB: ``<Name>.glb``."""
    return f"{collection_name}.glb"


def export_variants(collection_name: str, category: str, export_root: str) -> dict[str, Any]:
    """Write Desktop and Mobile ``<Name>.glb`` plus PNG textures; return paths and measurements.

    A rigged asset (SK_<Name> in its collection) exports skinned: the armature is named Armature
    for the export. The result holds ``desktop_glb``, ``mobile_glb``, ``rigged``, each variant's
    ``*_texture_bytes``, and ``meshes`` (``{"Desktop": [...], "Mobile": [...]}``, see
    :func:`mesh_records`).
    """
    rig = asset_armature(collection_name)
    require_armature_name_free(rig)
    variant_root = Path(export_root) / category / collection_name
    desktop_dir = variant_root / "Desktop"
    mobile_dir = variant_root / "Mobile"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    mobile_dir.mkdir(parents=True, exist_ok=True)

    desktop_objects = desktop_export_objects(bpy.data.collections[collection_name])
    mobile_collection = bpy.data.collections[mobile_collection_name(collection_name)]
    mobile_objects = sorted(mobile_collection.all_objects, key=lambda obj: obj.name)
    mobile_export = [rig, *mobile_objects] if rig is not None else mobile_objects
    desktop_materials = distinct_materials(desktop_objects)
    mobile_materials = distinct_materials(mobile_objects)
    desktop_images = _images_of(desktop_materials)
    mobile_images = _images_of(mobile_materials)

    desktop_glb = desktop_dir / glb_name(collection_name)
    mobile_glb = mobile_dir / glb_name(collection_name)
    options = RIG_GLB_OPTIONS if rig is not None else STATIC_GLB_OPTIONS
    original_paths = {img.name: (img.filepath_raw, img.file_format) for img in desktop_images}
    restores: list[tuple[bpy.types.ID, str]] = []
    try:
        # Both measures and both GLBs read the rest shape, so no leftover pose is exported (#236).
        with rest_pose(desktop_objects + mobile_objects):
            if rig is not None:
                restores.append((rig, rig.name))
                rig.name = ARMATURE_EXPORT_NAME
            desktop_bytes = sum(
                write_png(image, desktop_dir / f"{image.name}.png") for image in desktop_images
            )
            restores += _name_meshes(desktop_objects)
            desktop_meshes = mesh_records(desktop_objects)
            _select_only(desktop_objects)
            bpy.ops.export_scene.gltf(filepath=str(desktop_glb), **options)

            # The rig keeps its export name, so both files name it the same way. Desktop mesh
            # datablocks move aside with their objects, so Mobile meshes can take the names they
            # export.
            desktop_mesh_data = [obj.data for obj in desktop_objects if obj.type == "MESH"]
            restores += _rename(
                [obj for obj in desktop_objects if obj != rig]
                + desktop_mesh_data
                + desktop_materials
                + desktop_images,
                _to_temp,
            )
            restores += _rename(mobile_objects + mobile_materials + mobile_images, _unsuffixed)
            restores += _name_meshes(mobile_objects)
            mobile_bytes = sum(
                write_png(image, mobile_dir / f"{image.name}.png") for image in mobile_images
            )
            mobile_meshes = mesh_records(mobile_objects)
            _select_only(mobile_export)
            bpy.ops.export_scene.gltf(filepath=str(mobile_glb), **options)
    finally:
        for datablock, original_name in reversed(restores):
            datablock.name = original_name
        for image in desktop_images:
            image.filepath_raw, image.file_format = original_paths[image.name]

    return {
        "desktop_glb": desktop_glb,
        "mobile_glb": mobile_glb,
        "rigged": rig is not None,
        "desktop_texture_bytes": desktop_bytes,
        "mobile_texture_bytes": mobile_bytes,
        "meshes": {"Desktop": desktop_meshes, "Mobile": mobile_meshes},
    }


def mesh_records(objects: list[bpy.types.Object]) -> list[dict[str, Any]]:
    """Describe each exported mesh object as the engine import will see it, sorted by name.

    Each record is ``{name, tris, material_slots, bounds: {min, max}}``. ``name`` is the object's
    current (export) name, which the GLB writes as the node name. ``tris`` counts the triangles of
    the evaluated mesh, and ``material_slots`` counts the material slots its faces use (one GLB
    primitive each). ``bounds`` is the world-space box of the vertices in engine axes: Blender
    ``(x, y, z)`` becomes ``(x, z, -y)``, in metres. A skinned mesh is measured at its rest shape,
    which is what the GLB stores.
    """
    records = [_mesh_record(obj) for obj in objects if obj.type == "MESH" and obj.data is not None]
    return sorted(records, key=lambda record: str(record["name"]))


def engine_bounds(points: list[Vector]) -> dict[str, list[float]]:
    """The axis-aligned box of Blender-space points, in engine axes ``(x, z, -y)``."""
    if not points:
        return {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0]}
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    zs = [point.z for point in points]
    low = [min(xs), min(zs), -max(ys)]
    high = [max(xs), max(zs), -min(ys)]
    return {"min": [_round(value) for value in low], "max": [_round(value) for value in high]}


def _mesh_record(obj: bpy.types.Object) -> dict[str, Any]:
    mesh = _export_shape(obj)
    try:
        mesh.calc_loop_triangles()
        used = {polygon.material_index for polygon in mesh.polygons}
        world = obj.matrix_world
        return {
            "name": obj.name,
            "tris": len(mesh.loop_triangles),
            "material_slots": len(used),
            "bounds": engine_bounds([world @ vertex.co for vertex in mesh.vertices]),
        }
    finally:
        bpy.data.meshes.remove(mesh)


def _export_shape(obj: bpy.types.Object) -> bpy.types.Mesh:
    """A temporary copy of the mesh the GLB writes: modifiers applied, skin left at rest."""
    skins = [modifier for modifier in obj.modifiers if modifier.type == "ARMATURE"]
    states = [(modifier, modifier.show_viewport) for modifier in skins]
    try:
        for modifier in skins:
            modifier.show_viewport = False
        return evaluated_mesh(obj)
    finally:
        for modifier, shown in states:
            modifier.show_viewport = shown


def _round(value: float) -> float:
    rounded = round(float(value), BOUNDS_DECIMALS)
    return 0.0 if rounded == 0 else rounded


def _images_of(materials: list[bpy.types.Material]) -> list[bpy.types.Image]:
    return sorted(source_images(materials).values(), key=lambda image: image.name)


def _rename(
    datablocks: list[Any], new_name: Callable[[str], str]
) -> list[tuple[bpy.types.ID, str]]:
    originals = [(datablock, datablock.name) for datablock in datablocks]
    for datablock in datablocks:
        datablock.name = new_name(datablock.name)
    return originals


def _name_meshes(objects: list[bpy.types.Object]) -> list[tuple[bpy.types.ID, str]]:
    """Name each mesh datablock after its object, which already holds its export name (#142).

    The GLB writes both the node and the mesh name, so both carry the export name. A different
    mesh that already holds the name moves to a temporary name first, because Blender would suffix
    the new one. Returns the renamed datablocks with their original names, for the caller to
    restore.
    """
    originals: list[tuple[bpy.types.ID, str]] = []
    for obj in objects:
        if obj.type != "MESH" or obj.data.name == obj.name:
            continue
        holder = bpy.data.meshes.get(obj.name)
        if holder is not None:
            originals.append((holder, holder.name))
            holder.name = _to_temp(holder.name)
        originals.append((obj.data, obj.data.name))
        obj.data.name = obj.name
    return originals


def _to_temp(name: str) -> str:
    return f"{_TEMP_PREFIX}{name}"


def _unsuffixed(name: str) -> str:
    return name.replace(_MOBILE_SUFFIX, "", 1)


def _select_only(objects: list[bpy.types.Object]) -> None:
    view_layer = bpy.context.view_layer
    for obj in view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    view_layer.objects.active = objects[0] if objects else None
