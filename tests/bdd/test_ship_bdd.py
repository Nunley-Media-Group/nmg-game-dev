"""pytest-bdd bindings for ship.feature: the eleven acceptance scenarios of #6 (SCN001-SCN011).

Each scenario runs the real runner and scripts against the PATH shims in ``tests/ship_fakes.py``. No
scenario contacts Apple, Google, or a store, reads a keychain, or reads a real credential. The
scenarios that need live notarization, a real UAT build, or a real remote host are not run here.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.quality.mobile_budgets import MobileBudgetAudit, check_mobile_budgets
from nmg_game_dev.ship.artifacts import ReleaseEntry
from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.runner import run_ship
from tests.ship_fakes import (
    REPO_ROOT,
    ShipSandbox,
    make_sandbox,
    parse_frontmatter,
)

_SECRETS = (
    "placeholder-app-password",
    "placeholder-keystore-password",
)
_SMOKE_SCRIPT = REPO_ROOT / "scripts" / "ship-smoke.sh"
_SKILL = REPO_ROOT / "skills" / "ship" / "SKILL.md"


@dataclass
class ShipScenario:
    """The state one scenario carries from its Given steps to its Then steps."""

    sandbox: ShipSandbox
    capsys: pytest.CaptureFixture[str]
    error: ShipError | None = None
    entries: list[ReleaseEntry] = field(default_factory=list)
    output: str = ""
    audit: MobileBudgetAudit | None = None
    smoke: subprocess.CompletedProcess[str] | None = None
    frontmatter: dict[str, str] = field(default_factory=dict)
    skill_text: str = ""


@pytest.fixture
def ship(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> ShipScenario:
    return ShipScenario(sandbox=make_sandbox(tmp_path), capsys=capsys)


def _run(ship: ShipScenario, target: str, *, dry_run: bool = False) -> None:
    try:
        ship.entries = run_ship(
            target, ship.sandbox.project, ship.sandbox.release_dir, dry_run, ship.sandbox.env
        )
    except ShipError as error:
        ship.error = error
    captured = ship.capsys.readouterr()
    ship.output += captured.out + captured.err


def _artifacts(ship: ShipScenario, platform: str) -> list[Path]:
    folder = ship.sandbox.release_dir / platform
    if not folder.is_dir():
        return []
    return [path for path in folder.rglob("*") if path.is_file()]


def _project_file(ship: ShipScenario, rel: str, report: dict[str, object] | None) -> None:
    path = ship.sandbox.project.parent / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if report is not None:
        path.write_text(json.dumps(report), encoding="utf-8")


@scenario("ship.feature", "Ship macOS packages, signs, notarizes, and releases the app")
def test_ship_macos_packages_signs_notarizes_and_releases() -> None:
    """AC1: a macOS ship runs UAT, codesigns, notarizes, staples, and publishes the .app."""


@scenario("ship.feature", "Dry-run ship reports the plan without building")
def test_dry_run_ship_reports_the_plan() -> None:
    """AC2: a dry-run ship runs no tool and writes the plan."""


@scenario("ship.feature", "Ship mobile produces an .ipa and an .aab")
def test_ship_mobile_produces_ipa_and_aab() -> None:
    """AC3: a mobile ship publishes an .ipa and an .aab and keeps the password out of output."""


@scenario("ship.feature", "Cook-manifest gate blocks cross-variant leakage")
def test_cook_manifest_gate_blocks_leakage() -> None:
    """AC4: a Desktop path in the iOS cooked content blocks the iOS artifact."""


@scenario("ship.feature", "Windows build runs on the remote host")
def test_windows_build_runs_on_the_remote_host() -> None:
    """AC5: the Windows build runs over SSH and the .exe is copied back."""


@scenario("ship.feature", "Mobile budget gate blocks an over-budget asset before any build")
def test_mobile_budget_gate_blocks_over_budget_asset() -> None:
    """AC6: an over-budget Mobile asset stops the ship before any UAT invocation."""


@scenario("ship.feature", "A Mobile variant without a report fails the budget gate")
def test_mobile_variant_without_report_fails_gate() -> None:
    """AC7: a Mobile folder with no nmg-asset.json fails with ship.budget_report_missing."""


@scenario("ship.feature", "Consumer budget overrides apply")
def test_consumer_budget_overrides_apply() -> None:
    """AC8: nmg-budgets.json raises the standard_prop tris budget, and the gate passes."""


@scenario("ship.feature", "Missing prerequisites fail fast without leaking secrets")
def test_missing_prerequisites_fail_fast() -> None:
    """AC9: an unset NOTARIZATION_TEAM_ID stops the ship before any UAT invocation."""


@scenario("ship.feature", "Ship smoke dry-run succeeds on the fixture project")
def test_ship_smoke_dry_run_succeeds() -> None:
    """AC10: scripts/ship-smoke.sh runs a dry-run all ship of the fixture and exits 0."""


@scenario("ship.feature", "The ship skill is the single Claude Code entry point")
def test_ship_skill_is_the_entry_point() -> None:
    """AC11: the ship skill has the required frontmatter and invokes the CLI."""


# --- Given ---------------------------------------------------------------------------------


@given("a consumer project, a UE_ROOT with RunUAT.sh, and notarization variables set")
def _consumer_with_engine(ship: ShipScenario) -> None:
    # An earlier macOS build sits in release/ so the replacement can be checked.
    stale = ship.sandbox.release_dir / "macos" / "Dogfood.app" / "stale.marker"
    stale.parent.mkdir(parents=True)
    stale.write_text("earlier build", encoding="utf-8")


@given("a consumer project with notarization variables set and no Unreal Engine installed")
def _consumer_without_engine(ship: ShipScenario) -> None:
    ship.sandbox.env["UE_ROOT"] = str(ship.sandbox.project.parent / "no-engine-here")


@given("iOS and Android signing variables are set and every Mobile variant is within budget")
def _mobile_signing_set(ship: ShipScenario) -> None:
    assert ship.sandbox.env["IOS_PROVISIONING_PROFILE"]
    assert ship.sandbox.env["ANDROID_KEYSTORE_PASSWORD"]


@given(parsers.parse('the iOS cooked content contains "{rel_path}"'))
def _ios_leak(ship: ShipScenario, rel_path: str) -> None:
    ship.sandbox.env["NMG_SHIP_FAKE_COOK_LEAK"] = rel_path


@given("the Windows build host, user, SSH key, and remote project path are set")
def _windows_set(ship: ShipScenario) -> None:
    assert ship.sandbox.env["WINDOWS_REMOTE_PROJECT_PATH"]


@given(parsers.parse('"{rel_path}" reports a standard_prop with {tris:d} tris'))
def _standard_prop_report(ship: ShipScenario, rel_path: str, tris: int) -> None:
    _project_file(
        ship,
        rel_path,
        {"class": "standard_prop", "tris": tris, "max_texture_px": 1024, "materials": 1},
    )


@given(parsers.parse('"{rel_dir}" has no nmg-asset.json'))
def _mobile_folder_without_report(ship: ShipScenario, rel_dir: str) -> None:
    (ship.sandbox.project.parent / rel_dir).mkdir(parents=True, exist_ok=True)


@given("nmg-budgets.json sets standard_prop tris to 5000")
def _override_tris(ship: ShipScenario) -> None:
    _project_file(
        ship,
        "nmg-budgets.json",
        {"standard_prop": {"tris": 5000}},
    )


@given("NOTARIZATION_TEAM_ID is unset and the other notarization variables hold secret values")
def _team_unset(ship: ShipScenario) -> None:
    ship.sandbox.env.pop("NOTARIZATION_TEAM_ID")


@given("the repository checkout with no Unreal Engine install")
def _checkout(ship: ShipScenario) -> None:
    assert _SMOKE_SCRIPT.is_file()


@given("the plugin checkout")
def _plugin_checkout(ship: ShipScenario) -> None:
    assert _SKILL.is_file()


# --- When ----------------------------------------------------------------------------------


@when(parsers.parse('"ship {command}" runs'))
def _ship_command(ship: ShipScenario, command: str) -> None:
    parts = command.split()
    _run(ship, parts[0], dry_run="--dry-run" in parts)


@when("gate-mobile-budgets runs")
def _gate(ship: ShipScenario) -> None:
    ship.audit = check_mobile_budgets(ship.sandbox.project.parent)


@when("scripts/ship-smoke.sh runs")
def _smoke(ship: ShipScenario) -> None:
    uv = _uv_dir()
    env = {"PATH": f"{uv}:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(REPO_ROOT), "LANG": "C"}
    ship.smoke = subprocess.run(
        [str(_SMOKE_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@when("skills/ship/SKILL.md is parsed")
def _parse_skill(ship: ShipScenario) -> None:
    ship.skill_text = _SKILL.read_text(encoding="utf-8")
    ship.frontmatter = parse_frontmatter(ship.skill_text)


def _uv_dir() -> str:
    import shutil

    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is required to run scripts/ship-smoke.sh")
    return str(Path(uv).parent)


# --- Then ----------------------------------------------------------------------------------


@then("RunUAT BuildCookRun is invoked with -platform=Mac and Shipping package flags")
def _uat_mac(ship: ShipScenario) -> None:
    (argv,) = ship.sandbox.calls("RunUAT.sh")
    for flag in ("BuildCookRun", "-platform=Mac", "-clientconfig=Shipping", "-cook", "-stage"):
        assert flag in argv
    for flag in ("-pak", "-package", "-archive"):
        assert flag in argv


@then("the .app is codesigned with the team's signing identity")
def _codesigned(ship: ShipScenario) -> None:
    signed = ship.sandbox.calls("codesign")[0]
    identity = signed[signed.index("--sign") + 1]
    assert "(SMOKE00000)" in identity


@then("the .app is submitted with notarytool for the team and stapled")
def _notarized(ship: ShipScenario) -> None:
    xcrun = ship.sandbox.calls("xcrun")
    submit = next(call for call in xcrun if call[:2] == ["notarytool", "submit"])
    assert submit[submit.index("--team-id") + 1] == "SMOKE00000"
    assert any(call[:2] == ["stapler", "staple"] for call in xcrun)


@then("the signed .app is in release/macos/ replacing any earlier .app")
def _replaced(ship: ShipScenario) -> None:
    assert (ship.sandbox.release_dir / "macos" / "Dogfood.app").is_dir()
    assert not (ship.sandbox.release_dir / "macos" / "Dogfood.app" / "stale.marker").exists()


@then("release/RELEASE-NOTES.md lists the .app with its SHA-256")
def _notes(ship: ShipScenario) -> None:
    notes = (ship.sandbox.release_dir / "RELEASE-NOTES.md").read_text(encoding="utf-8")
    (entry,) = ship.entries
    assert "macos/Dogfood.app" in notes
    assert entry.sha256 in notes


@then("no UAT, codesign, security, or xcrun process runs")
def _nothing_ran(ship: ShipScenario) -> None:
    assert ship.sandbox.calls() == []


@then(
    'each planned command is printed with a "DRY-RUN:" prefix including a notarization dry-run pass'
)
def _planned(ship: ShipScenario) -> None:
    assert "DRY-RUN:" in ship.output
    assert "DRY-RUN: notarization pass (no submission) for team SMOKE00000" in ship.output


@then("release/macos/DRY-RUN.txt records the plan and the command exits 0")
def _dry_run_file(ship: ShipScenario) -> None:
    assert ship.error is None
    dry = (ship.sandbox.release_dir / "macos" / "DRY-RUN.txt").read_text(encoding="utf-8")
    assert "DRY-RUN:" in dry


@then("UAT is invoked for IOS and for Android")
def _uat_mobile(ship: ShipScenario) -> None:
    platforms = [
        next(arg for arg in call if arg.startswith("-platform="))
        for call in ship.sandbox.calls("RunUAT.sh")
    ]
    assert platforms == ["-platform=IOS", "-platform=Android"]


@then("an .ipa is in release/ios/ and an .aab is in release/android/")
def _ipa_aab(ship: ShipScenario) -> None:
    assert ship.error is None
    assert (ship.sandbox.release_dir / "ios" / "Dogfood.ipa").is_file()
    assert (ship.sandbox.release_dir / "android" / "Dogfood.aab").is_file()


@then("the mobile cook-manifest gate passed for both platforms")
def _gate_passed(ship: ShipScenario) -> None:
    # A platform is published only after its cook-manifest gate passes, so both entries prove it.
    assert [entry.platform for entry in ship.entries] == ["ios", "android"]


@then("the Android keystore password does not appear in the output")
def _no_password(ship: ShipScenario) -> None:
    for secret in _SECRETS:
        assert secret not in ship.output


@then("verify-cook-manifest.sh reports the Desktop path")
def _reports_path(ship: ShipScenario) -> None:
    assert "Content/Props/Crate/Desktop/SM_Crate.uasset" in ship.output


@then("the ship exits non-zero with a remediation")
def _non_zero(ship: ShipScenario) -> None:
    assert ship.error is not None
    assert ship.error.remediation


@then("no artifact is in release/ios/")
def _no_ios(ship: ShipScenario) -> None:
    assert _artifacts(ship, "ios") == []


@then("ssh invokes RunUAT.bat BuildCookRun with -platform=Win64 on the remote project")
def _ssh_uat(ship: ShipScenario) -> None:
    remote = ship.sandbox.calls("ssh")[0][-1]
    assert "RunUAT.bat" in remote
    assert "BuildCookRun" in remote
    assert "-platform=Win64" in remote
    assert "C:\\build\\Dogfood\\Dogfood.uproject" in remote


@then("the remote cooked listing passes the desktop cook-manifest gate")
def _listing_passed(ship: ShipScenario) -> None:
    assert [entry.platform for entry in ship.entries] == ["windows"]


@then("a .exe is copied back into release/windows/")
def _exe(ship: ShipScenario) -> None:
    assert (ship.sandbox.release_dir / "windows" / "Dogfood.exe").is_file()


@then("gate-mobile-budgets fails before any UAT invocation")
def _gate_fails_before_uat(ship: ShipScenario) -> None:
    assert ship.error is not None
    assert ship.error.code == "ship.mobile_budget_exceeded"
    assert not ship.sandbox.invoked("RunUAT.sh")


@then("no artifact is in release/ios/ or release/android/")
def _no_mobile(ship: ShipScenario) -> None:
    assert _artifacts(ship, "ios") == []
    assert _artifacts(ship, "android") == []


@then('the remediation names "Props/Crate", tris, 4200, budget 3000, and overage 1200')
def _names_overage(ship: ShipScenario) -> None:
    assert ship.error is not None
    remediation = ship.error.remediation
    for text in ("Props/Crate", "tris", "4200", "3000", "1200"):
        assert text in remediation


@then(parsers.parse('it fails with code "{code}" telling the developer to finalize "{asset}"'))
def _missing_report(ship: ShipScenario, code: str, asset: str) -> None:
    assert ship.audit is not None
    assert ship.audit.passed is False
    (finding,) = ship.audit.findings
    assert finding.code == code
    assert f"finalize {asset} to write Mobile/nmg-asset.json" in finding.remediation


@then("the gate passes")
def _gate_passes(ship: ShipScenario) -> None:
    assert ship.audit is not None
    assert ship.audit.passed is True


@then("it exits 1 before any UAT invocation naming NOTARIZATION_TEAM_ID")
def _exits_1(ship: ShipScenario) -> None:
    assert ship.error is not None
    assert ship.error.code == "ship.env_missing"
    assert "NOTARIZATION_TEAM_ID" in ship.error.message
    assert not ship.sandbox.invoked("RunUAT.sh")


@then("no secret value appears in the output")
def _no_secret(ship: ShipScenario) -> None:
    assert ship.error is not None
    text = ship.output + ship.error.message + ship.error.remediation
    for secret in _SECRETS:
        assert secret not in text


@then('a dry-run "all" ship of fixtures/dogfood.uproject exits 0')
def _smoke_exits_0(ship: ShipScenario) -> None:
    assert ship.smoke is not None
    assert ship.smoke.returncode == 0, ship.smoke.stderr
    assert "DRY-RUN" in ship.smoke.stdout


@then(
    'its frontmatter has name "ship", a description, required_mcp, required_env, '
    "and unattended_safe true"
)
def _frontmatter(ship: ShipScenario) -> None:
    fields = ship.frontmatter
    assert fields["name"] == "ship"
    assert fields["description"]
    assert "required_mcp" in fields
    assert "required_env" in fields
    assert fields["unattended_safe"] == "true"


@then('its flow invokes "python -m nmg_game_dev.ship"')
def _invokes(ship: ShipScenario) -> None:
    assert "python -m nmg_game_dev.ship" in ship.skill_text
