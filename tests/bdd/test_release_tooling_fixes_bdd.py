"""pytest-bdd bindings for release_tooling_fixes.feature: SCN001 and SCN004-SCN008 of #95.

SCN002 and SCN003 (the re-import entry lookup) run headless in tests/blender/test_reimport_entry.py.
SCN001 drives the real Blender gate and skips when no Blender resolves. The notarization scenarios
run scripts/notarize-macos.sh against the PATH shims in tests/ship_fakes.py and contact nothing.
The lock scenarios run uv offline against copies in a temp folder; committed lockfiles are never
relocked.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pytest_bdd import given, scenario, then, when

from tests.lock_fakes import (
    REPO_ROOT,
    copy_projects,
    installed_version,
    label,
    lock_check,
    make_stale,
    project_dirs,
    set_version,
)
from tests.release_fakes import resolved_blender, run_gate, write_suite
from tests.ship_fakes import ShipSandbox, make_sandbox, run_script

_PASSWORD = "placeholder-app-password"
_PROFILE = "nmg-notary"
_MCP_IMPORTS = {
    "finalize": "finalize_mcp.server",
    "texture-gen": "texture_gen_mcp.server",
}


@dataclass
class ReleaseScenario:
    """The state one scenario carries from its Given steps to its Then steps."""

    tmp_path: Path
    suite: Path | None = None
    run: subprocess.CompletedProcess[str] | None = None
    sandbox: ShipSandbox | None = None
    notary_env: dict[str, str] = field(default_factory=dict)
    notary_without: tuple[str, ...] = ()
    project_root: Path | None = None
    lock_message: str | None = None
    installed: str | None = None
    imports: dict[str, subprocess.CompletedProcess[str]] = field(default_factory=dict)
    dry_run: subprocess.CompletedProcess[str] | None = None


@pytest.fixture
def state(tmp_path: Path) -> ReleaseScenario:
    return ReleaseScenario(tmp_path=tmp_path)


def _signed_app(sandbox: ShipSandbox) -> Path:
    app = sandbox.project.parent / "archive" / "Mac" / "Dogfood.app"
    app.mkdir(parents=True, exist_ok=True)
    return app


def _submit_calls(sandbox: ShipSandbox) -> list[list[str]]:
    return [call for call in sandbox.calls("xcrun") if call[:2] == ["notarytool", "submit"]]


@pytest.mark.skipif(
    resolved_blender() is None,
    reason="no Blender resolves: set BLENDER_BIN or BLENDER_APP to run the gate for real",
)
@scenario("release_tooling_fixes.feature", "The Blender gate fails when a Blender test fails")
def test_scn001_the_blender_gate_fails_when_a_test_fails() -> None:
    """SCN001: the gate exits non-zero for a failing suite and exits 0 for a passing one."""


@given("a Blender test suite with one failing test")
def failing_blender_suite(state: ReleaseScenario) -> None:
    state.suite = write_suite(state.tmp_path / "failing", "def test_fails():\n    assert False\n")


@when("scripts/run-blender-tests.sh runs against it")
def gate_runs_against_failing_suite(state: ReleaseScenario) -> None:
    assert state.suite is not None
    state.run = run_gate({}, str(state.suite))


@then("it exits non-zero")
def gate_exits_non_zero(state: ReleaseScenario) -> None:
    assert state.run is not None
    assert state.run.returncode != 0, state.run.stdout + state.run.stderr


@then("it exits 0 against a suite whose tests all pass")
def gate_exits_zero_for_passing_suite(state: ReleaseScenario) -> None:
    passing = write_suite(state.tmp_path / "passing", "def test_passes():\n    assert True\n")
    result = run_gate({}, str(passing))
    assert result.returncode == 0, result.stdout + result.stderr


@scenario(
    "release_tooling_fixes.feature",
    "Notarization with a keychain profile keeps secrets out of argv",
)
def test_scn004_notarization_with_a_keychain_profile_keeps_secrets_out_of_argv() -> None:
    """SCN004: with NOTARIZATION_KEYCHAIN_PROFILE, notarytool gets the profile and no secret."""


@scenario("release_tooling_fixes.feature", "The password path still submits and warns")
def test_scn005_the_password_path_still_submits_and_warns() -> None:
    """SCN005: without the profile, notarytool gets the Apple ID and password, and it warns."""


@given("NOTARIZATION_KEYCHAIN_PROFILE is set and the Apple ID and app-specific password are unset")
def profile_set_and_apple_id_pair_unset(state: ReleaseScenario) -> None:
    state.sandbox = make_sandbox(state.tmp_path)
    state.notary_env = {"NOTARIZATION_KEYCHAIN_PROFILE": _PROFILE}
    state.notary_without = ("NOTARIZATION_APPLE_ID", "NOTARIZATION_APP_SPECIFIC_PASSWORD")


@given(
    "NOTARIZATION_KEYCHAIN_PROFILE is unset and the Apple ID, app-specific password "
    "and team ID are set"
)
def profile_unset_and_apple_id_pair_set(state: ReleaseScenario) -> None:
    state.sandbox = make_sandbox(state.tmp_path)
    state.notary_env = {}
    state.notary_without = ()


@when("scripts/notarize-macos.sh runs on a signed app")
def notarize_runs_on_signed_app(state: ReleaseScenario) -> None:
    assert state.sandbox is not None
    app = _signed_app(state.sandbox)
    state.run = run_script(
        state.sandbox,
        "notarize-macos.sh",
        str(app),
        extra_env=state.notary_env,
        without=state.notary_without,
    )


@then("notarytool is called with --keychain-profile and the profile name")
def notarytool_gets_the_keychain_profile(state: ReleaseScenario) -> None:
    assert state.run is not None
    assert state.run.returncode == 0, state.run.stderr
    assert state.sandbox is not None
    (submit,) = _submit_calls(state.sandbox)
    assert submit[submit.index("--keychain-profile") + 1] == _PROFILE


@then("notarytool is called without --apple-id or --password")
def notarytool_gets_no_apple_id_or_password(state: ReleaseScenario) -> None:
    assert state.sandbox is not None
    (submit,) = _submit_calls(state.sandbox)
    assert "--apple-id" not in submit
    assert "--password" not in submit


@then("notarytool is called with the Apple ID, password and team ID as before")
def notarytool_gets_the_password_path_arguments(state: ReleaseScenario) -> None:
    assert state.run is not None
    assert state.run.returncode == 0, state.run.stderr
    assert state.sandbox is not None
    (submit,) = _submit_calls(state.sandbox)
    assert submit[submit.index("--apple-id") + 1] == "ship-test@example.invalid"
    assert submit[submit.index("--password") + 1] == _PASSWORD
    assert submit[submit.index("--team-id") + 1] == "SMOKE00000"


@then("the password does not appear in the output")
def password_stays_out_of_output(state: ReleaseScenario) -> None:
    assert state.run is not None
    assert _PASSWORD not in state.run.stdout + state.run.stderr


@then(
    "a warning says the password is visible in process arguments "
    "and names NOTARIZATION_KEYCHAIN_PROFILE"
)
def warning_names_the_argument_visibility(state: ReleaseScenario) -> None:
    assert state.run is not None
    assert "visible in process arguments" in state.run.stderr
    assert "NOTARIZATION_KEYCHAIN_PROFILE" in state.run.stderr


@scenario("release_tooling_fixes.feature", "A version bump leaves every lockfile in sync")
def test_scn006_a_version_bump_leaves_every_lockfile_in_sync() -> None:
    """SCN006: after VERSION changes, every lock still checks and the package reports the bump."""


@given("copies of the root and both MCP sub-projects with their committed lockfiles")
def copied_projects(state: ReleaseScenario) -> None:
    state.project_root = copy_projects(state.tmp_path / "copy")


@when("VERSION changes to a new semver value")
def version_changes(state: ReleaseScenario) -> None:
    assert state.project_root is not None
    set_version(state.project_root, "9.9.9")


@then("uv lock --check passes in the root and in both MCP sub-projects")
def every_copied_lock_checks(state: ReleaseScenario) -> None:
    assert state.project_root is not None
    for project in project_dirs(state.project_root):
        assert lock_check(project, state.project_root) is None, label(project, state.project_root)


@then("the installed nmg-game-dev package reports the new version")
def installed_package_reports_new_version(state: ReleaseScenario) -> None:
    assert state.project_root is not None
    assert installed_version(state.project_root) == "9.9.9"


@scenario("release_tooling_fixes.feature", "Lock drift is reported with the project name")
def test_scn007_lock_drift_is_reported_with_the_project_name() -> None:
    """SCN007: a pyproject.toml that no longer matches its lock fails and names the project."""


@given("a project whose pyproject.toml no longer matches its lockfile")
def drifted_project(state: ReleaseScenario) -> None:
    state.project_root = copy_projects(state.tmp_path / "copy")
    make_stale(state.project_root)


@when("the lockfile check runs")
def lockfile_check_runs(state: ReleaseScenario) -> None:
    assert state.project_root is not None
    state.lock_message = lock_check(state.project_root, state.project_root)


@then("it fails and names that project as needing uv lock")
def drift_fails_and_names_the_project(state: ReleaseScenario) -> None:
    assert state.lock_message is not None, "a drifted pyproject.toml passed uv lock --check"
    assert "run `uv lock` in ." in state.lock_message


@scenario("release_tooling_fixes.feature", "Existing ship and MCP server behavior is preserved")
def test_scn008_existing_ship_and_mcp_server_behavior_is_preserved() -> None:
    """SCN008: the MCP servers import via uv run; notarize --dry-run submits nothing."""


@given("the committed finalize and texture-gen MCP sub-projects")
def committed_mcp_sub_projects(state: ReleaseScenario) -> None:  # noqa: ARG001
    for name in _MCP_IMPORTS:
        assert (REPO_ROOT / "mcp-servers" / name / "pyproject.toml").is_file()


@when("each server module is resolved through uv run --project as a consumer launches it")
def each_server_module_resolves(state: ReleaseScenario) -> None:
    for name, module in _MCP_IMPORTS.items():
        state.imports[name] = subprocess.run(
            [
                "uv",
                "run",
                "--offline",
                "--frozen",
                "--project",
                f"mcp-servers/{name}",
                "python",
                "-c",
                f"import {module}",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )


@then("both import successfully")
def both_servers_import(state: ReleaseScenario) -> None:
    for name, result in state.imports.items():
        assert result.returncode == 0, f"{name}: {result.stderr.strip()}"


@then("notarize-macos.sh --dry-run submits nothing")
def notarize_dry_run_submits_nothing(state: ReleaseScenario) -> None:
    sandbox = make_sandbox(state.tmp_path)
    app = _signed_app(sandbox)
    result = run_script(sandbox, "notarize-macos.sh", str(app), "--dry-run")
    assert result.returncode == 0, result.stderr
    assert sandbox.calls() == []
