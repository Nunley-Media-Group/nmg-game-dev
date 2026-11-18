"""Material variants as Godot ``StandardMaterial3D`` resources (#148, #249 FR6).

``import_godot`` calls ``write_variant_materials`` once per variant folder. It writes
``M_<Name>_<Part>_<Variant>.tres`` for each declared material variant and removes any such file
whose variant is no longer declared. ``list_material_variants`` reads them back from the files
finalize wrote (``nmg-variants.json`` plus the ``.tres`` files), so listing never starts Godot.

Each variant entry in ``nmg-variants.json`` (``material_variants.desktop`` / ``.mobile``) carries
``name``, ``material`` (``M_<Name>_<Part>``), ``base_color`` (the variant's
``T_<Name>_<Part>_BC_<Variant>.png`` beside the ``.glb``, or ``None`` for a parameter-only
variant), ``parameters`` (``{"Tint": [r, g, b, a]}``) and, when the add-on records it,
``material_resource`` (the ``.tres`` file name). Without ``material_resource`` the name is
``<material>_<name>.tres``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

from nmg_game_dev.pipeline.errors import PipelineError

from .project import find_project, godot_string, res_path

VARIANT_FOLDERS: Final = ("Desktop", "Mobile")
SIDECAR: Final = "nmg-variants.json"
_FAILED: Final = "finalize.material_variants_failed"
_WHITE: Final = (1.0, 1.0, 1.0, 1.0)


def resource_name(entry: Mapping[str, Any]) -> str:
    """Return the ``.tres`` file name for one sidecar entry."""
    declared = entry.get("material_resource")
    if isinstance(declared, str) and declared.endswith(".tres"):
        return Path(declared).name
    return f"{entry['material']}_{entry['name']}.tres"


def sidecar_entries(sidecar: Mapping[str, Any], variant: str) -> list[dict[str, Any]]:
    """Return the material-variant entries the sidecar declares for ``variant`` (Desktop/Mobile)."""
    declared = sidecar.get("material_variants")
    if not isinstance(declared, dict):
        return []
    entries = declared.get(variant.lower())
    if not isinstance(entries, list):
        return []
    return [dict(item) for item in cast(list[object], entries) if isinstance(item, dict)]


def render_material(
    project: Path,
    folder: Path,
    name: str,
    entry: Mapping[str, Any],
) -> str:
    """Return the ``StandardMaterial3D`` text for one material variant in ``folder``.

    Albedo is the variant base colour (or the part's own ``_BC`` for a parameter-only variant),
    the normal map is the part's ``_N``, and ``_ORM`` drives occlusion (red), roughness (green) and
    metallic (blue). ``albedo_color`` is the ``Tint`` parameter, white by default.
    """
    material = str(entry["material"])
    prefix = f"M_{name}_"
    if not material.startswith(prefix):
        raise PipelineError(
            code="import_godot.mismatch",
            message=f"Material variant {entry.get('name')} names {material}, which is not "
            f"{prefix}<Part>.",
            remediation="Name each declared material M_<Name>_<Part>, then rerun export.",
            stage="import_godot",
        )
    part = material[len(prefix) :]
    base_color = entry.get("base_color")
    albedo = str(base_color) if base_color else f"T_{name}_{part}_BC.png"
    textures = (
        ("1_albedo", folder / albedo),
        ("2_normal", folder / f"T_{name}_{part}_N.png"),
        ("3_orm", folder / f"T_{name}_{part}_ORM.png"),
    )
    lines = [f'[gd_resource type="StandardMaterial3D" load_steps={len(textures) + 1} format=3]', ""]
    for ident, path in textures:
        lines.append(
            f'[ext_resource type="Texture2D" path={godot_string(res_path(project, path))} '
            f'id="{ident}"]'
        )
    r, g, b, a = _tint(entry.get("parameters"))
    lines += [
        "",
        "[resource]",
        f"resource_name = {godot_string(material + '_' + str(entry['name']))}",
        f"albedo_color = Color({_num(r)}, {_num(g)}, {_num(b)}, {_num(a)})",
        'albedo_texture = ExtResource("1_albedo")',
        "metallic = 1.0",
        'metallic_texture = ExtResource("3_orm")',
        "metallic_texture_channel = 2",
        'roughness_texture = ExtResource("3_orm")',
        "roughness_texture_channel = 1",
        "normal_enabled = true",
        'normal_texture = ExtResource("2_normal")',
        "ao_enabled = true",
        'ao_texture = ExtResource("3_orm")',
        "ao_texture_channel = 0",
        "",
    ]
    return "\n".join(lines)


def write_variant_materials(
    project: Path,
    folder: Path,
    name: str,
    entries: Sequence[Mapping[str, Any]],
) -> list[Path]:
    """Write one ``.tres`` per entry into ``folder`` and remove undeclared variant ``.tres`` files.

    Only ``M_<Name>_*.tres`` files are candidates for removal: finalize never writes the main
    materials as ``.tres`` (they live inside the ``.glb``). Returns the written paths.
    """
    written: list[Path] = []
    for entry in entries:
        path = folder / resource_name(entry)
        text = render_material(project, folder, name, entry)
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
        written.append(path)
    keep = set(written)
    for stale in sorted(folder.glob(f"M_{name}_*.tres")):
        if stale not in keep:
            stale.unlink()
    return written


def list_material_variants(export_root: Path, category: str, name: str) -> list[dict[str, Any]]:
    """Return ``[{name, material, desktop, mobile}]`` from ``nmg-variants.json`` and the ``.tres``.

    ``desktop``/``mobile`` is the ``res://`` path of the variant's ``.tres`` when that file exists,
    else ``None``. Rows are sorted by ``(material, name)``. A missing or unreadable sidecar raises
    ``finalize.material_variants_failed``. Godot never runs.
    """
    root = export_root / category / name
    sidecar_path = root / SIDECAR
    sidecar = _read_sidecar(sidecar_path)
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    project: Path | None = None
    for variant in VARIANT_FOLDERS:
        for entry in sidecar_entries(sidecar, variant):
            variant_name = entry.get("name")
            material = entry.get("material")
            if not isinstance(variant_name, str) or not isinstance(material, str):
                raise _fail(
                    f"{sidecar_path} has a material variant without a name or material: {entry}"
                )
            row = rows.setdefault(
                (material, variant_name),
                {"name": variant_name, "material": material, "desktop": None, "mobile": None},
            )
            path = root / variant / resource_name(entry)
            if path.is_file():
                if project is None:
                    project = _project(root)
                row[variant.lower()] = res_path(project, path)
    return [rows[key] for key in sorted(rows)]


def _read_sidecar(path: Path) -> dict[str, Any]:
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise _fail(f"{path} does not exist; the asset has not been finalized there.") from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _fail(f"{path} cannot be read as JSON: {error}") from error
    if not isinstance(data, dict):
        raise _fail(f"{path} does not hold a JSON object.")
    return cast(dict[str, Any], data)


def _project(root: Path) -> Path:
    try:
        return find_project(root)
    except PipelineError as error:
        raise _fail(error.message) from error


def _fail(message: str) -> PipelineError:
    return PipelineError(
        code=_FAILED,
        message=message,
        remediation="Finalize the asset into the Godot project (game/assets by default), or pass "
        "the export_root it was finalized under, then rerun.",
        stage="finalize",
    )


def _tint(parameters: object) -> tuple[float, float, float, float]:
    if not isinstance(parameters, dict):
        return _WHITE
    value = cast(dict[str, object], parameters).get("Tint")
    if not isinstance(value, list) or len(value) not in (3, 4):
        return _WHITE
    numbers = [float(item) for item in cast(list[float], value)]
    if len(numbers) == 3:
        numbers.append(1.0)
    return numbers[0], numbers[1], numbers[2], numbers[3]


def _num(value: float) -> str:
    return format(value, ".6g") if value != int(value) else f"{int(value)}"


__all__ = [
    "list_material_variants",
    "render_material",
    "resource_name",
    "sidecar_entries",
    "write_variant_materials",
]
