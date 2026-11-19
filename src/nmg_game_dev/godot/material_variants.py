"""Material variants as Godot ``StandardMaterial3D`` resources (#148, #249 FR6).

``import_godot`` calls ``plan_variant_materials`` for both variant folders (which validates every
declared entry and renders its text without writing), then ``write_planned`` for each. Writing puts
``M_<Name>_<Part>_<Variant>.tres`` in place for each declared material variant and removes a
``.tres`` it wrote on an earlier run whose variant is no longer declared; the names it wrote are
kept in the folder's ``.nmg-material-variants.json``, so a hand-made ``.tres`` is never removed.
A malformed entry raises ``import_godot.mismatch``. ``list_material_variants`` reads them back
from the files finalize wrote (``nmg-variants.json`` plus the ``.tres`` files), so listing never
starts Godot.

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
WRITTEN_MANIFEST: Final = ".nmg-material-variants.json"
"""The ``.tres`` names finalize wrote into a variant folder: the only ones it may remove."""
_FAILED: Final = "finalize.material_variants_failed"
_WHITE: Final = (1.0, 1.0, 1.0, 1.0)
_ENTRY_REMEDIATION: Final = (
    "Fix the material variant in the asset's material variant declaration (each needs a name, a "
    "material named M_<Name>_<Part>, and an optional Tint of 3 or 4 numbers), then rerun export."
)


def _invalid_entry(detail: str) -> PipelineError:
    return PipelineError(
        code="import_godot.mismatch",
        message=f"A declared material variant is malformed: {detail}",
        remediation=_ENTRY_REMEDIATION,
        stage="import_godot",
    )


def check_entry(entry: Mapping[str, Any]) -> None:
    """Raise ``import_godot.mismatch`` unless ``entry`` has the fields writing a ``.tres`` reads."""
    for field in ("name", "material"):
        value = entry.get(field)
        if not isinstance(value, str) or not value:
            raise _invalid_entry(f"{field} must be a non-empty string in {dict(entry)}")
    base_color = entry.get("base_color")
    if base_color is not None and not isinstance(base_color, str):
        raise _invalid_entry(f"base_color must be a file name or null in {dict(entry)}")
    parameters = entry.get("parameters")
    if parameters is None:
        return
    if not isinstance(parameters, dict):
        raise _invalid_entry(f"parameters must be an object in {dict(entry)}")
    tint = cast(dict[str, object], parameters).get("Tint")
    if tint is None:
        return
    if (
        not isinstance(tint, list)
        or len(tint) not in (3, 4)
        or not all(
            isinstance(item, (int, float)) and not isinstance(item, bool)
            for item in cast(list[object], tint)
        )
    ):
        raise _invalid_entry(f"Tint must be 3 or 4 numbers in {dict(entry)}")


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


def plan_variant_materials(
    project: Path,
    folder: Path,
    name: str,
    entries: Sequence[Mapping[str, Any]],
) -> list[tuple[Path, str]]:
    """Validate every entry and return each ``.tres`` path with its text. Writes nothing."""
    planned: list[tuple[Path, str]] = []
    for entry in entries:
        check_entry(entry)
        planned.append(
            (folder / resource_name(entry), render_material(project, folder, name, entry))
        )
    return planned


def write_planned(folder: Path, planned: Sequence[tuple[Path, str]]) -> list[Path]:
    """Write the planned ``.tres`` files and remove the ones an earlier run wrote but no longer
    declares. Returns the written paths.

    Only names listed in ``.nmg-material-variants.json`` are candidates for removal, so a
    ``.tres`` someone made by hand in the folder stays.
    """
    written: list[Path] = []
    for path, text in planned:
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
        written.append(path)
    keep = {path.name for path in written}
    manifest = folder / WRITTEN_MANIFEST
    for stale in sorted(set(_written_before(manifest)) - keep):
        (folder / stale).unlink(missing_ok=True)
    if written or manifest.exists():
        manifest.write_text(json.dumps(sorted(keep), indent=2) + "\n", encoding="utf-8")
    return written


def write_variant_materials(
    project: Path,
    folder: Path,
    name: str,
    entries: Sequence[Mapping[str, Any]],
) -> list[Path]:
    """Validate, then write one ``.tres`` per entry into ``folder`` (see ``write_planned``)."""
    return write_planned(folder, plan_variant_materials(project, folder, name, entries))


def _written_before(manifest: Path) -> list[str]:
    """The ``.tres`` names an earlier run wrote; an unreadable manifest lists none."""
    try:
        data: Any = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [
        Path(item).name
        for item in cast(list[object], data)
        if isinstance(item, str) and item.endswith(".tres")
    ]


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
    "check_entry",
    "list_material_variants",
    "plan_variant_materials",
    "render_material",
    "resource_name",
    "sidecar_entries",
    "write_planned",
    "write_variant_materials",
]
