"""Finish a picked art take into game images (#253 FR4, AC5-AC7).

``icon`` and ``ui`` takes must sit on one flat background. The four 8 x 8 corner patches must agree
within ``TOLERANCE``; the background is flood-filled from the corners over pixels close to it, and
the rest is the subject. The subject's edge is feathered over 2 px, the subject is cropped and
scaled onto a square canvas with an 8 % margin, and its bottom sits on the baseline. ``icon`` also
writes a 64 px copy. A ``painting`` is resized to a width, keeps its aspect ratio, and is saved as
RGB with no alpha.

Every check runs before the first write, so a failing take writes nothing. Pillow writes each PNG
with no metadata and a fixed compression level, and every file is replaced through a temp file, so
a rerun gives byte-identical output.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image as PILImage
from PIL import ImageFilter

from nmg_game_dev.texture.art import NAME_PATTERN, raw_dir
from nmg_game_dev.texture.errors import TextureGenError

TOLERANCE = 24
MARGIN = 0.08
CORNER = 8
PNG_COMPRESS_LEVEL = 6
PAINTING_WIDTH = 1920
# kind -> (full canvas size, small copy size or None)
ICON_SIZES: dict[str, tuple[int, int | None]] = {"icon": (512, 64), "ui": (1024, None)}
DEST: dict[str, str] = {
    "icon": "game/assets/UI/Icons",
    "ui": "game/assets/UI/Panels",
    "painting": "game/assets/UI/Paintings",
}
LANCZOS = PILImage.Resampling.LANCZOS


def finish(
    root: Path, kind: str, name: str, pick: int, *, width: int | None = None
) -> dict[str, Any]:
    """Write the game images for take ``pick`` of ``name`` and return the files written.

    ``width`` applies to paintings only. A missing take raises ``art.take_not_found``; a background
    that is not flat raises ``art.background_not_flat``; a subject on the border, or no subject,
    raises ``art.subject_cropped``.
    """
    if kind not in DEST:
        raise TextureGenError(
            "texture.invalid_request",
            f"Unknown art kind {kind!r}.",
            "Use --kind icon, ui, or painting.",
        )
    if not NAME_PATTERN.match(name):
        raise TextureGenError(
            "texture.invalid_request",
            f"Art name {name!r} is not a PascalCase identifier.",
            "Use the name the take was generated under, such as HealthPotion.",
        )
    if width is not None and (kind != "painting" or width < 1):
        raise TextureGenError(
            "texture.invalid_request",
            "--width applies to a positive painting width only.",
            "Pass --width with --kind painting, or omit it for icons and UI art.",
        )
    take = raw_dir(root, kind) / f"{name}-{pick}.png"
    if not take.is_file():
        raise TextureGenError(
            "art.take_not_found",
            f"There is no raw take at {take}.",
            "Generate the take with texture art, or pick a seed that has a raw take under "
            "SourceArt/Art/raw/<kind>/.",
        )
    with PILImage.open(take) as opened:
        rgb = opened.convert("RGB")
    out_dir = root / DEST[kind]
    if kind == "painting":
        outputs = [(out_dir / f"{name}.png", _painting(rgb, width or PAINTING_WIDTH))]
    else:
        outputs = _cutout_outputs(rgb, out_dir, name, kind)
    files: list[dict[str, Any]] = []
    for path, image in outputs:
        _write_png(path, image)
        files.append({"path": str(path), "width": image.width, "height": image.height})
    return {"kind": kind, "name": name, "pick": pick, "files": files}


def _painting(rgb: PILImage.Image, width: int) -> PILImage.Image:
    """Resize to ``width`` keeping the aspect ratio. The result is RGB with no alpha."""
    height = max(1, round(width * rgb.height / rgb.width))
    return rgb.resize((width, height), LANCZOS)


def _cutout_outputs(
    rgb: PILImage.Image, out_dir: Path, name: str, kind: str
) -> list[tuple[Path, PILImage.Image]]:
    """The full canvas, and the icon's small copy, all computed before anything is written."""
    subject = _subject_mask(np.asarray(rgb, dtype=np.int16))
    alpha = PILImage.fromarray((subject * 255).astype(np.uint8))
    alpha = alpha.filter(ImageFilter.BoxBlur(1)).filter(ImageFilter.BoxBlur(1))
    rgba = rgb.convert("RGBA")
    rgba.putalpha(alpha)
    bbox = alpha.getbbox()
    if bbox is None:
        raise _subject_cropped()
    full_size, small_size = ICON_SIZES[kind]
    canvas = _place(rgba.crop(bbox), full_size)
    outputs = [(out_dir / f"{name}.png", canvas)]
    if small_size is not None:
        small = canvas.resize((small_size, small_size), LANCZOS)
        outputs.append((out_dir / f"{name}_small.png", small))
    return outputs


def _subject_mask(pixels: np.ndarray) -> np.ndarray:
    """Boolean mask of the subject: every pixel the corner flood fill does not reach."""
    patches = [
        pixels[:CORNER, :CORNER],
        pixels[:CORNER, -CORNER:],
        pixels[-CORNER:, :CORNER],
        pixels[-CORNER:, -CORNER:],
    ]
    means = [patch.reshape(-1, 3).mean(axis=0) for patch in patches]
    for index, first in enumerate(means):
        for second in means[index + 1 :]:
            if float(np.max(np.abs(first - second))) > TOLERANCE:
                raise TextureGenError(
                    "art.background_not_flat",
                    "The four corners of the take differ in colour, so its background is not flat.",
                    "Regenerate the take with a flat plain background (the icon and ui framing "
                    "asks for one), or pick a take whose corners match.",
                )
    background = np.mean(np.stack(means), axis=0)
    close = np.max(np.abs(pixels - background), axis=2) <= TOLERANCE
    reached = _flood_from_corners(close)
    subject = ~reached
    if not subject.any():
        raise _subject_cropped()
    if subject[0, :].any() or subject[-1, :].any() or subject[:, 0].any() or subject[:, -1].any():
        raise _subject_cropped()
    return subject


def _flood_from_corners(close: np.ndarray) -> np.ndarray:
    """4-connected fill from the four corners over ``close`` pixels, done as numpy frontiers so no
    recursion is needed."""
    reached = np.zeros(close.shape, dtype=bool)
    frontier = np.zeros(close.shape, dtype=bool)
    frontier[0, 0] = frontier[0, -1] = frontier[-1, 0] = frontier[-1, -1] = True
    frontier &= close
    while frontier.any():
        reached |= frontier
        grown = np.zeros_like(frontier)
        grown[1:, :] |= frontier[:-1, :]
        grown[:-1, :] |= frontier[1:, :]
        grown[:, 1:] |= frontier[:, :-1]
        grown[:, :-1] |= frontier[:, 1:]
        frontier = grown & close & ~reached
    return reached


def _subject_cropped() -> TextureGenError:
    return TextureGenError(
        "art.subject_cropped",
        "The subject touches the edge of the take, or the take has no subject.",
        "Regenerate the take with the whole object inside the frame and empty space around it, "
        "or pick another take.",
    )


def _place(cropped: PILImage.Image, size: int) -> PILImage.Image:
    """Scale ``cropped`` so its long side is the canvas minus the margins, then centre it
    horizontally with its bottom on the baseline at ``size * (1 - MARGIN)``."""
    long_side = round(size * (1 - 2 * MARGIN))
    width, height = cropped.size
    if width >= height:
        new_width, new_height = long_side, max(1, round(height * long_side / width))
    else:
        new_width, new_height = max(1, round(width * long_side / height)), long_side
    scaled = cropped.resize((new_width, new_height), LANCZOS)
    canvas = PILImage.new("RGBA", (size, size), (0, 0, 0, 0))
    baseline = round(size * (1 - MARGIN))
    canvas.paste(scaled, ((size - new_width) // 2, baseline - new_height))
    return canvas


def _write_png(path: Path, image: PILImage.Image) -> None:
    """Write ``image`` as a metadata-free PNG through a temp file and an atomic replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image.info.clear()
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(fd)
    try:
        image.save(tmp_name, format="PNG", compress_level=PNG_COMPRESS_LEVEL)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
