"""A reduced asset through finalize, and load-back of its <Name>_High collection (#139 AC10, AC2).

run_step runs validate, bake, variants, export, and reimport on a reduced standard_prop and a
reduced environment_piece. Each must pass with the atlas kept. The reimport runs in a fresh Blender
subprocess, as production does. Run with scripts/run-blender-tests.sh; plain CPython skips it.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .contract_fixtures import clear_scene  # noqa: E402
from .reduce_fixtures import build_high_poly, reduce_budgets_file  # noqa: E402

ENTRY = Path(__file__).resolve().parents[2] / "scripts" / "blender" / "finalize_entry.py"


@pytest.fixture(autouse=True)
def _isolated_scene(enabled_addon: str) -> Any:  # noqa: ARG001 - ordering dependency
    clear_scene()
    yield
    clear_scene()


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.finalize_core")


@pytest.fixture()
def reduce_core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.reduce_core")


def _request(tmp_path: Path, asset_class: str, budgets: str) -> dict[str, Any]:
    return {
        "collection": "Crate",
        "category": "Props",
        "asset_class": asset_class,
        "export_root": str(tmp_path / "export"),
        "blend": None,
        "budgets_path": budgets,
        "device": "CPU",
        "samples": 4,
    }


def _job_dir(tmp_path: Path, request: dict[str, Any]) -> Path:
    job = tmp_path / "job"
    job.mkdir(parents=True, exist_ok=True)
    (job / "request.json").write_text(json.dumps(request), encoding="utf-8")
    return job


def _record(job: Path, envelope: dict[str, Any]) -> None:
    (job / f"{envelope['step']}.json").write_text(json.dumps(envelope), encoding="utf-8")


def _run_reimport(job: Path) -> None:
    completed = subprocess.run(
        [
            bpy.app.binary_path,
            "--background",
            "--factory-startup",
            "--python",
            str(ENTRY),
            "--",
            "reimport",
            "--job-dir",
            str(job),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    envelope = json.loads((job / "reimport.json").read_text(encoding="utf-8"))
    assert envelope["ok"] is True, envelope["error"]
    for variant in ("Desktop", "Mobile"):
        report = json.loads(Path(envelope["outputs"]["reports"][variant]).read_text("utf-8"))
        assert report["passed"] is True, (variant, report["findings"])


def _finalize_chain(core: Any, tmp_path: Path, asset_class: str, budgets: str) -> dict[str, Any]:
    """Validate, bake, variants, export, and reimport the reduced asset; return the bake result."""
    request = _request(tmp_path, asset_class, budgets)
    job = _job_dir(tmp_path, request)

    validate = core.run_step("validate", request, job)
    _record(job, validate)
    assert validate["ok"] is True, validate["error"]

    bake = core.run_step("bake", request, job)
    _record(job, bake)
    assert bake["ok"] is True, bake["error"]

    variants = core.run_step("variants", request, job)
    _record(job, variants)
    assert variants["ok"] is True, variants["error"]

    export = core.run_step("export", request, job)
    _record(job, export)
    assert export["ok"] is True, export["error"]
    pre_report = json.loads(
        Path(export["outputs"]["variants"]["Desktop"]["pre_report"]).read_text(encoding="utf-8")
    )
    assert export["outputs"]["exported"] is True, pre_report["findings"]
    names = set(pre_report["snapshot"])
    assert not any(name.endswith("_High") for name in names), names
    assert {"SM_Crate", "SM_Crate_Turret", "SM_Crate_Lid"} <= names

    _run_reimport(job)
    return bake["outputs"]["bake"]


def test_reduced_standard_prop_finalizes_through_reimport_ac10(
    core: Any, reduce_core: Any, tmp_path: Path
) -> None:
    build_high_poly("Crate", contract=True)
    budgets = reduce_budgets_file(tmp_path)
    reduced = reduce_core.reduce_asset(
        "Crate", "standard_prop", budgets, device="CPU", out_dir=tmp_path / "reduce"
    )
    assert reduced["state"] == "reduced"

    bake = _finalize_chain(core, tmp_path, "standard_prop", budgets)

    assert bake["mode"] == "unique"
    assert bake["cache_hit"] is False


def test_reduced_environment_piece_keeps_its_atlas_through_reimport_ac10(
    core: Any, reduce_core: Any, tmp_path: Path
) -> None:
    # The texel-density rule still applies to a reduced environment piece. At the test's 256 px
    # Desktop size, a 0.1 scale asset reaches about 450 px/m, above the 256 px/m minimum.
    build_high_poly("Crate", contract=True, scale=0.1)
    budgets = reduce_budgets_file(tmp_path)
    reduced = reduce_core.reduce_asset(
        "Crate", "environment_piece", budgets, device="CPU", out_dir=tmp_path / "reduce"
    )
    assert reduced["state"] == "reduced"
    assert bpy.data.collections["Crate"]["nmg_reduced"] is True

    bake = _finalize_chain(core, tmp_path, "environment_piece", budgets)

    assert bake["mode"] == "unique", "a tagged environment piece must bake in unique mode"
    assert bake["merged"] is False


def test_load_back_with_the_high_suffix_restores_the_hidden_originals_ac2(
    core: Any, reduce_core: Any, tmp_path: Path
) -> None:
    build_high_poly("Crate")
    reduce_core.reduce_asset(
        "Crate",
        "standard_prop",
        reduce_budgets_file(tmp_path),
        device="CPU",
        out_dir=tmp_path / "reduce",
    )
    reduced_names = sorted(obj.name for obj in bpy.data.collections["Crate_High"].all_objects)
    result_blend = tmp_path / "reduced.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(result_blend), copy=True)

    outcome = core.load_back(str(result_blend), "Crate", core.content_hash("Crate"), ("", "_High"))

    assert outcome["loaded"] is True, outcome
    high = bpy.data.collections["Crate_High"]
    assert high.hide_viewport and high.hide_render
    assert sorted(obj.name for obj in high.all_objects) == reduced_names
    assert outcome["hash"] == core.content_hash("Crate")
    assert not [block.name for block in bpy.data.objects if block.name.startswith("__nmg_old_")]
