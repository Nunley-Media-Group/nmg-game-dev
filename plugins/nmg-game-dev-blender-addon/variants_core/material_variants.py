"""Material-variant textures for the Desktop and Mobile export, and their sidecar lists (#148).

export runs after a passing pre-check. It first clears the variant PNGs an earlier run wrote, then
writes T_<Name>_<Part>_BC_<Variant>.png into both variant folders. Desktop copies the declared file,
which the pre-check sized to the Desktop base colour. Mobile scales a copy to the Mobile base colour
the same way the main textures are scaled (textures.mobile_image_copy).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import bpy

from ..contract_core.material_variants import png_size
from .textures import mobile_image_copy, write_png


def export_material_variants(
    collection: str,
    variant_root: Path,
    entries: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Write the variant textures and return the sidecar lists for Desktop and Mobile.

    entries are the validated report entries: name, material, base_color (the declared PNG path,
    or None) and parameters. A parameter-only variant writes no texture, and its sidecar entry has
    base_color None.
    """
    desktop_dir = variant_root / "Desktop"
    mobile_dir = variant_root / "Mobile"
    for folder in (desktop_dir, mobile_dir):
        # Clear the textures of variants that are no longer declared, so a removed variant leaves
        # no file behind in either folder.
        for stale in list(folder.glob(f"T_{collection}_*_BC_*.png")):
            stale.unlink()
    records: list[dict[str, Any]] = []
    for entry in entries:
        name = str(entry["name"])
        material = str(entry["material"])
        part = material.removeprefix(f"M_{collection}_")
        texture: str | None = None
        base_color = entry.get("base_color")
        if base_color:
            stem = f"T_{collection}_{part}_BC_{name}"
            _write_textures(collection, part, stem, Path(str(base_color)), desktop_dir, mobile_dir)
            texture = f"{stem}.png"
        records.append(
            {
                "name": name,
                "material": material,
                "base_color": texture,
                "parameters": dict(entry.get("parameters", {})),
                "material_instance": f"MI_{collection}_{part}_{name}",
            }
        )
    return {"desktop": records, "mobile": [dict(record) for record in records]}


def _write_textures(
    collection: str,
    part: str,
    stem: str,
    source: Path,
    desktop_dir: Path,
    mobile_dir: Path,
) -> None:
    """Write one declared base colour into both folders, sized to each folder's main base colour."""
    shutil.copyfile(source, desktop_dir / f"{stem}.png")
    mobile_main = png_size(mobile_dir / f"T_{collection}_{part}_BC.png")
    image = bpy.data.images.load(str(source), check_existing=False)
    try:
        target = mobile_main[0] if mobile_main is not None else max(image.size)
        scaled = mobile_image_copy(image, target)
        try:
            write_png(scaled, mobile_dir / f"{stem}.png")
        finally:
            bpy.data.images.remove(scaled)
    finally:
        bpy.data.images.remove(image)
