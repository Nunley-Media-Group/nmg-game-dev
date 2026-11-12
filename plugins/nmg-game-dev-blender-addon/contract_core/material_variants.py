"""Material variants: the declaration, its contract rules, and the texture sizes they check (#148).

A declaration is <Name>.material-variants.json beside the asset's .blend. validate_asset loads it
with load_declaration and checks it with check_declaration, and export reads the report entries
that check_declaration returns. This module imports no bpy: validate.py passes in the predicted
parts, the authored materials the bake merges, and the Desktop base-colour sizes read from the
scene.
"""

from __future__ import annotations

import json
import math
import re
import struct
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from ..utils.master_material import MASTER_PARAMETERS
from .report import ContractError, finding

SCHEMA_VERSION: Final = 1
_PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
_NAME: Final = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_TOP_KEYS: Final = frozenset({"schema", "material_variants"})
_ENTRY_KEYS: Final = frozenset({"name", "material", "base_color", "parameters"})
_INVALID: Final = "material_variant.declaration_invalid"


def png_size(path: Path) -> tuple[int, int] | None:
    """Return (width, height) from the PNG IHDR chunk, or None when path is not a readable PNG."""
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != _PNG_SIGNATURE or header[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def load_declaration(path: Path) -> list[dict[str, Any]]:
    """Return the declared entries after the structural checks, or raise declaration_invalid.

    Parameter values are not checked here. check_declaration reports a malformed value as a
    material_variant.parameter finding, so only the document's shape can raise declaration_invalid.
    """
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _invalid(path, f"it is not readable JSON ({error})") from error
    if (
        not isinstance(data, dict)
        or set(data) - _TOP_KEYS
        or data.get("schema") != SCHEMA_VERSION
        or not isinstance(data.get("material_variants"), list)
    ):
        raise _invalid(path, 'it must be an object with "schema": 1 and a material_variants list')
    entries: list[dict[str, Any]] = []
    for index, entry in enumerate(data["material_variants"]):
        if not isinstance(entry, dict) or set(entry) - _ENTRY_KEYS:
            raise _invalid(
                path,
                f"entry {index} must be an object with the keys name, material, "
                "base_color, and parameters",
            )
        name, material = entry.get("name"), entry.get("material")
        base_color = entry.get("base_color")
        parameters = entry.get("parameters", {})
        if not isinstance(name, str) or not isinstance(material, str):
            raise _invalid(path, f"entry {index} needs string name and material values")
        if base_color is not None and (not isinstance(base_color, str) or not base_color):
            raise _invalid(path, f"entry {index} base_color must be a non-empty path string")
        if not isinstance(parameters, dict):
            raise _invalid(path, f"entry {index} parameters must be an object")
        entries.append(
            {
                "name": name,
                "material": material,
                "base_color": base_color,
                "parameters": dict(parameters),
            }
        )
    return entries


def check_declaration(
    collection: str,
    path: Path,
    entries: list[dict[str, Any]],
    *,
    parts: list[str],
    merged_sources: frozenset[str],
    main_px: Mapping[str, int],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Check each declared entry against the material_variant rules.

    parts are the post-bake part names, so M_<Name>_<Part> is each predicted material.
    merged_sources are the authored material names the bake merges into M_<Name>_Body, and
    main_px maps each part to its Desktop base-colour size. Returns the findings and the report
    entries (name, material, base_color path or None, and the parameters with alpha defaulted).
    """
    prefix = f"M_{collection}_"
    part_materials = {f"{prefix}{part}": part for part in parts}
    findings: list[dict[str, str]] = []
    report: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        name, material = entry["name"], entry["material"]
        part = part_materials.get(material)
        part_name = material[len(prefix) :] if material.startswith(prefix) else ""

        if not _NAME.fullmatch(name):
            _fail(
                findings,
                collection,
                name,
                material,
                "material_variant.name",
                "the name must be PascalCase letters and digits",
            )
        combined = f"{part_name}_{name}" if part_name else ""
        if combined and combined in parts:
            _fail(
                findings,
                collection,
                name,
                material,
                "material_variant.name",
                f"MI_{collection}_{combined} would be the material instance of part {combined}",
            )

        if (material, name) in seen:
            _fail(
                findings,
                collection,
                name,
                material,
                "material_variant.duplicate",
                f"another entry on {material} already has the name {name}",
            )
        seen.add((material, name))

        if part is None and material in merged_sources:
            _fail(
                findings,
                collection,
                name,
                material,
                "material_variant.material_merged",
                f"the bake merges {material} into M_{collection}_Body, so declare the variant "
                f"on M_{collection}_Body",
            )
        elif part is None:
            _fail(
                findings,
                collection,
                name,
                material,
                "material_variant.material_missing",
                f"{material} is not one of the asset's materials after the bake "
                f"({', '.join(sorted(part_materials)) or 'none'})",
            )

        base_path: Path | None = None
        if entry["base_color"] is not None:
            base_path = _resolve(path.parent, entry["base_color"])
            size = png_size(base_path) if base_path.is_file() else None
            if size is None:
                _fail(
                    findings,
                    collection,
                    name,
                    material,
                    "material_variant.texture_missing",
                    f"base_color {entry['base_color']} must be an existing PNG beside the "
                    "declaration",
                )
            else:
                width, height = size
                if width != height or width <= 0 or width & (width - 1):
                    _fail(
                        findings,
                        collection,
                        name,
                        material,
                        "material_variant.texture_size",
                        f"base_color is {width}x{height}; replacement textures must be "
                        "power-of-two squares",
                    )
                elif part is not None and width != main_px[part]:
                    _fail(
                        findings,
                        collection,
                        name,
                        material,
                        "material_variant.texture_size",
                        f"base_color is {width} px; the Desktop base colour of {material} is "
                        f"{main_px[part]} px",
                    )

        parameters = entry["parameters"]
        valid: dict[str, list[float]] = {}
        for parameter, value in parameters.items():
            kind = MASTER_PARAMETERS.get(parameter)
            if kind is None:
                _fail(
                    findings,
                    collection,
                    name,
                    material,
                    "material_variant.parameter",
                    f"{parameter} is not a parameter of M_NmgORM "
                    f"(declared: {', '.join(sorted(MASTER_PARAMETERS))})",
                )
            elif kind == "vector":
                vector = _vector(value)
                if vector is None:
                    _fail(
                        findings,
                        collection,
                        name,
                        material,
                        "material_variant.parameter",
                        f"{parameter} must be [r, g, b] or [r, g, b, a] with finite numbers of "
                        "at least 0",
                    )
                else:
                    valid[parameter] = vector

        if base_path is None and not parameters:
            _fail(
                findings,
                collection,
                name,
                material,
                "material_variant.empty",
                "give it a base_color, parameters, or both",
            )
        report.append(
            {
                "name": name,
                "material": material,
                "base_color": str(base_path) if base_path is not None else None,
                "parameters": valid,
            }
        )
    return findings, report


def _fail(
    findings: list[dict[str, str]],
    collection: str,
    name: str,
    material: str,
    rule: str,
    detail: str,
) -> None:
    findings.append(
        finding(
            rule,
            name,
            f"{collection}: material variant {name} on {material} fails {rule}: {detail}.",
        )
    )


def _resolve(base: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else base / candidate


def _vector(value: Any) -> list[float] | None:
    """A [r, g, b] or [r, g, b, a] list of finite numbers at least 0, with alpha defaulted to 1."""
    if not isinstance(value, list) or len(value) not in (3, 4):
        return None
    numbers: list[float] = []
    for item in value:
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(item)
            or item < 0
        ):
            return None
        numbers.append(float(item))
    if len(numbers) == 3:
        numbers.append(1.0)
    return numbers


def _invalid(path: Path, detail: str) -> ContractError:
    return ContractError(
        _INVALID,
        f"{path.name} is not a valid material-variants declaration: {detail}.",
        "Fix the declaration to the format in docs/asset-contract.md section 4, then rerun.",
    )
