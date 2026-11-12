"""Finalize step runners for the Blender side: validate, bake, variants, export, export_anims, and
reimport (#69, #138).

run_step returns the envelope the host reads. Each runner returns (summary, outputs). A
ContractError, BakeError, VariantError, BudgetOverrideError, or AnimError becomes a failed envelope
whose code starts with the step name. Other exceptions propagate to
scripts/blender/finalize_entry.py, which writes a best-effort envelope and exits 2.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final

import bpy

from ..bake_core import BakeError, bake_asset
from ..contract_core import ContractError, reimport_check, validate_asset
from ..contract_core.terrain import TERRAIN_CLASS
from ..terrain_core.export import export_terrain
from ..terrain_core.reimport import terrain_reimport_check, write_height_samples
from ..terrain_core.variants import DESKTOP, MOBILE, TerrainVariant, terrain_variants
from ..utils.budgets import BudgetOverrideError, resolve_budget
from ..variants_core.assets import (
    asset_meshes,
    desktop_export_objects,
    distinct_materials,
    require_export_root,
    validate_inputs,
)
from ..variants_core.cleanup import cleanup_desktop
from ..variants_core.errors import VariantError
from ..variants_core.export import export_variants
from ..variants_core.material_variants import export_material_variants
from ..variants_core.mobile import build_mobile
from ..variants_core.sidecars import write_sidecars
from ..variants_core.textures import check_baked_material, max_texture_px, source_images
from . import anims
from .anims import AnimError

SCHEMA_VERSION: Final = 1
STEPS: Final[tuple[str, ...]] = (
    "validate",
    "bake",
    "variants",
    "export",
    "export_anims",
    "reimport",
)
_SCENE_STEPS: Final = frozenset({"validate", "bake", "variants", "export", "export_anims"})
_VARIANTS: Final[tuple[str, ...]] = ("Desktop", "Mobile")
_DEFAULT_SAMPLES: Final = 32

Runner = Callable[[Mapping[str, Any], Path, Mapping[str, Any] | None], tuple[str, dict[str, Any]]]


def run_step(
    step: str,
    request: Mapping[str, Any],
    job_dir: str | Path,
    inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one finalize step in the open Blender process and return its envelope.

    request holds collection, category, asset_class, export_root, blend, budgets_path, and device,
    plus the optional samples (bake sample count, default 32). inputs carries an upstream step's
    outputs when the caller has them: the variants outputs for export, and the export outputs
    (under "variants") for reimport. When inputs is None, each step reads the envelope it needs
    from job_dir.
    """
    job = Path(job_dir)
    job.mkdir(parents=True, exist_ok=True)
    runner = _RUNNERS.get(step)
    if runner is None:
        return _failed(
            step,
            "finalize.unknown_step",
            f"{step!r} is not a finalize step.",
            f"Use one of: {', '.join(STEPS)}.",
        )
    collection = str(request.get("collection", ""))
    if step in _SCENE_STEPS and bpy.data.collections.get(collection) is None:
        return _failed(
            step,
            "finalize.collection_not_found",
            f"No collection named {collection!r} is in the open file.",
            "Open the file that holds the asset, or set collection to the name of its collection.",
        )

    _progress(step, 0.0, "started")
    try:
        summary, outputs = runner(request, job, inputs)
    except (ContractError, BakeError, VariantError, BudgetOverrideError, AnimError) as error:
        _progress(step, 1.0, error.message)
        return _failed(step, _step_code(step, error.code), error.message, error.remediation)
    _progress(step, 1.0, summary)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "step": step,
        "ok": True,
        "summary": summary,
        "outputs": outputs,
        "error": None,
    }


def _validate(
    request: Mapping[str, Any], job: Path, inputs: Mapping[str, Any] | None
) -> tuple[str, dict[str, Any]]:
    collection = str(request["collection"])

    def report_progress(fraction: float, message: str) -> None:
        # run_step emits the 0.0 and 1.0 lines, so the checks map strictly inside (0, 1) (#133).
        _progress("validate", 0.01 + 0.98 * fraction, message)

    # The authored asset is validated without the material rules, which the bake produces (#69).
    report = validate_asset(
        collection,
        str(request["asset_class"]),
        _budgets_path(request),
        authored=True,
        material_variants_path=_material_variants_path(request),
        progress=report_progress,
    )
    path = job / "validate.report.json"
    _write_json(path, report)
    if report["passed"]:
        summary = f"{collection} passed the contract"
    else:
        summary = f"{collection} has {len(report['findings'])} contract finding(s)"
    return summary, {"report": str(path)}


def _bake(
    request: Mapping[str, Any], job: Path, inputs: Mapping[str, Any] | None
) -> tuple[str, dict[str, Any]]:
    collection = str(request["collection"])
    result = bake_asset(
        collection,
        str(request["asset_class"]),
        job / "bake",
        _budgets_path(request),
        str(request.get("device", "GPU")),
        int(request.get("samples", _DEFAULT_SAMPLES)),
    )
    blend = _save_copy(job / "bake.blend")
    state = "cache hit" if result.get("cache_hit") else "baked"
    return f"{collection}: {state}", {"blend": str(blend), "bake": result}


def _variants(
    request: Mapping[str, Any], job: Path, inputs: Mapping[str, Any] | None
) -> tuple[str, dict[str, Any]]:
    collection = str(request["collection"])
    if str(request["asset_class"]) == TERRAIN_CLASS:
        return _terrain_variants(collection, request, job)
    budget = resolve_budget(str(request["asset_class"]), _budgets_path(request))
    validate_inputs(collection, budget)
    desktop_materials = distinct_materials(desktop_export_objects(bpy.data.collections[collection]))
    desktop_px = max_texture_px(list(source_images(desktop_materials).values()))
    cleanup = cleanup_desktop(collection)
    mobile = build_mobile(collection, budget)
    blend = _save_copy(job / "variants.blend")
    metrics = {
        "budget": budget,
        "desktop": {
            "tris": cleanup["tris_after"],
            "max_texture_px": desktop_px,
            "materials": len(desktop_materials),
        },
        "mobile": {
            "tris": mobile["tris"],
            "lod_tris": mobile["lod_tris"],
            "lod_levels": mobile["lod_levels"],
            "max_texture_px": mobile["max_texture_px"],
            "materials": mobile["materials"],
        },
    }
    tris = {
        "Desktop": {"tris": cleanup["tris_after"], "objects": cleanup["objects"]},
        "Mobile": {
            "tris": mobile["tris"],
            "lod_tris": mobile["lod_tris"],
            "lod_levels": mobile["lod_levels"],
        },
    }
    summary = f"{collection}: Desktop {cleanup['tris_after']} tris, Mobile {mobile['tris']} tris"
    return summary, {"blend": str(blend), "tris": tris, "metrics": metrics}


def _export(
    request: Mapping[str, Any], job: Path, inputs: Mapping[str, Any] | None
) -> tuple[str, dict[str, Any]]:
    collection = str(request["collection"])
    category = str(request["category"])
    asset_class = str(request["asset_class"])
    export_root = str(request["export_root"])
    budgets_path = _budgets_path(request)
    if asset_class == TERRAIN_CLASS:
        return _export_terrain(collection, category, export_root, budgets_path, job)
    require_export_root(export_root)
    budget = resolve_budget(asset_class, budgets_path)
    metrics = _upstream_metrics(inputs, job)

    variant_root = Path(export_root) / category / collection
    report = validate_asset(
        collection,
        asset_class,
        budgets_path,
        material_variants_path=_material_variants_path(request),
    )
    # One validation covers both variants; reimport_check filters the snapshot by variant.
    pre_reports = {}
    for variant in _VARIANTS:
        path = job / f"export.pre-report-{variant}.json"
        _write_json(path, report)
        pre_reports[variant] = str(path)
    outputs: dict[str, Any] = {
        "variants": {
            variant: {"dir": str(variant_root / variant), "pre_report": pre_reports[variant]}
            for variant in _VARIANTS
        },
        "sidecar": str(variant_root / "nmg-variants.json"),
        "exported": False,
    }
    if not report["passed"]:
        summary = (
            f"{collection}: pre-export contract failed with {len(report['findings'])} "
            "finding(s); nothing exported"
        )
        return summary, outputs

    exported = export_variants(collection, category, export_root)
    material_variants = None
    if "material_variants" in report:
        material_variants = export_material_variants(
            collection, variant_root, report["material_variants"]
        )
    payload = _sidecar_payload(
        collection, category, asset_class, budget, metrics, exported, material_variants
    )
    write_sidecars(variant_root, payload)
    outputs.update(
        {
            "exported": True,
            "fbx": {"Desktop": str(exported["desktop_fbx"]), "Mobile": str(exported["mobile_fbx"])},
            "texture_bytes": {
                "Desktop": exported["desktop_texture_bytes"],
                "Mobile": exported["mobile_texture_bytes"],
            },
        }
    )
    return f"{collection}: exported Desktop and Mobile to {variant_root}", outputs


def _export_anims(
    request: Mapping[str, Any], job: Path, inputs: Mapping[str, Any] | None
) -> tuple[str, dict[str, Any]]:
    """Probe the rig's clips, or export the named ones (#138).

    ``inputs.mode`` is ``probe`` (the default, which writes nothing) or ``export``, which writes one
    FBX per name in ``inputs.clips`` into ``<export_root>/<Category>/<Name>/Animations``.
    """
    collection = str(request["collection"])
    mode = str((inputs or {}).get("mode", "probe"))
    if mode == "probe":
        report = anims.probe(collection)
        count = len(report["clips"])
        return f"{collection}: {count} clip(s) on the rig", report
    if mode == "export":
        names = [str(name) for name in (inputs or {}).get("clips", [])]
        out_dir = Path(str(request["export_root"])) / str(request["category"]) / collection
        records = anims.export_clips(collection, names, out_dir / anims.ANIMATIONS_DIR)
        return f"{collection}: exported {len(records)} clip(s)", {"clips": records}
    raise AnimError(
        "export_anims.bad_mode",
        f"export_anims mode {mode!r} is not probe or export.",
        "Call the step with mode probe or export.",
    )


def _reimport(
    request: Mapping[str, Any], job: Path, inputs: Mapping[str, Any] | None
) -> tuple[str, dict[str, Any]]:
    source = inputs if inputs is not None else _read_outputs(job, "export", "reimport")
    variants = source.get("variants")
    if not isinstance(variants, Mapping):
        raise ContractError(
            "reimport.variants_missing",
            "The reimport step has no export outputs with a variants map.",
            "Run the export step first, or pass its outputs as inputs.",
        )
    reports: dict[str, str] = {}
    findings = 0
    for variant in _VARIANTS:
        spec = variants.get(variant)
        if not isinstance(spec, Mapping):
            raise ContractError(
                "reimport.variant_missing",
                f"The export outputs have no {variant} entry.",
                "Run the export step for both variants before reimport.",
            )
        _fresh_scene()
        if str(request.get("asset_class")) == TERRAIN_CLASS:
            report = terrain_reimport_check(str(spec["dir"]), str(spec["pre_report"]))
        else:
            report = reimport_check(str(spec["dir"]), str(spec["pre_report"]))
        path = job / f"reimport.{variant}.json"
        _write_json(path, report)
        reports[variant] = str(path)
        findings += len(report["findings"])
    if findings == 0:
        summary = "re-import passed for Desktop and Mobile"
    else:
        summary = f"re-import reported {findings} finding(s)"
    return summary, {"reports": reports}


def _terrain_budgets(budgets_path: str | None) -> dict[str, dict[str, int]]:
    """The terrain budget for each variant, keyed desktop and mobile, with overrides merged in."""
    return {
        "desktop": resolve_budget(TERRAIN_CLASS, budgets_path, "desktop"),
        "mobile": resolve_budget(TERRAIN_CLASS, budgets_path, "mobile"),
    }


def _terrain_variants(
    collection: str, request: Mapping[str, Any], job: Path
) -> tuple[str, dict[str, Any]]:
    """Build the terrain Desktop and Mobile variants (#154, AC3). The scene itself is unchanged."""
    budgets = _terrain_budgets(_budgets_path(request))
    for material in distinct_materials(asset_meshes(bpy.data.collections[collection])):
        check_baked_material(material)
    variants = terrain_variants(collection, budgets)
    blend = _save_copy(job / "variants.blend")
    metrics = {
        "terrain": True,
        DESKTOP.lower(): variants[DESKTOP].metrics(),
        MOBILE.lower(): variants[MOBILE].metrics(),
    }
    mobile = variants[MOBILE]
    summary = (
        f"{collection}: Desktop {variants[DESKTOP].heightmap_px} px, Mobile "
        f"{mobile.heightmap_px} px with {len(mobile.layers)} layer(s)"
    )
    return summary, {"blend": str(blend), "metrics": metrics}


def _export_terrain(
    collection: str,
    category: str,
    export_root: str,
    budgets_path: str | None,
    job: Path,
) -> tuple[str, dict[str, Any]]:
    """Validate, then write the terrain PNGs and sidecars (#154, AC2, AC6).

    A failing pre-export contract exports nothing. On a pass, each pre-export report also names the
    evaluated height samples that the re-import check compares the decoded PNGs against.
    """
    require_export_root(export_root)
    budget = resolve_budget(TERRAIN_CLASS, budgets_path)
    report = validate_asset(collection, TERRAIN_CLASS, budgets_path)
    variants = (
        terrain_variants(collection, _terrain_budgets(budgets_path)) if report["passed"] else None
    )
    variant_root = Path(export_root) / category / collection
    pre_reports = {}
    for variant in (DESKTOP, MOBILE):
        payload = dict(report)
        if variants is not None:
            heights = write_height_samples(
                job / f"export.heights-{variant}.f32", variants[variant].heights
            )
            payload["terrain_heights"] = str(heights)
        path = job / f"export.pre-report-{variant}.json"
        _write_json(path, payload)
        pre_reports[variant] = str(path)
    outputs: dict[str, Any] = {
        "variants": {
            variant: {"dir": str(variant_root / variant), "pre_report": pre_reports[variant]}
            for variant in (DESKTOP, MOBILE)
        },
        "sidecar": str(variant_root / "nmg-variants.json"),
        "exported": False,
    }
    if variants is None:
        summary = (
            f"{collection}: pre-export contract failed with {len(report['findings'])} "
            "finding(s); nothing exported"
        )
        return summary, outputs

    exported = export_terrain(collection, category, export_root, variants)
    payload = _terrain_sidecar_payload(collection, category, budget, variants, exported)
    write_sidecars(variant_root, payload)
    outputs.update(
        {
            "exported": True,
            "heightmap": {
                DESKTOP: str(exported["desktop_heightmap"]),
                MOBILE: str(exported["mobile_heightmap"]),
            },
            "texture_bytes": {
                DESKTOP: exported["desktop_texture_bytes"],
                MOBILE: exported["mobile_texture_bytes"],
            },
        }
    )
    return f"{collection}: exported Desktop and Mobile to {variant_root}", outputs


def _terrain_sidecar_payload(
    collection: str,
    category: str,
    budget: Mapping[str, int],
    variants: Mapping[str, TerrainVariant],
    exported: Mapping[str, Any],
) -> dict[str, Any]:
    """nmg-variants.json for terrain: "terrain": true and each variant's fields and samples."""

    def block(variant: str) -> dict[str, Any]:
        return {
            "heightmap": f"{variant}/T_{collection}_Height.png",
            **variants[variant].metrics(),
            "texture_bytes": exported[f"{variant.lower()}_texture_bytes"],
        }

    return {
        "terrain": True,
        "name": collection,
        "category": category,
        "class": TERRAIN_CLASS,
        "budget": dict(budget),
        "desktop": block(DESKTOP),
        "mobile": block(MOBILE),
    }


def _sidecar_payload(
    collection: str,
    category: str,
    asset_class: str,
    budget: Mapping[str, int],
    metrics: Mapping[str, Any],
    exported: Mapping[str, Any],
    material_variants: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    desktop = metrics["desktop"]
    mobile = metrics["mobile"]
    payload: dict[str, Any] = {
        "name": collection,
        "category": category,
        "class": asset_class,
        "budget": dict(budget),
        "desktop": {
            "fbx": f"Desktop/SM_{collection}.fbx",
            "tris": desktop["tris"],
            "texture_bytes": exported["desktop_texture_bytes"],
            "max_texture_px": desktop["max_texture_px"],
            "materials": desktop["materials"],
        },
        "mobile": {
            "fbx": f"Mobile/SM_{collection}.fbx",
            "tris": mobile["tris"],
            "lod_tris": mobile["lod_tris"],
            "lod_levels": mobile["lod_levels"],
            "texture_bytes": exported["mobile_texture_bytes"],
            "max_texture_px": mobile["max_texture_px"],
            "materials": mobile["materials"],
        },
    }
    # The key exists only when the asset declares material variants (#148, AC4 and AC7).
    if material_variants is not None:
        payload["material_variants"] = dict(material_variants)
    return payload


def _material_variants_path(request: Mapping[str, Any]) -> str | None:
    value = request.get("material_variants_path")
    return str(value) if value else None


def _upstream_metrics(inputs: Mapping[str, Any] | None, job: Path) -> dict[str, Any]:
    source = inputs if inputs is not None else _read_outputs(job, "variants", "export")
    metrics = source.get("metrics")
    if not isinstance(metrics, Mapping):
        raise ContractError(
            "export.upstream_missing",
            "The export step has no variants metrics to write the sidecar from.",
            "Run the variants step first, or pass its outputs as inputs.",
        )
    return dict(metrics)


def _read_outputs(job: Path, upstream: str, for_step: str) -> dict[str, Any]:
    path = job / f"{upstream}.json"
    if not path.is_file():
        raise ContractError(
            f"{for_step}.upstream_missing",
            f"{path.name} is not in the job directory, so the {upstream} outputs are unknown.",
            f"Run the {upstream} step in this job first, or pass its outputs as inputs.",
        )
    envelope = json.loads(path.read_text(encoding="utf-8"))
    outputs = envelope.get("outputs")
    if not isinstance(outputs, dict):
        raise ContractError(
            f"{for_step}.upstream_missing",
            f"{path.name} has no outputs.",
            f"Rerun the {upstream} step in this job.",
        )
    return outputs


def _fresh_scene() -> None:
    if any(obj.type == "MESH" for obj in bpy.data.objects):
        bpy.ops.wm.read_factory_settings(use_empty=True)


def _save_copy(path: Path) -> Path:
    """Save the open scene to path as a copy, so the session's own file path is unchanged."""
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(path), copy=True)
    return path


def _budgets_path(request: Mapping[str, Any]) -> str | None:
    value = request.get("budgets_path")
    return str(value) if value else None


def _step_code(step: str, code: str) -> str:
    """Return code as a dotted code that starts with the step name (the envelope contract)."""
    if code.startswith(f"{step}."):
        return code
    if code.startswith("variants."):
        return f"{step}.{code.removeprefix('variants.')}"
    return f"{step}.{code}"


def _failed(step: str, code: str, message: str, remediation: str) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "step": step,
        "ok": False,
        "summary": message,
        "outputs": {},
        "error": {"code": code, "message": message, "remediation": remediation},
    }


def _progress(step: str, progress: float, message: str) -> None:
    line = {"state": "running", "step": step, "progress": round(progress, 3), "message": message}
    print("NMG_PROGRESS " + json.dumps(line, sort_keys=True), flush=True)


def _write_json(path: Path, data: Any) -> None:
    text = json.dumps(data, indent=2, sort_keys=True, default=str)
    path.write_text(text + "\n", encoding="utf-8")


_RUNNERS: Final[dict[str, Runner]] = {
    "validate": _validate,
    "bake": _bake,
    "variants": _variants,
    "export": _export,
    "export_anims": _export_anims,
    "reimport": _reimport,
}
