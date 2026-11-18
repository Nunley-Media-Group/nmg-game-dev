"""The finalize ``import_godot`` step for a mesh asset (#249 FR1, AC1, AC2).

``import_variants`` lands both exported variants in the Godot project:

1. Writes each variant's material-variant ``.tres`` files (``material_variants.py``).
2. Runs ``godot --headless --import`` once for the project.
3. Runs ``probe_asset.gd`` once per variant on ``<Variant>/<Name>.glb``.
4. Compares the probe with that variant's ``nmg-asset.json`` ``meshes``: the same mesh names,
   equal ``tris``, equal ``material_slots``, and bounds within 0.001 m. Any difference raises
   ``import_godot.mismatch`` naming the mesh and the field.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, NoReturn, cast

from nmg_game_dev.pipeline.errors import PipelineError

from .material_variants import sidecar_entries, write_variant_materials
from .project import res_path
from .runner import GodotRunner, import_project, run_probe

VARIANTS: Final = ("Desktop", "Mobile")
ASSET_SIDECAR: Final = "nmg-asset.json"
PROBE: Final = "probe_asset.gd"
BOUNDS_TOLERANCE_M: Final = 0.001
_STAGE: Final = "import_godot"
_MISMATCH_REMEDIATION: Final = (
    "Re-export the asset so the .glb and nmg-asset.json come from the same run, then rerun "
    "import_godot. If it persists, open the .glb in Godot and compare its meshes with the sidecar."
)


def import_variants(
    runner: GodotRunner,
    project: Path,
    *,
    name: str,
    variant_dirs: Mapping[str, Path],
    sidecar: Mapping[str, Any] | None = None,
    timeout: float | None = None,
) -> dict[str, dict[str, Any]]:
    """Import and verify both variants. Returns ``{Desktop|Mobile: {resource_path, meshes, ...}}``.

    ``variant_dirs`` maps ``Desktop`` and ``Mobile`` to their export folders inside ``project``.
    ``sidecar`` is the parsed ``nmg-variants.json`` (its ``material_variants`` lists are used).
    """
    expected: dict[str, list[dict[str, Any]]] = {}
    materials: dict[str, list[str]] = {}
    for variant in VARIANTS:
        folder = variant_dirs[variant]
        expected[variant] = _expected_meshes(folder / ASSET_SIDECAR, variant)
        glb = folder / f"{name}.glb"
        if not glb.is_file():
            raise PipelineError(
                code="import_godot.mismatch",
                message=f"{variant} has no exported {glb.name} in {folder}.",
                remediation="Rerun the export step so both variants hold <Name>.glb.",
                stage=_STAGE,
            )
        written = write_variant_materials(
            project, folder, name, sidecar_entries(sidecar or {}, variant)
        )
        materials[variant] = [res_path(project, path) for path in written]

    import_project(runner, project, timeout=timeout)

    results: dict[str, dict[str, Any]] = {}
    for variant in VARIANTS:
        resource = res_path(project, variant_dirs[variant] / f"{name}.glb")
        probe = run_probe(
            runner,
            project,
            PROBE,
            {"glb": resource},
            error_code="import_godot.import_failed",
            timeout=timeout,
        )
        measured = _measured_meshes(probe, variant)
        compare_meshes(variant, expected[variant], measured)
        results[variant] = {
            "resource_path": resource,
            "meshes": measured,
            "material_variants": materials[variant],
        }
    return results


def compare_meshes(
    variant: str,
    expected: Sequence[Mapping[str, Any]],
    measured: Sequence[Mapping[str, Any]],
) -> None:
    """Raise ``import_godot.mismatch`` naming the mesh and field at the first difference."""
    wanted = {str(mesh["name"]): mesh for mesh in expected}
    found = {str(mesh["name"]): mesh for mesh in measured}
    missing = sorted(set(wanted) - set(found))
    if missing:
        _mismatch(variant, missing[0], "name", "present in the import", "missing")
    extra = sorted(set(found) - set(wanted))
    if extra:
        _mismatch(variant, extra[0], "name", "absent (not in nmg-asset.json)", "imported")
    for mesh_name in sorted(wanted):
        want, got = wanted[mesh_name], found[mesh_name]
        for field in ("tris", "material_slots"):
            if int(want[field]) != int(got[field]):
                _mismatch(variant, mesh_name, field, want[field], got[field])
        for corner in ("min", "max"):
            want_corner = _vector(want, corner)
            got_corner = _vector(got, corner)
            pairs = zip(want_corner, got_corner, strict=True)
            if any(abs(a - b) > BOUNDS_TOLERANCE_M for a, b in pairs):
                _mismatch(variant, mesh_name, f"bounds.{corner}", want_corner, got_corner)


def _expected_meshes(path: Path, variant: str) -> list[dict[str, Any]]:
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PipelineError(
            code="import_godot.mismatch",
            message=f"{variant} has no readable {ASSET_SIDECAR} at {path}: {error}",
            remediation="Rerun the export step so each variant folder holds nmg-asset.json.",
            stage=_STAGE,
        ) from error
    meshes = data.get("meshes") if isinstance(data, dict) else None
    if not isinstance(meshes, list) or not meshes:
        raise PipelineError(
            code="import_godot.mismatch",
            message=f"{path} lists no meshes to compare the import with.",
            remediation="Rerun the export step with the current add-on so nmg-asset.json lists "
            "each mesh's name, tris, material_slots and bounds.",
            stage=_STAGE,
        )
    return [_mesh_record(item, f"{path}") for item in cast(list[object], meshes)]


def _measured_meshes(probe: Mapping[str, Any], variant: str) -> list[dict[str, Any]]:
    meshes = probe.get("meshes")
    if not isinstance(meshes, list):
        raise PipelineError(
            code="import_godot.import_failed",
            message=f"The {variant} probe reported no meshes list.",
            remediation="Read the Godot output, confirm probe_asset.gd ran on the .glb, then "
            "rerun.",
            stage=_STAGE,
        )
    return [_mesh_record(item, f"the {variant} probe") for item in cast(list[object], meshes)]


def _mesh_record(item: object, source: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise _malformed(source, "a mesh entry is not an object")
    entry = cast(dict[str, Any], item)
    try:
        bounds = entry["bounds"]
        low = [float(value) for value in bounds["min"]]
        high = [float(value) for value in bounds["max"]]
        mesh_name = str(entry["name"])
        tris = int(entry["tris"])
        slots = int(entry["material_slots"])
    except (KeyError, TypeError, ValueError) as error:
        raise _malformed(source, f"a mesh entry lacks {error}") from error
    if len(low) != 3 or len(high) != 3:
        raise _malformed(source, f"mesh {mesh_name} bounds are not [x, y, z]")
    return {
        "name": mesh_name,
        "tris": tris,
        "material_slots": slots,
        "bounds": {"min": low, "max": high},
    }


def _vector(mesh: Mapping[str, Any], corner: str) -> list[float]:
    return [float(value) for value in mesh["bounds"][corner]]


def _malformed(source: str, detail: str) -> PipelineError:
    return PipelineError(
        code="import_godot.mismatch",
        message=f"{source} is malformed: {detail}.",
        remediation=_MISMATCH_REMEDIATION,
        stage=_STAGE,
    )


def _mismatch(variant: str, mesh: str, field: str, expected: object, measured: object) -> NoReturn:
    raise PipelineError(
        code="import_godot.mismatch",
        message=f"{variant} mesh {mesh} {field}: expected {expected}, imported {measured}.",
        remediation=_MISMATCH_REMEDIATION,
        stage=_STAGE,
    )


__all__ = ["BOUNDS_TOLERANCE_M", "compare_meshes", "import_variants"]
