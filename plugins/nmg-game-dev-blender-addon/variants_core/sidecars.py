"""Sidecar JSON written next to the exported variants (metrics for the quality gates and import).

``<Category>/<Name>/nmg-variants.json`` describes both variants. Each variant folder also gets an
``nmg-asset.json`` that the mobile budget gate and the engine import check read.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

VARIANTS: Final[tuple[str, ...]] = ("Desktop", "Mobile")
ASSET_SIDECAR: Final = "nmg-asset.json"
VARIANTS_SIDECAR: Final = "nmg-variants.json"


def write_sidecars(variant_root: Path, payload: dict[str, Any]) -> dict[str, Path]:
    """Write nmg-variants.json and each variant's nmg-asset.json; return the nmg-asset.json paths.

    A mesh asset's nmg-asset.json is ``{class, tris, max_texture_px, materials, meshes}``, where
    ``meshes`` comes from the payload variant block's ``meshes`` and is left out of
    nmg-variants.json. A terrain's is ``{class, heightmap_px, layers, max_texture_px}``, with
    ``layers`` as a count. Keys are sorted for determinism.
    """
    variant_root.mkdir(parents=True, exist_ok=True)
    assets: dict[str, Path] = {}
    summary = dict(payload)
    for variant in VARIANTS:
        block = dict(payload[variant.lower()])
        meshes = block.pop("meshes", [])
        summary[variant.lower()] = block
        folder = variant_root / variant
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ASSET_SIDECAR
        _write_json(path, _asset(payload, block, meshes))
        assets[variant] = path
    _write_json(variant_root / VARIANTS_SIDECAR, summary)
    return assets


def _asset(
    payload: Mapping[str, Any], block: Mapping[str, Any], meshes: list[Any]
) -> dict[str, Any]:
    if payload.get("terrain"):
        # Terrain (#154): the mobile gate reads heightmap_px, the layer count, and texture size.
        return {
            "class": payload["class"],
            "heightmap_px": block["heightmap_px"],
            "layers": len(block["layers"]),
            "max_texture_px": block["max_texture_px"],
        }
    return {
        "class": payload["class"],
        "tris": block["tris"],
        "max_texture_px": block["max_texture_px"],
        "materials": block["materials"],
        "meshes": list(meshes),
    }


def mesh_payload(
    *,
    collection: str,
    category: str,
    asset_class: str,
    budget: Mapping[str, int],
    metrics: Mapping[str, Any],
    exported: Mapping[str, Any],
    material_variants: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The sidecar payload of a mesh asset from the variants metrics and the export result.

    ``metrics`` holds ``desktop`` and ``mobile`` blocks with ``tris``, ``max_texture_px``, and
    ``materials``. ``exported`` is :func:`variants_core.export.export_variants`'s result.
    """

    def block(variant: str) -> dict[str, Any]:
        source = metrics[variant.lower()]
        return {
            "glb": f"{variant}/{collection}.glb",
            "tris": source["tris"],
            "texture_bytes": exported[f"{variant.lower()}_texture_bytes"],
            "max_texture_px": source["max_texture_px"],
            "materials": source["materials"],
            "meshes": exported["meshes"][variant],
        }

    payload: dict[str, Any] = {
        "name": collection,
        "category": category,
        "class": asset_class,
        "budget": dict(budget),
        "rigged": bool(exported["rigged"]),
        "desktop": block("Desktop"),
        "mobile": block("Mobile"),
    }
    # The key exists only when the asset declares material variants (#148, AC4 and AC7).
    if material_variants is not None:
        payload["material_variants"] = dict(material_variants)
    return payload


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
