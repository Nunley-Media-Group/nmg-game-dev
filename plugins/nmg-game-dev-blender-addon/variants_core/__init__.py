"""Variant core: Desktop cleanup, Mobile decimation with LODs, and FBX and sidecar export.

The operators and the finalize pipeline call these functions directly. Every failure is
raised as VariantError with a stable code, message, and remediation, before any file is
written.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import bpy

from ..utils.budgets import BudgetOverrideError, resolve_budget
from .assets import desktop_export_objects, distinct_materials, require_export_root, validate_inputs
from .cleanup import cleanup_desktop
from .errors import VariantError
from .export import export_variants
from .mobile import build_mobile
from .sidecars import write_sidecars
from .textures import max_texture_px, source_images

__all__ = [
    "VariantError",
    "cleanup_desktop",
    "generate_variants",
    "optimize_mobile",
]


def optimize_mobile(
    collection_name: str,
    asset_class: str = "standard_prop",
    budgets_path: str | None = None,
) -> dict[str, Any]:
    """Rebuild the Mobile variant in <Name>_Mobile and return its report."""
    budget = _budget(asset_class, budgets_path)
    validate_inputs(collection_name, budget)
    return build_mobile(collection_name, budget)


def generate_variants(
    collection_name: str,
    category: str,
    asset_class: str,
    export_root: str,
    budgets_path: str | None = None,
) -> dict[str, Any]:
    """Cleanup, Mobile build, export, and sidecars for one asset. Returns the result dict."""
    budget = _budget(asset_class, budgets_path)
    require_export_root(export_root)
    validate_inputs(collection_name, budget)

    desktop_objects = desktop_export_objects(bpy.data.collections[collection_name])
    desktop_materials = distinct_materials(desktop_objects)
    desktop_px = max_texture_px(list(source_images(desktop_materials).values()))

    cleanup = cleanup_desktop(collection_name)
    mobile = build_mobile(collection_name, budget)
    exported = export_variants(collection_name, category, export_root)

    payload: dict[str, Any] = {
        "name": collection_name,
        "category": category,
        "class": asset_class,
        "budget": budget,
        "desktop": {
            "fbx": f"Desktop/SM_{collection_name}.fbx",
            "tris": cleanup["tris_after"],
            "texture_bytes": exported["desktop_texture_bytes"],
            "max_texture_px": desktop_px,
            "materials": len(desktop_materials),
        },
        "mobile": {
            "fbx": f"Mobile/SM_{collection_name}.fbx",
            "tris": mobile["tris"],
            "lod_tris": mobile["lod_tris"],
            "lod_levels": mobile["lod_levels"],
            "texture_bytes": exported["mobile_texture_bytes"],
            "max_texture_px": mobile["max_texture_px"],
            "materials": mobile["materials"],
        },
    }
    write_sidecars(Path(export_root) / category / collection_name, payload)

    return {
        **payload,
        "desktop_path": str(exported["desktop_fbx"]),
        "mobile_path": str(exported["mobile_fbx"]),
        "poly_count_desktop": cleanup["tris_after"],
        "poly_count_mobile": mobile["tris"],
        "texture_bytes_desktop": exported["desktop_texture_bytes"],
        "texture_bytes_mobile": exported["mobile_texture_bytes"],
    }


def _budget(asset_class: str, budgets_path: str | None) -> dict[str, int]:
    try:
        return resolve_budget(asset_class, budgets_path or None)
    except BudgetOverrideError as error:
        raise VariantError(error.code, error.message, error.remediation) from error
