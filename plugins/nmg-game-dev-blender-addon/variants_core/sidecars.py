"""Sidecar JSON written next to the exported variants (metrics for the quality gates)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_sidecars(variant_root: Path, payload: dict[str, Any]) -> None:
    """Write nmg-variants.json and Mobile/nmg-asset.json. Keys are sorted for determinism."""
    variant_root.mkdir(parents=True, exist_ok=True)
    (variant_root / "Mobile").mkdir(parents=True, exist_ok=True)
    _write_json(variant_root / "nmg-variants.json", payload)

    mobile = payload["mobile"]
    asset = {
        "class": payload["class"],
        "tris": mobile["tris"],
        "max_texture_px": mobile["max_texture_px"],
        "materials": mobile["materials"],
    }
    _write_json(variant_root / "Mobile" / "nmg-asset.json", asset)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
