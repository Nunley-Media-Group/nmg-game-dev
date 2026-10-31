"""Derived PBR maps from a seamless albedo (#7 FR15, AC19).

Writes ``<stem>_N.png`` (OpenGL normal from luminance height), ``<stem>_R.png`` and ``<stem>_M.png``
(constant roughness and metallic from a preset or explicit values), and optionally
``<stem>_AO.png``. Every map is wrap-around, so each one tiles like the albedo it came from.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image as PILImage

from nmg_game_dev.texture.errors import TextureGenError

# (roughness, metallic) per material preset.
PRESETS: dict[str, tuple[float, float]] = {
    "fabric": (0.9, 0.0),
    "wood": (0.7, 0.0),
    "stone": (0.85, 0.0),
    "plastic": (0.5, 0.0),
    "metal": (0.35, 1.0),
}

AO_BLUR_RADIUS = 4
AO_STRENGTH = 4.0


@dataclass(frozen=True)
class MapSet:
    """The derived map files written next to one albedo."""

    normal: Path
    roughness: Path
    metallic: Path
    ao: Path | None

    def as_dict(self) -> dict[str, str]:
        out = {"N": str(self.normal), "R": str(self.roughness), "M": str(self.metallic)}
        if self.ao is not None:
            out["AO"] = str(self.ao)
        return out


def resolve_material(maps: str | tuple[float, float]) -> tuple[float, float]:
    """A preset name or explicit ``(roughness, metallic)`` pair, each value in [0, 1]."""
    if isinstance(maps, str):
        if maps not in PRESETS:
            raise TextureGenError(
                "texture.invalid_request",
                f"Unknown material preset {maps!r}.",
                f"Use one of the presets: {', '.join(sorted(PRESETS))}, or pass explicit "
                "roughness and metallic values.",
            )
        return PRESETS[maps]
    roughness, metallic = maps
    for name, value in (("roughness", roughness), ("metallic", metallic)):
        if not 0.0 <= value <= 1.0:
            raise TextureGenError(
                "texture.invalid_request",
                f"{name} must be between 0 and 1, got {value}.",
                "Pass roughness and metallic values between 0 and 1.",
            )
    return roughness, metallic


def _wrap_box_blur(field: NDArray[np.float64], radius: int) -> NDArray[np.float64]:
    """Separable box blur that wraps at the edges, so the result stays seamless."""
    blurred = field
    for axis in (0, 1):
        acc = np.zeros_like(blurred)
        for offset in range(-radius, radius + 1):
            acc += np.roll(blurred, offset, axis=axis)
        blurred = acc / (2 * radius + 1)
    return blurred


def _write_gray(path: Path, value: float, height: int, width: int) -> None:
    level = int(round(min(max(value, 0.0), 1.0) * 255))
    PILImage.fromarray(np.full((height, width), level, dtype=np.uint8)).save(path)


def derive(
    albedo_path: Path,
    roughness: float,
    metallic: float,
    ao: bool = False,
    strength: float = 2.0,
) -> MapSet:
    """Write the N, R, M (and optional AO) maps beside ``albedo_path`` and return their paths."""
    rgb = np.asarray(PILImage.open(albedo_path).convert("RGB"), dtype=np.float64) / 255.0
    height_field = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    rows, cols = height_field.shape

    dx = (np.roll(height_field, -1, axis=1) - np.roll(height_field, 1, axis=1)) / 2.0
    dy = (np.roll(height_field, -1, axis=0) - np.roll(height_field, 1, axis=0)) / 2.0
    nx, ny, nz = -dx * strength, -dy * strength, np.ones_like(height_field)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.stack([nx / length, ny / length, nz / length], axis=-1)
    normal_rgb = np.clip(np.rint((normal + 1.0) / 2.0 * 255.0), 0, 255).astype(np.uint8)

    stem = albedo_path.with_suffix("")
    normal_path = Path(f"{stem}_N.png")
    roughness_path = Path(f"{stem}_R.png")
    metallic_path = Path(f"{stem}_M.png")
    PILImage.fromarray(normal_rgb).save(normal_path)
    _write_gray(roughness_path, roughness, rows, cols)
    _write_gray(metallic_path, metallic, rows, cols)

    ao_path: Path | None = None
    if ao:
        blurred = _wrap_box_blur(height_field, AO_BLUR_RADIUS)
        occlusion = 1.0 - np.clip(AO_STRENGTH * (blurred - height_field), 0.0, 1.0)
        ao_path = Path(f"{stem}_AO.png")
        PILImage.fromarray(np.rint(occlusion * 255.0).astype(np.uint8)).save(ao_path)

    return MapSet(normal=normal_path, roughness=roughness_path, metallic=metallic_path, ao=ao_path)
