"""Pack baked float channels into contract PNGs: BC (sRGB), N, and ORM (Non-Color).

Values are encoded here with NumPy and written as raw 8-bit buffers, so Blender's color
management never transforms them: Blender's PNG save writes the stored bytes unchanged.
"""

from __future__ import annotations

from pathlib import Path

import bpy
import numpy as np

KINDS: tuple[str, ...] = ("BC", "N", "ORM")
_COLORSPACE: dict[str, str] = {"BC": "sRGB", "N": "Non-Color", "ORM": "Non-Color"}


def read_rgba(image: bpy.types.Image) -> np.ndarray:
    """Return a baked float image as an (height, width, 4) array in Blender's row order."""
    width, height = image.size
    flat = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(flat)
    return flat.reshape(height, width, 4)


def srgb_encode(linear: np.ndarray) -> np.ndarray:
    clipped = np.clip(linear, 0.0, 1.0)
    return np.where(
        clipped <= 0.0031308,
        clipped * 12.92,
        1.055 * np.power(clipped, 1.0 / 2.4) - 0.055,
    )


def base_color_rgb(rgba: np.ndarray) -> np.ndarray:
    return srgb_encode(rgba[..., :3])


def normal_rgb(rgba: np.ndarray) -> np.ndarray:
    return np.clip(rgba[..., :3], 0.0, 1.0)


def orm_rgb(ao: np.ndarray, roughness: np.ndarray, metallic: np.ndarray) -> np.ndarray:
    """R = ambient occlusion, G = roughness, B = metallic (contract section 4)."""
    return np.clip(np.stack([ao[..., 0], roughness[..., 0], metallic[..., 0]], axis=-1), 0.0, 1.0)


def write_png(name: str, rgb: np.ndarray, kind: str, path: Path) -> bpy.types.Image:
    """Save rgb as a PNG at path and return the in-memory image (the caller removes it)."""
    height, width = rgb.shape[:2]
    image = bpy.data.images.new(name, width, height, alpha=True, float_buffer=False)
    image.colorspace_settings.name = _COLORSPACE[kind]
    rgba = np.ones((height, width, 4), dtype=np.float32)
    rgba[..., :3] = np.clip(rgb, 0.0, 1.0)
    image.pixels.foreach_set(rgba.ravel())
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    return image


def pack_set(
    part: str,
    asset: str,
    channels: dict[str, np.ndarray],
    desktop_dir: Path,
    mobile_dir: Path,
    desktop_px: int,
    mobile_px: int,
) -> dict[str, dict[str, Path]]:
    """Write the BC, N, and ORM PNGs for one texture set at Desktop and Mobile size.

    Returns {"desktop": {"BC": path, ...}, "mobile": {...}}. Mobile copies are the Desktop
    image scaled with Image.scale, saved under the same file names.
    """
    paths: dict[str, dict[str, Path]] = {"desktop": {}, "mobile": {}}
    target = min(mobile_px, desktop_px)
    desktop_dir.mkdir(parents=True, exist_ok=True)
    mobile_dir.mkdir(parents=True, exist_ok=True)
    for kind in KINDS:
        image_name = f"T_{asset}_{part}_{kind}"
        desktop_path = desktop_dir / f"{image_name}.png"
        mobile_path = mobile_dir / f"{image_name}.png"
        desktop = write_png(image_name, channels[kind], kind, desktop_path)
        if target != desktop_px:
            scaled = desktop.copy()
            scaled.scale(target, target)
            scaled.filepath_raw = str(mobile_path)
            scaled.file_format = "PNG"
            scaled.save()
            bpy.data.images.remove(scaled)
        else:
            _rewrite_copy(desktop, mobile_path)
        bpy.data.images.remove(desktop)
        paths["desktop"][kind] = desktop_path
        paths["mobile"][kind] = mobile_path
    return paths


def _rewrite_copy(image: bpy.types.Image, path: Path) -> None:
    copy = image.copy()
    copy.filepath_raw = str(path)
    copy.file_format = "PNG"
    copy.save()
    bpy.data.images.remove(copy)


def file_bytes(paths: list[Path]) -> int:
    return sum(path.stat().st_size for path in paths)
