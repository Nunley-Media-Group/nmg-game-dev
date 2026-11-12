"""Root-wide contact sheet for reviewing generated tiling textures (#152).

``build`` scans the output root for texture sets (direct subfolders holding ``textures.json``),
renders every manifest albedo as a cell (the albedo tiled 2x2 under a two-line label), and writes
the cells, 24 to a page, to ``contact_sheet_NNN.png`` at the root. Only manifest ``images`` entries
become cells, so derived maps and comparison sheets never do. The rebuild calls no backend, no
hardware probe, and no model-weight check, so it runs on any host.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image as PILImage
from PIL import ImageDraw

from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.sheet import GUTTER

MANIFEST_NAME = "textures.json"
PAGE_PREFIX = "contact_sheet_"
TILE = 192
CELL = 2 * TILE
COLUMNS = 6
ROWS = 4
PER_PAGE = COLUMNS * ROWS
LABEL_HEIGHT = 40
LABEL_PAD = 6
LABEL_LINE = 16
BACKGROUND = (24, 24, 24)
TEXT = (235, 235, 235)
_PAGE_NAME = re.compile(rf"{PAGE_PREFIX}(\d+)\.png")


@dataclass(frozen=True)
class Cell:
    """One manifest image: its texture set, its labels, and where its albedo sits."""

    set_name: str
    backend: str
    seed: int
    path: Path


@dataclass(frozen=True)
class ContactSheet:
    """The pages written at the root, the cells they hold, and the albedos left out."""

    pages: tuple[Path, ...] = ()
    cells: int = 0
    skipped: tuple[dict[str, str], ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {
            "pages": [str(page) for page in self.pages],
            "cells": self.cells,
            "skipped": [dict(entry) for entry in self.skipped],
        }


def _set_dirs(root: Path) -> list[Path]:
    """The direct subfolders of ``root`` that hold a manifest, sorted by name."""
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / MANIFEST_NAME).is_file())


def _manifest_cells(set_dir: Path) -> list[Cell]:
    """The cells one set's manifest lists. Raises when the manifest is unreadable or malformed."""
    data = json.loads((set_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    images = data.get("images") if isinstance(data, dict) else None
    if not isinstance(images, list):
        raise ValueError("'images' is missing or not a list")
    return [
        Cell(
            set_name=set_dir.name,
            backend=str(entry["backend"]),
            seed=int(entry["seed"]),
            path=set_dir / Path(str(entry["path"])).name,
        )
        for entry in images
    ]


def collect(root: Path) -> tuple[list[Cell], list[dict[str, str]]]:
    """The cells of every texture set under ``root``, sorted, and the manifests skipped."""
    cells: list[Cell] = []
    skipped: list[dict[str, str]] = []
    for set_dir in _set_dirs(root):
        try:
            found = _manifest_cells(set_dir)
        except (OSError, ValueError, KeyError, TypeError) as error:
            manifest = set_dir / MANIFEST_NAME
            skipped.append({"path": str(manifest), "reason": f"unreadable manifest: {error}"})
            continue
        cells.extend(found)
    cells.sort(key=lambda cell: (cell.set_name, cell.backend, cell.seed))
    return cells, skipped


def _load_tile(path: Path) -> PILImage.Image:
    """The albedo at ``path`` as an RGB tile of ``TILE`` pixels a side."""
    with PILImage.open(path) as opened:
        albedo = opened.convert("RGB")
    return albedo.resize((TILE, TILE), PILImage.Resampling.LANCZOS)


def _render_page(tiles: list[tuple[Cell, PILImage.Image]]) -> PILImage.Image:
    """One page: up to ``COLUMNS`` cells per row, as many rows as the cells need."""
    rows = (len(tiles) + COLUMNS - 1) // COLUMNS
    row_pitch = CELL + LABEL_HEIGHT + GUTTER
    page = PILImage.new(
        "RGB",
        (GUTTER + COLUMNS * (CELL + GUTTER), GUTTER + rows * row_pitch),
        BACKGROUND,
    )
    draw = ImageDraw.Draw(page)
    for index, (cell, tile) in enumerate(tiles):
        x = GUTTER + (index % COLUMNS) * (CELL + GUTTER)
        y = GUTTER + (index // COLUMNS) * row_pitch
        for dx in (0, TILE):
            for dy in (0, TILE):
                page.paste(tile, (x + dx, y + dy))
        label_y = y + CELL + LABEL_PAD
        draw.text((x + LABEL_PAD, label_y), cell.set_name, fill=TEXT)
        draw.text(
            (x + LABEL_PAD, label_y + LABEL_LINE),
            f"{cell.backend} seed {cell.seed}",
            fill=TEXT,
        )
    return page


def _remove_stale_pages(root: Path, page_count: int) -> None:
    """Delete contact sheet pages numbered above ``page_count``, left by an older, larger build."""
    for page in root.glob(f"{PAGE_PREFIX}*.png"):
        match = _PAGE_NAME.fullmatch(page.name)
        if match is not None and int(match.group(1)) > page_count:
            page.unlink()


def build(root: Path, *, require_sets: bool) -> ContactSheet:
    """Rebuild the contact sheet pages at ``root`` from the current texture sets.

    With ``require_sets`` (the on-demand rebuild), a root with no texture sets raises
    ``texture.no_texture_sets``. The generate run passes False and never fails on an empty root.
    """
    if require_sets and not _set_dirs(root):
        raise TextureGenError(
            "texture.no_texture_sets",
            f"No texture sets under {root}.",
            "Generate a texture first (python -m nmg_game_dev.texture generate --prompt … or the "
            "generate_textures tool), or pass --root / set NMG_GAME_DEV_TEXTURE_DIR to the folder "
            "that holds them.",
        )
    cells, skipped = collect(root)
    tiles: list[tuple[Cell, PILImage.Image]] = []
    for cell in cells:
        try:
            tiles.append((cell, _load_tile(cell.path)))
        except OSError as error:
            skipped.append({"path": str(cell.path), "reason": f"{type(error).__name__}: {error}"})
    pages: list[Path] = []
    for number, start in enumerate(range(0, len(tiles), PER_PAGE), start=1):
        page = root / f"{PAGE_PREFIX}{number:03d}.png"
        _render_page(tiles[start : start + PER_PAGE]).save(page)
        pages.append(page)
    _remove_stale_pages(root, len(pages))
    return ContactSheet(pages=tuple(pages), cells=len(tiles), skipped=tuple(skipped))
