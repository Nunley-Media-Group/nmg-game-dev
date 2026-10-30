"""Mobile budget gate (#6, FR6; AC6-AC8, plus the invalid report and override codes)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nmg_game_dev.quality.mobile_budgets import (
    DEFAULT_MOBILE_BUDGETS,
    check_mobile_budgets,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit-mobile-budgets.py"


def _project(root: Path) -> Path:
    (root / "Content").mkdir(parents=True)
    return root


def _report(root: Path, rel: str, report: dict[str, object]) -> None:
    folder = root / "Content" / rel / "Mobile"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "nmg-asset.json").write_text(json.dumps(report), encoding="utf-8")


_CRATE = {"class": "standard_prop", "tris": 4200, "max_texture_px": 1024, "materials": 1}


def test_defaults_match_the_asset_contract_mobile_column() -> None:
    assert DEFAULT_MOBILE_BUDGETS == {
        "small_prop": {"tris": 500, "max_texture_px": 512, "materials": 1},
        "standard_prop": {"tris": 3000, "max_texture_px": 1024, "materials": 1},
        "hero_prop": {"tris": 10000, "max_texture_px": 2048, "materials": 2},
        "character": {"tris": 15000, "max_texture_px": 2048, "materials": 2},
        "environment_piece": {"tris": 10000, "max_texture_px": 1024, "materials": 3},
    }


def test_over_budget_standard_prop_fails_with_the_overage(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _report(root, "Props/Crate", _CRATE)
    audit = check_mobile_budgets(root)
    assert audit.passed is False
    assert audit.assets == ["Props/Crate"]
    (finding,) = audit.findings
    assert finding.code == "ship.mobile_budget_exceeded"
    assert finding.subject == "Props/Crate"
    assert "Props/Crate: tris 4200 > 3000 (+1200)" in finding.remediation


def test_within_budget_passes(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _report(root, "Props/Crate", {**_CRATE, "tris": 2800})
    audit = check_mobile_budgets(root)
    assert audit.passed is True
    assert audit.findings == []


def test_missing_report_fails_and_tells_the_developer_to_finalize(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "Content" / "Props" / "Lamp" / "Mobile").mkdir(parents=True)
    audit = check_mobile_budgets(root)
    (finding,) = audit.findings
    assert finding.code == "ship.budget_report_missing"
    assert finding.remediation.startswith("finalize Props/Lamp to write Mobile/nmg-asset.json")


def test_override_raises_the_budget_for_the_metric_only(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _report(root, "Props/Crate", _CRATE)
    (root / "nmg-budgets.json").write_text(
        json.dumps({"standard_prop": {"tris": 5000}}), encoding="utf-8"
    )
    audit = check_mobile_budgets(root)
    assert audit.passed is True


def test_override_for_a_different_metric_keeps_the_default(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _report(root, "Props/Crate", _CRATE)
    (root / "nmg-budgets.json").write_text(
        json.dumps({"standard_prop": {"materials": 4}}), encoding="utf-8"
    )
    assert check_mobile_budgets(root).passed is False


def test_malformed_report_is_invalid_not_missing(tmp_path: Path) -> None:
    root = _project(tmp_path)
    folder = root / "Content" / "Props" / "Crate" / "Mobile"
    folder.mkdir(parents=True)
    (folder / "nmg-asset.json").write_text("not json", encoding="utf-8")
    (finding,) = check_mobile_budgets(root).findings
    assert finding.code == "ship.budget_report_invalid"


def test_report_with_a_string_tris_or_unknown_class_is_invalid(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _report(root, "Props/A", {**_CRATE, "tris": "4200"})
    _report(root, "Props/B", {**_CRATE, "class": "vehicle"})
    _report(root, "Props/C", {"class": "standard_prop", "tris": 1})
    codes = {finding.code for finding in check_mobile_budgets(root).findings}
    assert codes == {"ship.budget_report_invalid"}


def test_invalid_overrides_fail_the_audit(tmp_path: Path) -> None:
    cases: list[object] = [
        {"vehicle": {"tris": 9000}},
        {"standard_prop": {"polys": 9000}},
        {"standard_prop": {"tris": "9000"}},
        {"standard_prop": {"tris": True}},
        ["not", "an", "object"],
    ]
    for index, case in enumerate(cases):
        root = _project(tmp_path / f"case-{index}")
        (root / "nmg-budgets.json").write_text(json.dumps(case), encoding="utf-8")
        audit = check_mobile_budgets(root)
        assert audit.passed is False
        assert [finding.code for finding in audit.findings] == ["ship.budget_override_invalid"]


def test_desktop_variants_and_a_project_without_content_are_not_checked(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "Content" / "Props" / "Crate" / "Desktop").mkdir(parents=True)
    assert check_mobile_budgets(root).assets == []
    empty = tmp_path / "empty"
    empty.mkdir()
    assert check_mobile_budgets(empty).passed is True


def test_audit_script_exits_0_on_pass_and_1_on_fail(tmp_path: Path) -> None:
    passing = _project(tmp_path / "pass")
    _report(passing, "Props/Crate", {**_CRATE, "tris": 100})
    failing = _project(tmp_path / "fail")
    _report(failing, "Props/Crate", _CRATE)

    ok = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--project-root", str(passing)],
        capture_output=True,
        text=True,
        check=False,
    )
    bad = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--project-root", str(failing)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0
    assert "PASS" in ok.stdout
    assert bad.returncode == 1
    assert "ship.mobile_budget_exceeded" in bad.stdout
    assert "Props/Crate: tris 4200 > 3000 (+1200)" in bad.stdout
