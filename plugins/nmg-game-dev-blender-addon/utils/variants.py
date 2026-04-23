from __future__ import annotations

from pathlib import Path
from typing import Literal


def resolve_variant_path(parent: Path, variant: Literal["Desktop", "Mobile"]) -> Path:
    if variant not in ("Desktop", "Mobile"):
        raise ValueError(f"Invalid variant '{variant}'. Must be 'Desktop' or 'Mobile'.")
    return parent / variant
