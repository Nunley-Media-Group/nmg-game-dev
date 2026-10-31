"""Side-by-side comparison sheet for ``both`` runs (#7 AC20).

Each image sits under a label strip that names its backend, seed, and generation time.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageDraw

LABEL_HEIGHT = 28
GUTTER = 12
SHEET_HEIGHT = 512


def compare(images: Sequence[Path], labels: Sequence[str], out_path: Path) -> Path:
    """Write ``images`` side by side, each under its label, to ``out_path`` and return it."""
    if len(images) != len(labels) or not images:
        raise ValueError("compare() needs one label per image and at least one image")
    tiles: list[PILImage.Image] = []
    for path in images:
        tile = PILImage.open(path).convert("RGB")
        scale = SHEET_HEIGHT / tile.height
        tiles.append(tile.resize((round(tile.width * scale), SHEET_HEIGHT)))
    width = sum(t.width for t in tiles) + GUTTER * (len(tiles) + 1)
    sheet = PILImage.new("RGB", (width, SHEET_HEIGHT + LABEL_HEIGHT + 2 * GUTTER), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    x = GUTTER
    for tile, label in zip(tiles, labels, strict=True):
        sheet.paste(tile, (x, GUTTER))
        draw.text((x, GUTTER + SHEET_HEIGHT + 6), label, fill=(235, 235, 235))
        x += tile.width + GUTTER
    sheet.save(out_path)
    return out_path
