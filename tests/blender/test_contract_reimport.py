"""Re-import check under Blender headless: AC3 (SCN003).

Each test exports the compliant Crate, then runs the check in a fresh headless Blender process
through run_isolated, the same path the operator takes.
"""

from __future__ import annotations

import importlib
import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .contract_fixtures import build_crate, clear_scene, export_crate  # noqa: E402
from .rig_fixtures import add_baked_hero_material, build_hero, reset_scene  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_scene() -> Iterator[None]:
    yield
    clear_scene()


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core")


@pytest.fixture()
def exported(core: Any, tmp_path: Path) -> tuple[Path, Path]:
    """Return (<export>/Props/Crate, pre-export report path) for the compliant Crate."""
    build_crate()
    pre_report = core.validate_asset("Crate", "standard_prop")
    variant_root = export_crate(tmp_path)
    report_file = tmp_path / "pre-report.json"
    report_file.write_text(json.dumps(pre_report), encoding="utf-8")
    return variant_root, report_file


def test_ac3_reimport_passes_after_export(core: Any, exported: tuple[Path, Path]) -> None:
    variant_root, pre_report = exported

    report = core.run_isolated(variant_root / "Desktop", pre_report)

    assert report["kind"] == "reimport"
    assert report["passed"], report["findings"]
    assert report["findings"] == []
    assert "SM_Crate" in report["snapshot"]


def test_ac3_reimport_passes_for_the_mobile_variant(core: Any, exported: tuple[Path, Path]) -> None:
    variant_root, pre_report = exported

    report = core.run_isolated(variant_root / "Mobile", pre_report)

    assert report["passed"], report["findings"]


def test_ac3_deleted_texture_fails_naming_the_file(core: Any, exported: tuple[Path, Path]) -> None:
    variant_root, pre_report = exported
    (variant_root / "Desktop" / "T_Crate_Body_BC.png").unlink()

    report = core.run_isolated(variant_root / "Desktop", pre_report)

    assert not report["passed"]
    missing = [item for item in report["findings"] if item["rule"] == "reimport.texture_missing"]
    assert missing, report["findings"]
    assert missing[0]["target"] == "T_Crate_Body_BC.png"
    assert "T_Crate_Body_BC.png" in missing[0]["message"]


def test_ac3_reimport_refuses_a_session_scene_with_meshes(
    core: Any, exported: tuple[Path, Path]
) -> None:
    variant_root, pre_report = exported
    report_data = json.loads(pre_report.read_text(encoding="utf-8"))

    with pytest.raises(core.ContractError) as raised:
        core.reimport_check(variant_root / "Desktop", report_data)

    assert raised.value.code == "reimport.session_not_fresh"
    assert raised.value.remediation


# ---------------------------------------------------------------------------
# SCN005: the re-import check covers rigged variants (#102)
# ---------------------------------------------------------------------------


@pytest.fixture()
def rigged_exported(core: Any, enabled_addon: str, tmp_path: Path) -> tuple[Path, Path]:
    """Return (<export>/Characters/Hero, pre-export report path) for a rigged Hero."""
    rig_core = importlib.import_module(f"{enabled_addon}.rig_core")
    variants = importlib.import_module(f"{enabled_addon}.variants_core")
    reset_scene()
    assert rig_core.rig_humanoid("Hero", "humanoid", build_hero())["status"] == "ok"
    add_baked_hero_material()
    variants.generate_variants("Hero", "Characters", "character", str(tmp_path))
    pre_report = core.validate_asset("Hero", "character")
    report_file = tmp_path / "pre-report.json"
    report_file.write_text(json.dumps(pre_report), encoding="utf-8")
    return tmp_path / "Characters" / "Hero", report_file


def test_scn005_reimport_imports_every_lod_file_and_passes(
    core: Any, rigged_exported: tuple[Path, Path]
) -> None:
    variant_root, pre_report = rigged_exported

    report = core.run_isolated(variant_root / "Mobile", pre_report)

    assert report["kind"] == "reimport"
    assert report["passed"], report["findings"]
    assert {"SM_Hero", "SM_Hero_LOD1", "SM_Hero_LOD2"} <= set(report["snapshot"])


def test_scn005_mesh_exported_without_its_skin_is_reported(
    core: Any, rigged_exported: tuple[Path, Path], tmp_path: Path
) -> None:
    variant_root, pre_report = rigged_exported
    bare = tmp_path / "bare" / "Desktop"
    bare.mkdir(parents=True)
    root = bpy.data.objects["SM_Hero"]
    bpy.ops.object.select_all(action="DESELECT")
    root.select_set(True)
    bpy.context.view_layer.objects.active = root
    bpy.ops.export_scene.fbx(
        filepath=str(bare / "SM_Hero.fbx"), use_selection=True, object_types={"MESH"}
    )
    for image in ("T_Hero_Body_BC", "T_Hero_Body_N", "T_Hero_Body_ORM"):
        shutil.copy(variant_root / "Desktop" / f"{image}.png", bare / f"{image}.png")

    report = core.run_isolated(bare, pre_report)

    skin = [item for item in report["findings"] if item["rule"] == "reimport.skin_missing"]
    assert skin, report["findings"]
    assert skin[0]["target"] == "SM_Hero"
    assert not report["passed"]
