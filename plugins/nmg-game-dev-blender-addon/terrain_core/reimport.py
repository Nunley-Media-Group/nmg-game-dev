"""Terrain re-import check against the pre-export report (#154, FR10).

For one variant folder the check reads ``T_<Name>_Height.png`` and the ``T_<Name>_Layer_<L>.png``
weightmaps, and confirms the layer textures exist. It fails the report with ``reimport.terrain``
when the resolution or bit depth differs, a file is missing, a weight pixel does not sum to 255,
or a decoded height differs from the evaluated height by more than 0.05 m. The evaluated heights
come from the height samples file that the export step wrote next to the pre-export report.
"""

from __future__ import annotations

import json
import sys
from array import array
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from ..contract_core.report import ContractError, build_report, finding
from .heightfield import WEIGHT_TOTAL, decode_heights, read_png_gray

HEIGHT_TOLERANCE_M: Final = 0.05
LAYER_TEXTURE_SUFFIXES: Final[tuple[str, ...]] = ("BC", "N", "ORM")
_VARIANTS: Final[tuple[str, ...]] = ("desktop", "mobile")


def write_height_samples(path: Path, heights: Sequence[float]) -> Path:
    """Write the evaluated heights (metres, grid order) as little-endian float32 values."""
    values = array("f", heights)
    if sys.byteorder == "big":
        values.byteswap()
    path.write_bytes(values.tobytes())
    return path


def read_height_samples(path: Path) -> array:
    """Read the float32 height samples that write_height_samples wrote."""
    values = array("f")
    values.frombytes(path.read_bytes())
    if sys.byteorder == "big":
        values.byteswap()
    return values


def terrain_reimport_check(
    variant_dir: str | Path, pre_report: str | Path | Mapping[str, Any]
) -> dict[str, Any]:
    """Decode one exported terrain variant and compare it with pre_report."""
    folder = Path(variant_dir)
    variant = folder.name.lower()
    if variant not in _VARIANTS:
        raise ContractError(
            "reimport.variant_unknown",
            f"{folder.name} is not a Desktop or Mobile folder.",
            "Point variant_dir at <Category>/<Name>/Desktop or <Category>/<Name>/Mobile.",
        )
    pre = _load_pre_report(pre_report)
    asset = str(pre["asset"])
    spec = pre["terrain"][variant]
    n = int(spec["heightmap_px"])
    layers = [str(layer) for layer in spec["layers"]]
    zmin = float(spec["height_min_m"])
    zmax = float(spec["height_max_m"])
    heights_path = pre.get("terrain_heights")
    if not heights_path:
        raise ContractError(
            "reimport.heights_missing",
            "The pre-export report has no terrain height samples to compare against.",
            "Rerun the export step so it writes the evaluated heights for this variant.",
        )

    findings: list[dict[str, str]] = []
    height_error = _check_heightmap(folder, asset, n, zmin, zmax, Path(heights_path), findings)
    weight_codes = _check_weightmaps(folder, asset, n, layers, findings)
    if weight_codes is not None and _pixels_off_total(weight_codes):
        findings.append(
            finding(
                "reimport.terrain",
                f"T_{asset}_Layer",
                f"The {variant} weightmaps do not sum to {WEIGHT_TOTAL} at every pixel.",
            )
        )
    for layer in layers:
        for suffix in LAYER_TEXTURE_SUFFIXES:
            name = f"T_{asset}_{layer}_{suffix}.png"
            if not (folder / name).is_file():
                findings.append(_missing(name))

    snapshot = {
        "variant": variant,
        "heightmap_px": n,
        "layers": layers,
        "max_height_error_m": round(height_error, 6),
    }
    return build_report("reimport", asset, "terrain", findings, snapshot)


def _check_heightmap(
    folder: Path,
    asset: str,
    n: int,
    zmin: float,
    zmax: float,
    heights_path: Path,
    findings: list[dict[str, str]],
) -> float:
    """Compare the decoded heightmap with the evaluated heights; return the largest error (m)."""
    name = f"T_{asset}_Height.png"
    path = folder / name
    if not path.is_file():
        findings.append(_missing(name))
        return 0.0
    image = read_png_gray(path)
    if image.bit_depth != 16 or (image.width, image.height) != (n, n):
        findings.append(
            finding(
                "reimport.terrain",
                name,
                f"{name} is {image.width}x{image.height} at {image.bit_depth}-bit; the terrain "
                f"heightmap must be {n}x{n} at 16-bit.",
            )
        )
        return 0.0
    expected = read_height_samples(heights_path)
    if len(expected) != n * n:
        raise ContractError(
            "reimport.heights_mismatch",
            f"The height samples hold {len(expected)} values for a {n}x{n} heightmap.",
            "Rerun the export step so the height samples match the heightmap resolution.",
        )
    decoded = decode_heights(image.samples, n, zmin, zmax)
    error = max((abs(a - b) for a, b in zip(decoded, expected, strict=True)), default=0.0)
    if error > HEIGHT_TOLERANCE_M:
        findings.append(
            finding(
                "reimport.terrain",
                name,
                f"{name} decodes to heights {error:.4f} m from the evaluated terrain; the limit "
                f"is {HEIGHT_TOLERANCE_M} m.",
            )
        )
    return error


def _check_weightmaps(
    folder: Path,
    asset: str,
    n: int,
    layers: Sequence[str],
    findings: list[dict[str, str]],
) -> list[bytes] | None:
    """Read each layer weightmap (8-bit); return the codes when every layer is valid."""
    codes: list[bytes] = []
    complete = True
    for layer in layers:
        name = f"T_{asset}_Layer_{layer}.png"
        path = folder / name
        if not path.is_file():
            findings.append(_missing(name))
            complete = False
            continue
        image = read_png_gray(path)
        if image.bit_depth != 8 or (image.width, image.height) != (n, n):
            findings.append(
                finding(
                    "reimport.terrain",
                    name,
                    f"{name} is {image.width}x{image.height} at {image.bit_depth}-bit; a weightmap "
                    f"must be {n}x{n} at 8-bit.",
                )
            )
            complete = False
            continue
        codes.append(image.samples)
    return codes if complete and codes else None


def _pixels_off_total(codes: Sequence[bytes]) -> bool:
    """True when any pixel's weights across the layers do not sum to WEIGHT_TOTAL."""
    return any(sum(pixel) != WEIGHT_TOTAL for pixel in zip(*codes, strict=True))


def _missing(name: str) -> dict[str, str]:
    return finding("reimport.terrain", name, f"{name} is missing from the exported variant folder.")


def _load_pre_report(pre_report: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(pre_report, Mapping):
        return dict(pre_report)
    return dict(json.loads(Path(pre_report).read_text(encoding="utf-8")))
