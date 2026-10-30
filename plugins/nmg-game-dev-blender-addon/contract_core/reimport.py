"""Re-import check: compare an exported variant with the report written before export.

reimport_check imports the FBX into the calling process, so that process must be fresh (no
meshes in the scene). Sessions call run_isolated, which spawns a fresh headless Blender with
scripts/blender/contract_entry.py and reads back the report it writes.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import bpy
from mathutils import Vector

from .report import ContractError, build_report, finding
from .validate import export_name, object_snapshot, triangle_count

ENTRY_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "blender" / "contract_entry.py"
DIMENSION_TOLERANCE = 1e-3
PIVOT_TOLERANCE = 1e-4
_DIMENSION_FLOOR = 1e-6
_VARIANTS = ("desktop", "mobile")


def reimport_check(
    variant_dir: str | Path, pre_report: str | Path | Mapping[str, Any]
) -> dict[str, Any]:
    """Import SM_<Name>.fbx from variant_dir and compare it with pre_report. Fresh process only."""
    folder = Path(variant_dir)
    variant = folder.name.lower()
    if variant not in _VARIANTS:
        raise ContractError(
            "reimport.variant_unknown",
            f"{folder.name} is not a Desktop or Mobile folder.",
            "Point variant_dir at <Category>/<Name>/Desktop or <Category>/<Name>/Mobile.",
        )
    pre = _load_pre_report(pre_report)
    asset = pre["asset"]
    fbx = folder / f"SM_{asset}.fbx"
    if not fbx.is_file():
        raise ContractError(
            "reimport.fbx_missing",
            f"{fbx} does not exist.",
            "Export the variant before running the re-import check.",
        )
    if any(obj.type == "MESH" for obj in bpy.data.objects):
        raise ContractError(
            "reimport.session_not_fresh",
            "The scene already holds meshes, so the imported FBX would mix with them.",
            "Run the check with run_isolated(), which spawns a fresh headless Blender process.",
        )

    expected = {
        export_name(name): entry
        for name, entry in pre["snapshot"].items()
        if entry["variant"] == variant
    }
    findings = _texture_findings(asset, folder, expected)

    bpy.ops.import_scene.fbx(filepath=str(fbx))
    actual_objects = list(bpy.data.objects)
    actual_meshes = {obj.name: obj for obj in actual_objects if obj.type == "MESH"}
    actual_snapshot = {
        obj.name: object_snapshot(
            obj, variant, triangle_count(obj.data) if obj.type == "MESH" else 0
        )
        for obj in actual_objects
    }

    expected_meshes = {name: entry for name, entry in expected.items() if entry["type"] == "MESH"}
    findings += _name_findings(expected_meshes, actual_meshes, expected)
    findings += _mesh_findings(expected_meshes, actual_meshes)
    findings += _pivot_findings(asset, expected_meshes, actual_meshes)
    return build_report("reimport", asset, pre["class"], findings, actual_snapshot)


def run_isolated(
    variant_dir: str | Path,
    pre_report: str | Path | Mapping[str, Any],
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run reimport_check in a fresh headless Blender process and return the report it writes."""
    if not ENTRY_SCRIPT.is_file():
        raise ContractError(
            "reimport.entry_missing",
            f"{ENTRY_SCRIPT} does not exist.",
            "Run the re-import check from a checkout that contains scripts/blender/"
            "contract_entry.py.",
        )
    workdir = Path(tempfile.mkdtemp(prefix="nmg_reimport_"))
    pre_path = _pre_report_file(pre_report, workdir)
    out = Path(report_path) if report_path is not None else workdir / "reimport-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    command = [
        bpy.app.binary_path,
        "--background",
        "--factory-startup",
        "--python",
        str(ENTRY_SCRIPT),
        "--",
        "reimport",
        "--variant-dir",
        str(variant_dir),
        "--pre-report",
        str(pre_path),
        "--report",
        str(out),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if not out.is_file():
        tail = "\n".join((completed.stderr or completed.stdout).strip().splitlines()[-6:])
        raise ContractError(
            "reimport.isolated_failed",
            f"The fresh Blender process exited {completed.returncode} without writing a report.",
            f"Fix this error, then rerun the check: {tail}",
        )
    data: dict[str, Any] = json.loads(out.read_text(encoding="utf-8"))
    return data


def _load_pre_report(pre_report: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(pre_report, Mapping):
        return dict(pre_report)
    try:
        data: dict[str, Any] = json.loads(Path(pre_report).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ContractError(
            "reimport.report_unreadable",
            f"The pre-export report {pre_report} cannot be read: {error}",
            "Run validate_asset before export and pass the report it writes.",
        ) from error
    return data


def _pre_report_file(pre_report: str | Path | Mapping[str, Any], workdir: Path) -> Path:
    if isinstance(pre_report, Mapping):
        path = workdir / "pre-report.json"
        path.write_text(json.dumps(dict(pre_report), indent=2, sort_keys=True), encoding="utf-8")
        return path
    return Path(pre_report)


def _texture_findings(
    asset: str, folder: Path, expected: dict[str, dict[str, Any]]
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    images = sorted(
        {export_name(image) for entry in expected.values() for image in entry["images"]}
    )
    if not any(name.endswith("_ORM") for name in images):
        findings.append(
            finding(
                "reimport.orm_missing",
                asset,
                f"The pre-export report lists no ORM texture for the {folder.name} variant.",
            )
        )
    for name in images:
        path = folder / f"{name}.png"
        if path.is_file():
            continue
        rule = "reimport.orm_missing" if name.endswith("_ORM") else "reimport.texture_missing"
        findings.append(
            finding(
                rule,
                path.name,
                f"{path.name} is missing from {folder}; the FBX needs it beside the file.",
            )
        )
    return findings


def _name_findings(
    expected_meshes: dict[str, dict[str, Any]],
    actual_meshes: dict[str, bpy.types.Object],
    expected: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for name in sorted(set(expected_meshes) - set(actual_meshes)):
        findings.append(
            finding(
                "reimport.name_mismatch",
                name,
                f"The pre-export report lists mesh {name}, which the FBX does not contain.",
            )
        )
    for name in sorted(set(actual_meshes) - set(expected_meshes)):
        findings.append(
            finding(
                "reimport.name_mismatch",
                name,
                f"The FBX contains mesh {name}, which the pre-export report does not list.",
            )
        )
    materials = sorted(
        {export_name(material) for entry in expected.values() for material in entry["materials"]}
    )
    imported = {material.name for material in bpy.data.materials}
    for name in materials:
        if name not in imported:
            findings.append(
                finding(
                    "reimport.name_mismatch",
                    name,
                    f"Material {name} from the pre-export report is missing from the FBX.",
                )
            )
    return findings


def _mesh_findings(
    expected_meshes: dict[str, dict[str, Any]], actual_meshes: dict[str, bpy.types.Object]
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for name in sorted(set(expected_meshes) & set(actual_meshes)):
        entry = expected_meshes[name]
        obj = actual_meshes[name]
        if "UVMap" not in [layer.name for layer in obj.data.uv_layers]:
            findings.append(
                finding("reimport.uv_missing", name, f"{name} has no UVMap after import.")
            )
        if not _dimensions_match(entry["dimensions"], obj.dimensions):
            findings.append(
                finding(
                    "reimport.dimensions",
                    name,
                    f"{name} dimensions are {_format(obj.dimensions)} after import; the report "
                    f"has {_format(entry['dimensions'])}.",
                )
            )
        imported_tris = triangle_count(obj.data)
        if imported_tris != entry["tris"]:
            findings.append(
                finding(
                    "reimport.tris",
                    name,
                    f"{name} has {imported_tris} triangles after import; the report has "
                    f"{entry['tris']}.",
                )
            )
    return findings


def _pivot_findings(
    asset: str,
    expected_meshes: dict[str, dict[str, Any]],
    actual_meshes: dict[str, bpy.types.Object],
) -> list[dict[str, str]]:
    root_name = f"SM_{asset}"
    root_entry = expected_meshes.get(root_name)
    actual_root = actual_meshes.get(root_name)
    if root_entry is None or actual_root is None:
        return []
    pre_root = Vector(root_entry["origin"])
    post_root = actual_root.matrix_world.translation
    findings: list[dict[str, str]] = []
    for name, entry in sorted(expected_meshes.items()):
        parent = entry["parent"]
        if name == root_name or parent is None or export_name(parent) != root_name:
            continue
        if name not in actual_meshes:
            continue
        pre_offset = Vector(entry["origin"]) - pre_root
        post_offset = actual_meshes[name].matrix_world.translation - post_root
        moved = (pre_offset - post_offset).length
        if moved > PIVOT_TOLERANCE:
            findings.append(
                finding(
                    "reimport.pivot",
                    name,
                    f"{name} pivot moved {moved * 1000:.3f} mm relative to {root_name}; the "
                    "limit is 0.1 mm.",
                )
            )
    return findings


def _dimensions_match(expected: list[float], actual: Vector) -> bool:
    for before, after in zip(expected, actual, strict=True):
        allowed = max(DIMENSION_TOLERANCE * abs(before), _DIMENSION_FLOOR)
        if abs(before - after) > allowed:
            return False
    return True


def _format(values: Any) -> str:
    return "(" + ", ".join(f"{float(value):.4f}" for value in values) + ")"
