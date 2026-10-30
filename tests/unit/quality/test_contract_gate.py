"""Unit tests for the contract report models and gate (#30, AC6 / SCN006)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.quality.contract import (
    ContractGateError,
    ContractReport,
    ReportKind,
    gate,
    load_report,
)

_TRANSFORM = {
    "rule": "transform.root_applied",
    "target": "SM_Crate",
    "message": "Root rotation is (0, 0, 90) degrees; it must be applied.",
    "remediation": "Apply rotation and scale to SM_Crate (Ctrl+A) before export.",
}
_PIVOT = {
    "rule": "pivot.bottom_center",
    "target": "SM_Crate",
    "message": "Origin is 0.4 m above the bottom center.",
    "remediation": "Move the origin to the bottom center at world origin.",
}


def _report_dict(kind: str, passed: bool, findings: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "kind": kind,
        "asset": "Crate",
        "class": "standard_prop",
        "passed": passed,
        "findings": findings,
        "snapshot": {"SM_Crate": {"tris": 12}},
    }


def _report(kind: ReportKind, passed: bool, findings: list[dict[str, str]]) -> ContractReport:
    return ContractReport.model_validate(_report_dict(kind, passed, findings))


@pytest.mark.parametrize("kind", ["contract", "reimport"])
def test_passing_report_returns_without_raising(kind: ReportKind) -> None:
    report = _report(kind, passed=True, findings=[])
    gate(report, kind)


def test_failing_contract_report_raises_contract_failed() -> None:
    report = _report("contract", passed=False, findings=[_TRANSFORM, _PIVOT])

    with pytest.raises(ContractGateError) as info:
        gate(report, "contract")

    error = info.value
    assert error.code == "quality.contract_failed"
    assert error.stage == "quality"
    assert "transform.root_applied SM_Crate" in error.message
    assert "pivot.bottom_center SM_Crate" in error.message
    assert "Apply rotation and scale" in error.remediation
    assert "Move the origin to the bottom center" in error.remediation
    assert error.report is report


def test_failing_reimport_report_raises_reimport_mismatch() -> None:
    finding = {
        "rule": "reimport.texture_missing",
        "target": "T_Crate_Body_BC.png",
        "message": "T_Crate_Body_BC.png is not beside SM_Crate.fbx.",
        "remediation": "Re-export the Desktop variant so its textures are written beside the FBX.",
    }
    report = _report("reimport", passed=False, findings=[finding])

    with pytest.raises(ContractGateError) as info:
        gate(report, "reimport")

    error = info.value
    assert error.code == "quality.reimport_mismatch"
    assert error.stage == "quality"
    assert "reimport.texture_missing T_Crate_Body_BC.png" in error.message
    assert error.report is report


def test_gate_error_is_a_pipeline_error() -> None:
    report = _report("contract", passed=False, findings=[_PIVOT])

    with pytest.raises(PipelineError):
        gate(report, "contract")


def test_failing_report_without_findings_still_raises() -> None:
    report = _report("contract", passed=False, findings=[])

    with pytest.raises(ContractGateError) as info:
        gate(report, "contract")

    assert info.value.code == "quality.contract_failed"
    assert "no findings recorded" in info.value.message


def test_load_report_parses_class_alias_and_ignores_extra_keys(tmp_path: Path) -> None:
    payload = _report_dict("contract", passed=False, findings=[_TRANSFORM])
    payload["blender_version"] = "5.2.3"
    path = tmp_path / "nmg-report.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = load_report(path)

    assert report.kind == "contract"
    assert report.asset == "Crate"
    assert report.asset_class == "standard_prop"
    assert report.passed is False
    assert [finding.rule for finding in report.findings] == ["transform.root_applied"]
    assert report.snapshot == {"SM_Crate": {"tris": 12}}


def test_load_report_missing_file_raises_report_unreadable(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as info:
        load_report(tmp_path / "absent.json")

    assert info.value.code == "quality.report_unreadable"


def test_load_report_malformed_json_raises_report_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(PipelineError) as info:
        load_report(path)

    assert info.value.code == "quality.report_unreadable"


def test_load_then_gate_raises_for_failing_file(tmp_path: Path) -> None:
    path = tmp_path / "nmg-report.json"
    path.write_text(
        json.dumps(_report_dict("reimport", passed=False, findings=[_PIVOT])),
        encoding="utf-8",
    )

    with pytest.raises(PipelineError) as info:
        gate(load_report(path), "reimport")

    assert info.value.code == "quality.reimport_mismatch"
