"""Re-import check under Blender headless: AC3 (SCN003).

Each test exports the compliant Crate, then runs the check in a fresh headless Blender process
through run_isolated, the same path the operator takes.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .contract_fixtures import build_crate, clear_scene, export_crate  # noqa: E402


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
