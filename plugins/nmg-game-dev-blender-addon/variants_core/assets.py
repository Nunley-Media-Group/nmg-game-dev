"""Asset lookup and up-front validation shared by every variant entry point."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

import bpy

from .errors import VariantError
from .textures import check_baked_material

#: The armature's name inside every rigged FBX. Export renames SK_<Name> to this and restores it.
ARMATURE_EXPORT_NAME: Final = "Armature"


def mobile_collection_name(name: str) -> str:
    return f"{name}_Mobile"


def asset_armature(name: str) -> bpy.types.Object | None:
    """Return SK_<Name> when it is an ARMATURE in collection <Name>, else None (unrigged)."""
    collection = bpy.data.collections.get(name)
    if collection is None:
        return None
    rig = collection.objects.get(f"SK_{name}")
    if rig is None or rig.type != "ARMATURE":
        return None
    return rig


def require_armature_name_free(rig: bpy.types.Object | None) -> None:
    """Raise before any write if an object other than the rig already holds the export name."""
    if rig is None:
        return
    clash = bpy.data.objects.get(ARMATURE_EXPORT_NAME)
    if clash is not None and clash != rig:
        raise VariantError(
            "variants.armature_name_taken",
            f"An object named '{ARMATURE_EXPORT_NAME}' already exists, so {rig.name} cannot be "
            "renamed for export.",
            f"Rename or delete the object named {ARMATURE_EXPORT_NAME}, then rerun.",
        )


def require_asset(name: str) -> tuple[bpy.types.Collection, bpy.types.Object]:
    """Return the asset collection and its root mesh SM_<Name>, or raise asset_not_found."""
    collection = bpy.data.collections.get(name)
    root = collection.objects.get(f"SM_{name}") if collection is not None else None
    if collection is None or root is None or root.type != "MESH":
        raise VariantError(
            "variants.asset_not_found",
            f"No collection '{name}' with a root mesh 'SM_{name}' was found.",
            f"Create or select the asset collection '{name}' with a mesh named SM_{name} "
            "(contract section 1), then rerun.",
        )
    return collection, root


def asset_meshes(collection: bpy.types.Collection) -> list[bpy.types.Object]:
    return sorted(
        (obj for obj in collection.all_objects if obj.type == "MESH"),
        key=lambda obj: obj.name,
    )


def desktop_export_objects(collection: bpy.types.Collection) -> list[bpy.types.Object]:
    return sorted(
        (obj for obj in collection.all_objects if obj.type in {"MESH", "ARMATURE"}),
        key=lambda obj: obj.name,
    )


def distinct_materials(objects: list[bpy.types.Object]) -> list[bpy.types.Material]:
    unique: dict[str, bpy.types.Material] = {}
    for obj in objects:
        for slot in obj.material_slots:
            if slot.material is not None:
                unique[slot.material.name] = slot.material
    return [unique[key] for key in sorted(unique)]


def validate_inputs(name: str, budget: Mapping[str, int]) -> None:
    """Raise before any mutation if the asset cannot become Desktop and Mobile variants."""
    collection, _root = require_asset(name)
    materials = distinct_materials(asset_meshes(collection))
    for material in materials:
        check_baked_material(material)
    if len(materials) > budget["materials"]:
        raise VariantError(
            "variants.mobile_material_limit",
            f"'{name}' uses {len(materials)} materials; the Mobile limit for this class "
            f"is {budget['materials']}.",
            "Merge the materials into one baked material with the bake step (#67), or "
            "choose an asset class with a higher Mobile material limit.",
        )


def require_export_root(export_root: str) -> None:
    if not export_root.strip():
        raise VariantError(
            "variants.export_root_missing",
            "No export root was given, so the FBX and sidecar paths are undefined.",
            "Set export_root to the directory that holds <Category>/<Name>/ exports.",
        )
