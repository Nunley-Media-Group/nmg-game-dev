"""pytest-bdd bindings for ship.feature: the Godot ship scenarios (#6 SCN001-SCN011, #249 AC9).

Each scenario runs the real runner, and the real sign and notarize scripts, against the fake Godot
and PATH shims in ``tests/ship_fakes.py``. No scenario runs Godot, contacts Apple, Google, or a
store, reads a keychain, or reads a real credential.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.godot.runner import CommandResult
from nmg_game_dev.quality.mobile_budgets import (
    OVERRIDES_NAME,
    MobileBudgetAudit,
    check_mobile_budgets,
)
from nmg_game_dev.ship.artifacts import ReleaseEntry, artifact_sha256
from nmg_game_dev.ship.errors import ShipError
from tests.ship_fakes import (
    APP,
    REPO_ROOT,
    ShipSandbox,
    make_sandbox,
    parse_frontmatter,
    write_mobile_report,
)

_SECRETS = (
    "placeholder-app-password",
    "placeholder-keystore-password",
)
_IDENTITY = "Developer ID Application: Example Studio (SMOKE00000)"
_SMOKE_SCRIPT = REPO_ROOT / "scripts" / "ship-smoke.sh"
_SKILL = REPO_ROOT / "skills" / "ship" / "SKILL.md"
_MIB = 1024 * 1024


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
        ship.entries = ship.sandbox.ship(target, dry_run=dry_run)
    except ShipError as error:
        ship.error = error
    captured = ship.capsys.readouterr()
    ship.output += captured.out + captured.err


def _artifacts(ship: ShipScenario, platform: str) -> list[Path]:
    folder = ship.sandbox.release_dir / platform
    if not folder.is_dir():
        return []
    return [path for path in folder.rglob("*") if path.is_file()]


def _notes(ship: ShipScenario) -> str:
    return (ship.sandbox.release_dir / "RELEASE-NOTES.md").read_text(encoding="utf-8")


@scenario("ship.feature", "Ship macOS exports, signs, notarizes, and releases the app")
def test_ship_macos_exports_signs_notarizes_and_releases() -> None:
    """SCN001: a macOS ship exports, codesigns, notarizes, staples, and lists the .app."""


@scenario("ship.feature", "Dry-run ship reports the plan without exporting")
def test_dry_run_ship_reports_the_plan() -> None:
    """SCN002: a dry-run ship runs no Godot or tool and writes the plan."""


@scenario("ship.feature", "Ship exports every target through Godot")
def test_ship_exports_every_target_through_godot() -> None:
    """SCN003 (#249 SCN009): the gates run first, then every platform exports its artifact."""


@scenario("ship.feature", "A script that does not parse stops the ship")
def test_a_script_that_does_not_parse_stops_the_ship() -> None:
    """SCN004: --check-only failing on one script stops the ship before any export."""


@scenario("ship.feature", "A large web pack warns")
def test_a_large_web_pack_warns() -> None:
    """SCN005: a web index.pck over 38 MiB prints ship.web_pack_large and still ships."""


@scenario("ship.feature", "Mobile budget gate blocks an over-budget asset before any export")
def test_mobile_budget_gate_blocks_over_budget_asset() -> None:
    """SCN006: an over-budget Mobile asset stops the ship before any export."""


@scenario("ship.feature", "A Mobile variant without a report fails the budget gate")
def test_mobile_variant_without_report_fails_gate() -> None:
    """SCN007: a Mobile folder with no nmg-asset.json fails with ship.budget_report_missing."""


@scenario("ship.feature", "Consumer budget overrides apply")
def test_consumer_budget_overrides_apply() -> None:
    """SCN008: nmg-budgets.json raises the standard_prop tris budget, and the gate passes."""


@scenario("ship.feature", "Missing prerequisites fail fast without leaking secrets")
def test_missing_prerequisites_fail_fast() -> None:
    """SCN009: an unset NOTARIZATION_TEAM_ID stops the ship before any Godot command."""


@scenario("ship.feature", "Ship smoke dry-run succeeds on the fixture project")
def test_ship_smoke_dry_run_succeeds() -> None:
    """SCN010: scripts/ship-smoke.sh runs a dry-run all ship of the fixture and exits 0."""


@scenario("ship.feature", "The ship skill is the single Claude Code entry point")
def test_ship_skill_is_the_entry_point() -> None:
    """SCN011: the ship skill has the required frontmatter and invokes the CLI."""


# --- Given ---------------------------------------------------------------------------------


@given("a consumer Godot project with notarization variables set and an earlier macOS build")
def _consumer_with_earlier_build(ship: ShipScenario) -> None:
    stale = ship.sandbox.release_dir / "macos" / "Old.app" / "stale.marker"
    stale.parent.mkdir(parents=True)
    stale.write_text("earlier build", encoding="utf-8")


@given("a consumer Godot project with notarization variables set")
def _consumer(ship: ShipScenario) -> None:
    assert ship.sandbox.env["NOTARIZATION_TEAM_ID"]


@given('a consumer Godot project with project tests and the environment for target "all"')
def _consumer_for_all(ship: ShipScenario) -> None:
    tests = ship.sandbox.game / "tests"
    tests.mkdir()
    (tests / "run_tests.gd").write_text("extends SceneTree\n", encoding="utf-8")
    write_mobile_report(
        ship.sandbox.game,
        "Props/Crate",
        {"class": "standard_prop", "tris": 2800, "max_texture_px": 1024, "materials": 1},
    )


@given(parsers.parse('"{rel}" in the consumer project does not parse'))
def _broken_script(ship: ShipScenario, rel: str) -> None:
    def check(args: list[str], project: Path) -> CommandResult:
        if args[2] == f"res://{rel}":
            return CommandResult(1, stderr="SCRIPT ERROR: Parse Error: Unexpected token.\n")
        return CommandResult(0)

    ship.sandbox.godot.responses["--check-only"] = check


@given(parsers.parse("the web export writes an index.pck of {size:d} MiB"))
def _large_web_pack(ship: ShipScenario, size: int) -> None:
    ship.sandbox.web_pack_bytes = size * _MIB


@given(
    parsers.parse(
        '"assets/{rel_dir}/Mobile/nmg-asset.json" reports a standard_prop with {tris:d} tris'
    )
)
def _standard_prop_report(ship: ShipScenario, rel_dir: str, tris: int) -> None:
    write_mobile_report(
        ship.sandbox.game,
        rel_dir,
        {"class": "standard_prop", "tris": tris, "max_texture_px": 1024, "materials": 1},
    )


@given(parsers.parse('"assets/{rel_dir}/Mobile/" has no nmg-asset.json'))
def _mobile_folder_without_report(ship: ShipScenario, rel_dir: str) -> None:
    write_mobile_report(ship.sandbox.game, rel_dir, None)


@given("nmg-budgets.json sets standard_prop tris to 5000")
def _override_tris(ship: ShipScenario) -> None:
    (ship.sandbox.game.parent / OVERRIDES_NAME).write_text(
        json.dumps({"standard_prop": {"tris": 5000}}), encoding="utf-8"
    )


@given("NOTARIZATION_TEAM_ID is unset and the other notarization variables hold secret values")
def _team_unset(ship: ShipScenario) -> None:
    ship.sandbox.env.pop("NOTARIZATION_TEAM_ID")


@given("the repository checkout with no Godot install required")
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


@when("the mobile budget gate runs")
def _gate(ship: ShipScenario) -> None:
    game = ship.sandbox.game
    ship.audit = check_mobile_budgets(game / "assets", game.parent / OVERRIDES_NAME)


@when("scripts/ship-smoke.sh runs")
def _smoke(ship: ShipScenario) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is required to run scripts/ship-smoke.sh")
    env = {
        "PATH": f"{Path(uv).parent}:/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(REPO_ROOT),
        "LANG": "C",
    }
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


# --- Then ----------------------------------------------------------------------------------


@then(parsers.parse('Godot exports the "{preset}" preset headless'))
def _exported(ship: ShipScenario, preset: str) -> None:
    assert ship.error is None, ship.error
    assert ship.sandbox.exports() == [preset]


@then("the .app is codesigned with the team's signing identity")
def _codesigned(ship: ShipScenario) -> None:
    app = ship.sandbox.release_dir / "macos" / f"{APP}.app"
    sign = ship.sandbox.calls("codesign")[0]
    assert sign[5:8] == ["--sign", _IDENTITY, str(app)]


@then("the .app is submitted with notarytool for the team and stapled")
def _notarized(ship: ShipScenario) -> None:
    app = ship.sandbox.release_dir / "macos" / f"{APP}.app"
    xcrun = ship.sandbox.calls("xcrun")
    (submit,) = [call for call in xcrun if call[:2] == ["notarytool", "submit"]]
    assert submit[submit.index("--team-id") + 1] == "SMOKE00000"
    assert ["stapler", "staple", str(app)] in xcrun


@then("the signed .app is in release/macos/ replacing any earlier build")
def _replaced(ship: ShipScenario) -> None:
    macos = ship.sandbox.release_dir / "macos"
    assert (macos / f"{APP}.app").is_dir()
    assert not (macos / "Old.app").exists()


@then("release/RELEASE-NOTES.md lists the .app with its SHA-256")
def _notes_list_app(ship: ShipScenario) -> None:
    (entry,) = ship.entries
    assert entry.path == f"macos/{APP}.app"
    assert f"| macos | `{entry.path}` | `{entry.sha256}` |" in _notes(ship)


@then("no Godot, codesign, or xcrun process runs")
def _nothing_ran(ship: ShipScenario) -> None:
    assert ship.error is None, ship.error
    assert ship.sandbox.godot.calls == []
    assert not ship.sandbox.invoked("codesign")
    assert not ship.sandbox.invoked("xcrun")


@then(
    'each planned command is printed with a "DRY-RUN:" prefix including a notarization dry-run pass'
)
def _planned(ship: ShipScenario) -> None:
    assert "DRY-RUN: godot --headless" in ship.output
    assert "--export-release macOS" in ship.output
    assert "DRY-RUN: codesign" in ship.output
    assert "DRY-RUN: notarization pass (no submission) for team SMOKE00000" in ship.output


@then("release/macos/DRY-RUN.txt records the plan")
def _dry_run_file(ship: ShipScenario) -> None:
    dry = (ship.sandbox.release_dir / "macos" / "DRY-RUN.txt").read_text(encoding="utf-8")
    assert "--export-release macOS" in dry
    assert "DRY-RUN: notarization pass" in dry
    assert "DRY RUN" in _notes(ship)


@then("the script check, the project tests, and the mobile budget gate run before any export")
def _gates_first(ship: ShipScenario) -> None:
    assert ship.error is None, ship.error
    commands = ship.sandbox.godot_commands()
    first_export = next(i for i, call in enumerate(commands) if call[0] == "--export-release")
    before = commands[:first_export]
    # A fresh checkout is imported first, so class_name types resolve in the script check.
    assert before[0] == ["--import"]
    before = before[1:]
    # The headless smoke run (#251) sits between the project tests and the first export.
    smoke = ["--fixed-fps", "60", "--quit-after", "600", "--", "--nmg-autoplay", "--nmg-test-saves"]
    assert [call[0] for call in before[:-2]] == ["--check-only"] * (len(before) - 2)
    assert before[-2:] == [["-s", "res://tests/run_tests.gd"], smoke]
    # The budget gate passed (a within-budget Mobile report exists), so the mobile exports ran.
    assert "iOS" in ship.sandbox.exports()


@then(
    "release/ holds the macOS .app, the .ipa, the .aab, the .exe, and the web folder, each with "
    "SHA-256 in RELEASE-NOTES.md"
)
def _all_artifacts(ship: ShipScenario) -> None:
    release = ship.sandbox.release_dir
    expected = {
        "macos": f"macos/{APP}.app",
        "windows": f"windows/{APP}.exe",
        "ios": f"ios/{APP}.ipa",
        "android": f"android/{APP}.aab",
        "web": "web",
    }
    assert {entry.platform: entry.path for entry in ship.entries} == expected
    notes = _notes(ship)
    for entry in ship.entries:
        assert (release / entry.path).exists()
        assert entry.sha256 == artifact_sha256(release / entry.path)
        assert f"`{entry.path}` | `{entry.sha256}`" in notes
    assert (release / "web" / "index.html").is_file()


@then("no WINDOWS_BUILD_* variable was required")
def _no_windows_vars(ship: ShipScenario) -> None:
    assert not any(name.startswith("WINDOWS_") for name in ship.sandbox.env)


@then("the Android keystore password does not appear in the output")
def _no_password(ship: ShipScenario) -> None:
    assert "placeholder-keystore-password" not in ship.output


@then(parsers.parse('the ship fails with code "{code}" naming "{rel}"'))
def _fails_naming(ship: ShipScenario, code: str, rel: str) -> None:
    assert ship.error is not None
    assert ship.error.code == code
    assert rel in ship.error.message


@then("no preset is exported")
def _no_export(ship: ShipScenario) -> None:
    assert ship.sandbox.exports() == []


@then(parsers.parse('the output warns "{warning}"'))
def _warns(ship: ShipScenario, warning: str) -> None:
    assert ship.error is None, ship.error
    assert warning in ship.output


@then("release/web/ is listed in RELEASE-NOTES.md")
def _web_listed(ship: ShipScenario) -> None:
    (entry,) = ship.entries
    assert entry.path == "web"
    assert f"| web | `web` | `{entry.sha256}` |" in _notes(ship)


@then("the mobile budget gate fails before any export")
def _gate_fails_before_export(ship: ShipScenario) -> None:
    assert ship.error is not None
    assert ship.error.code == "ship.mobile_budget_exceeded"
    assert ship.sandbox.exports() == []


@then("no artifact is in release/ios/ or release/android/")
def _no_mobile(ship: ShipScenario) -> None:
    assert _artifacts(ship, "ios") == []
    assert _artifacts(ship, "android") == []


@then('the remediation names "Props/Crate", tris, 4200, budget 3000, and overage 1200')
def _names_overage(ship: ShipScenario) -> None:
    assert ship.error is not None
    assert "Props/Crate: tris 4200 > 3000 (+1200)" in ship.error.remediation


@then(parsers.parse('it fails with code "{code}" telling the developer to finalize "{asset}"'))
def _missing_report(ship: ShipScenario, code: str, asset: str) -> None:
    assert ship.audit is not None
    assert ship.audit.passed is False
    (finding,) = ship.audit.findings
    assert finding.code == code
    assert f"finalize {asset}" in finding.remediation


@then("the gate passes")
def _gate_passes(ship: ShipScenario) -> None:
    assert ship.audit is not None
    assert ship.audit.passed is True, ship.audit.findings


@then("it fails before any Godot command naming NOTARIZATION_TEAM_ID")
def _fails_before_godot(ship: ShipScenario) -> None:
    assert ship.error is not None
    assert ship.error.code == "ship.env_missing"
    assert "NOTARIZATION_TEAM_ID" in ship.error.message
    assert ship.sandbox.godot.calls == []


@then("no secret value appears in the output")
def _no_secret(ship: ShipScenario) -> None:
    assert ship.error is not None
    text = ship.output + ship.error.message + ship.error.remediation
    for secret in _SECRETS:
        assert secret not in text


@then('a dry-run "all" ship of tests/godot/fixture/project.godot exits 0')
def _smoke_exits_0(ship: ShipScenario) -> None:
    assert ship.smoke is not None
    assert ship.smoke.returncode == 0, ship.smoke.stderr
    assert "DRY-RUN" in ship.smoke.stdout
    assert "tests/godot/fixture" in ship.smoke.stdout


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
