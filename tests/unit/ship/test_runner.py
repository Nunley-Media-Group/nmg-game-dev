"""The ship runner end to end against a fake Godot and PATH shims (#6; #249 FR9, AC9).

No test runs Godot, contacts Apple, Google, or a store, reads a keychain, or reads a real
credential. Each run uses the sandbox's placeholder environment. Godot is a ``FakeGodotRunner``
whose export writes the artifact, and every other tool is a shim that records its argv.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from nmg_game_dev.godot.runner import CommandResult
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.ship import runner as ship_runner
from nmg_game_dev.ship.__main__ import main as ship_main
from nmg_game_dev.ship.artifacts import artifact_sha256
from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.runner import (
    WEB_PACK_LIMIT,
    app_name,
    patch_preset_options,
    project_scripts,
    run_ship,
)
from tests.ship_fakes import APP, ShipSandbox, write_mobile_report

_KEYSTORE_PASSWORD = "placeholder-keystore-password"
_APP_PASSWORD = "placeholder-app-password"
_IDENTITY = "Developer ID Application: Example Studio (SMOKE00000)"
_PROFILE_UUID = "11111111-2222-3333-4444-555555555555"
_CRATE = {"class": "standard_prop", "tris": 2800, "max_texture_px": 1024, "materials": 1}


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    return captured.out + captured.err


# Order of the gates and exports -----------------------------------------------------------------


def test_all_runs_script_check_then_tests_then_budget_then_every_export(
    sandbox: ShipSandbox,
) -> None:
    (sandbox.game / "tests").mkdir()
    (sandbox.game / "tests" / "run_tests.gd").write_text("extends SceneTree\n", encoding="utf-8")
    write_mobile_report(sandbox.game, "Props/Crate", _CRATE)

    entries = sandbox.ship("all")

    commands = sandbox.godot_commands()
    checks = [call for call in commands if call[:1] == ["--check-only"]]
    assert [call[2] for call in checks] == [
        "res://main.gd",
        "res://scripts/player.gd",
        "res://tests/run_tests.gd",
    ]
    assert all(call[1] == "-s" for call in checks)
    assert commands[len(checks)] == ["-s", "res://tests/run_tests.gd"]
    assert sandbox.exports() == ["macOS", "Windows Desktop", "iOS", "Android", "Web"]
    first_export = next(i for i, call in enumerate(commands) if call[0] == "--export-release")
    assert first_export == len(checks) + 1
    assert [entry.platform for entry in entries] == ["macos", "windows", "ios", "android", "web"]


def test_scripts_under_dot_godot_are_not_checked(sandbox: ShipSandbox) -> None:
    assert project_scripts(sandbox.game) == ["main.gd", "scripts/player.gd"]


def test_project_without_run_tests_skips_the_tests_step(sandbox: ShipSandbox) -> None:
    sandbox.ship("windows")
    assert ["-s", "res://tests/run_tests.gd"] not in sandbox.godot_commands()


def test_every_godot_call_targets_the_game_folder(sandbox: ShipSandbox) -> None:
    sandbox.ship("windows")
    assert {project.resolve() for project in sandbox.godot.projects} == {sandbox.game.resolve()}


def test_a_script_that_does_not_parse_stops_before_any_export(sandbox: ShipSandbox) -> None:
    def check(args: list[str], project: Path) -> CommandResult:
        if args[2] == "res://scripts/player.gd":
            return CommandResult(1, stderr='SCRIPT ERROR: Parse Error: Expected "end of file".\n')
        return CommandResult(0)

    sandbox.godot.responses["--check-only"] = check
    with pytest.raises(ShipError) as caught:
        sandbox.ship("all")
    assert caught.value.code == "ship.script_check_failed"
    assert "scripts/player.gd" in caught.value.message
    assert "Parse Error" in caught.value.message
    assert sandbox.exports() == []


def test_a_script_error_line_fails_the_check_even_on_exit_0(sandbox: ShipSandbox) -> None:
    sandbox.godot.responses["--check-only"] = CommandResult(0, stdout="SCRIPT ERROR: bad\n")
    with pytest.raises(ShipError) as caught:
        sandbox.ship("windows")
    assert caught.value.code == "ship.script_check_failed"


def test_failing_project_tests_stop_before_any_export(sandbox: ShipSandbox) -> None:
    (sandbox.game / "tests").mkdir()
    (sandbox.game / "tests" / "run_tests.gd").write_text("extends SceneTree\n", encoding="utf-8")
    sandbox.godot.responses["-s"] = CommandResult(1, stdout="3 passed, 1 failed\n")
    with pytest.raises(ShipError) as caught:
        sandbox.ship("windows")
    assert caught.value.code == "ship.tests_failed"
    assert sandbox.exports() == []


# Mobile budget gate ------------------------------------------------------------------------------


@pytest.mark.parametrize("target", ["ios", "android", "web", "mobile"])
def test_over_budget_mobile_asset_stops_before_any_export(
    sandbox: ShipSandbox, target: str
) -> None:
    write_mobile_report(sandbox.game, "Props/Crate", {**_CRATE, "tris": 4200})
    with pytest.raises(ShipError) as caught:
        sandbox.ship(target)
    error = caught.value
    assert error.code == "ship.mobile_budget_exceeded"
    assert "Props/Crate: tris 4200 > 3000 (+1200)" in error.remediation
    assert sandbox.exports() == []


@pytest.mark.parametrize("target", ["macos", "windows", "desktop"])
def test_desktop_targets_skip_the_budget_gate(sandbox: ShipSandbox, target: str) -> None:
    write_mobile_report(sandbox.game, "Props/Crate", {**_CRATE, "tris": 4200})
    sandbox.ship(target)
    assert sandbox.exports()


def test_mobile_variant_without_a_report_names_the_asset(sandbox: ShipSandbox) -> None:
    write_mobile_report(sandbox.game, "Props/Lamp", None)
    with pytest.raises(ShipError) as caught:
        sandbox.ship("android")
    assert caught.value.code == "ship.budget_report_missing"
    assert "finalize Props/Lamp" in caught.value.remediation


def test_consumer_root_budget_overrides_apply(sandbox: ShipSandbox) -> None:
    write_mobile_report(sandbox.game, "Props/Crate", {**_CRATE, "tris": 4200})
    (sandbox.game.parent / "nmg-budgets.json").write_text(
        '{"standard_prop": {"tris": 5000}}', encoding="utf-8"
    )
    assert [entry.platform for entry in sandbox.ship("android")] == ["android"]


def test_the_budget_gate_runs_in_a_dry_run(sandbox: ShipSandbox) -> None:
    write_mobile_report(sandbox.game, "Props/Crate", {**_CRATE, "tris": 4200})
    with pytest.raises(ShipError) as caught:
        sandbox.ship("web", dry_run=True)
    assert caught.value.code == "ship.mobile_budget_exceeded"


# Exports and artifacts ---------------------------------------------------------------------------


def test_every_platform_exports_its_preset_into_the_release_folder(sandbox: ShipSandbox) -> None:
    entries = sandbox.ship("all")
    release = sandbox.release_dir
    outputs = {call[1]: call[2] for call in sandbox.godot_commands("--export-release")}
    assert outputs == {
        "macOS": str(release / "macos" / f"{APP}.app"),
        "Windows Desktop": str(release / "windows" / f"{APP}.exe"),
        "iOS": str(release / "ios" / f"{APP}.ipa"),
        "Android": str(release / "android" / f"{APP}.aab"),
        "Web": str(release / "web" / "index.html"),
    }
    assert [entry.path for entry in entries] == [
        f"macos/{APP}.app",
        f"windows/{APP}.exe",
        f"ios/{APP}.ipa",
        f"android/{APP}.aab",
        "web",
    ]
    notes = (release / "RELEASE-NOTES.md").read_text(encoding="utf-8")
    for entry in entries:
        assert entry.sha256 == artifact_sha256(release / entry.path)
        assert f"| {entry.platform} | `{entry.path}` | `{entry.sha256}` |" in notes


def test_macos_is_signed_and_notarized_after_the_export(sandbox: ShipSandbox) -> None:
    sandbox.ship("macos")
    app = sandbox.release_dir / "macos" / f"{APP}.app"
    sign = sandbox.calls("codesign")[0]
    assert sign[5:8] == ["--sign", _IDENTITY, str(app)]
    submit = [call for call in sandbox.calls("xcrun") if call[:2] == ["notarytool", "submit"]]
    assert submit[0][submit[0].index("--team-id") + 1] == "SMOKE00000"
    assert ["stapler", "staple", str(app)] in sandbox.calls("xcrun")


def test_a_failed_export_raises_export_failed_and_stops(sandbox: ShipSandbox) -> None:
    sandbox.failing_preset = "Windows Desktop"
    with pytest.raises(ShipError) as caught:
        sandbox.ship("desktop")
    assert caught.value.code == "ship.export_failed"
    assert "Windows Desktop" in caught.value.message
    assert (sandbox.release_dir / "macos" / f"{APP}.app").is_dir()


def test_a_failed_macos_export_is_never_signed(sandbox: ShipSandbox) -> None:
    sandbox.failing_preset = "macOS"
    with pytest.raises(ShipError) as caught:
        sandbox.ship("macos")
    assert caught.value.code == "ship.export_failed"
    assert not sandbox.invoked("codesign")
    assert not sandbox.invoked("xcrun")


def test_an_export_that_writes_nothing_is_artifact_not_found(sandbox: ShipSandbox) -> None:
    sandbox.godot.responses["--export-release"] = CommandResult(0)
    with pytest.raises(ShipError) as caught:
        sandbox.ship("windows")
    assert caught.value.code == "ship.artifact_not_found"


def test_rerun_replaces_an_earlier_artifact(sandbox: ShipSandbox) -> None:
    old = sandbox.release_dir / "windows" / "old-build.txt"
    old.parent.mkdir(parents=True)
    old.write_text("stale", encoding="utf-8")
    sandbox.ship("windows")
    assert not old.exists()
    assert (sandbox.release_dir / "windows" / f"{APP}.exe").is_file()


def test_windows_needs_no_windows_build_variables(sandbox: ShipSandbox) -> None:
    env = {key: value for key, value in sandbox.env.items() if not key.startswith("WINDOWS_")}
    entries = run_ship(
        "windows", sandbox.project, sandbox.release_dir, False, env, godot=sandbox.godot
    )
    assert [entry.path for entry in entries] == [f"windows/{APP}.exe"]


def test_app_name_strips_non_alphanumerics_and_falls_back_to_game(tmp_path: Path) -> None:
    project = tmp_path / "project.godot"
    project.write_text('[application]\n\nconfig/name="My Game: 2!"\n', encoding="utf-8")
    assert app_name(project) == "MyGame2"
    project.write_text('[application]\n\nconfig/name="!!"\n', encoding="utf-8")
    assert app_name(project) == "Game"
    project.write_text("config_version=5\n", encoding="utf-8")
    assert app_name(project) == "Game"


# Web --------------------------------------------------------------------------------------------


def test_a_large_web_pack_warns(sandbox: ShipSandbox, capsys: pytest.CaptureFixture[str]) -> None:
    sandbox.web_pack_bytes = WEB_PACK_LIMIT + 5 * 1024 * 1024
    entries = sandbox.ship("web")
    assert [entry.path for entry in entries] == ["web"]
    assert "WARNING [ship.web_pack_large]: index.pck is 43.0 MB, over 38 MB" in _output(capsys)


def test_a_web_pack_at_the_limit_does_not_warn(
    sandbox: ShipSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox.web_pack_bytes = WEB_PACK_LIMIT
    sandbox.ship("web")
    assert "ship.web_pack_large" not in _output(capsys)


def test_the_web_folder_is_hashed_as_a_folder(sandbox: ShipSandbox) -> None:
    (entry,) = sandbox.ship("web")
    web = sandbox.release_dir / "web"
    assert {path.name for path in web.iterdir()} >= {"index.html", "index.pck", "index.wasm"}
    assert entry.sha256 == artifact_sha256(web)


# Android ----------------------------------------------------------------------------------------


def test_android_keystore_reaches_only_the_export_child(
    sandbox: ShipSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox.ship("android", ANDROID_KEYSTORE_ALIAS="release-key")
    exports = [
        env
        for call, env in zip(sandbox.godot.calls, sandbox.godot.envs, strict=True)
        if call[0] == "--export-release"
    ]
    assert exports == [
        {
            "GODOT_ANDROID_KEYSTORE_RELEASE_PATH": sandbox.env["ANDROID_KEYSTORE"],
            "GODOT_ANDROID_KEYSTORE_RELEASE_USER": "release-key",
            "GODOT_ANDROID_KEYSTORE_RELEASE_PASSWORD": _KEYSTORE_PASSWORD,
        }
    ]
    others = [
        env
        for call, env in zip(sandbox.godot.calls, sandbox.godot.envs, strict=True)
        if call[0] != "--export-release"
    ]
    assert all(env is None for env in others)
    output = _output(capsys)
    assert _KEYSTORE_PASSWORD not in output
    assert "GODOT_ANDROID_KEYSTORE_RELEASE_PASSWORD=***" in output


def test_android_alias_defaults_to_upload(sandbox: ShipSandbox) -> None:
    sandbox.ship("android")
    (env,) = [env for env in sandbox.godot.envs if env is not None]
    assert env["GODOT_ANDROID_KEYSTORE_RELEASE_USER"] == "upload"


def test_android_installs_the_build_template_only_when_missing(sandbox: ShipSandbox) -> None:
    sandbox.ship("android")
    (first,) = sandbox.godot_commands("--export-release")
    assert first[3:] == ["--install-android-build-template"]

    (sandbox.game / "android" / "build").mkdir(parents=True)
    sandbox.godot.calls.clear()
    sandbox.ship("android")
    (second,) = sandbox.godot_commands("--export-release")
    assert "--install-android-build-template" not in second


# iOS --------------------------------------------------------------------------------------------


def test_ios_patches_the_preset_for_the_export_and_restores_it_byte_for_byte(
    sandbox: ShipSandbox,
) -> None:
    presets = sandbox.game / "export_presets.cfg"
    original = presets.read_bytes()
    sandbox.ship("ios")
    seen = sandbox.presets_at_export["iOS"]
    assert 'application/app_store_team_id="SMOKE00000"' in seen
    assert f'application/provisioning_profile_uuid_release="{_PROFILE_UUID}"' in seen
    assert presets.read_bytes() == original
    (cms,) = [call for call in sandbox.calls("security") if call[:1] == ["cms"]]
    assert cms == ["cms", "-D", "-i", sandbox.env["IOS_PROVISIONING_PROFILE"]]


def test_ios_preset_is_restored_when_the_export_fails(sandbox: ShipSandbox) -> None:
    presets = sandbox.game / "export_presets.cfg"
    original = presets.read_bytes()
    sandbox.failing_preset = "iOS"
    with pytest.raises(ShipError) as caught:
        sandbox.ship("ios")
    assert caught.value.code == "ship.export_failed"
    assert presets.read_bytes() == original


def test_an_unreadable_profile_stops_before_the_ios_export(sandbox: ShipSandbox) -> None:
    presets = sandbox.game / "export_presets.cfg"
    original = presets.read_bytes()
    with pytest.raises(ShipError) as caught:
        sandbox.ship("ios", NMG_SHIP_FAKE_PROFILE_FAIL="1")
    assert caught.value.code == "ship.ios_profile_invalid"
    assert sandbox.exports() == []
    assert presets.read_bytes() == original


def test_patch_preset_options_replaces_only_the_named_section() -> None:
    text = (
        '[preset.0]\n\nname="macOS"\n\n[preset.0.options]\n\napplication/app_store_team_id="A"\n\n'
        '[preset.1]\n\nname="iOS"\n\n[preset.1.options]\n\napplication/app_store_team_id=""\n'
        'application/bundle_identifier="com.nmg.x"\n'
    )
    patched = patch_preset_options(
        text,
        1,
        {
            "application/app_store_team_id": "TEAM",
            "application/provisioning_profile_uuid_release": "UUID",
        },
    )
    assert patched.count('application/app_store_team_id="A"') == 1
    assert 'application/app_store_team_id="TEAM"' in patched
    assert patched.endswith(
        'application/bundle_identifier="com.nmg.x"\n'
        'application/provisioning_profile_uuid_release="UUID"\n'
    )


# Preflight ---------------------------------------------------------------------------------------


def test_missing_notarization_team_fails_before_any_godot_and_leaks_no_secret(
    sandbox: ShipSandbox,
) -> None:
    env = {key: value for key, value in sandbox.env.items() if key != "NOTARIZATION_TEAM_ID"}
    with pytest.raises(ShipError) as caught:
        run_ship("macos", sandbox.project, sandbox.release_dir, False, env, godot=sandbox.godot)
    error = caught.value
    assert error.code == "ship.env_missing"
    assert "NOTARIZATION_TEAM_ID" in error.message
    assert _APP_PASSWORD not in error.message + error.remediation
    assert sandbox.godot.calls == []


def test_no_identity_for_the_team_fails_before_any_godot(sandbox: ShipSandbox) -> None:
    with pytest.raises(ShipError) as caught:
        sandbox.ship(
            "macos",
            NMG_SHIP_FAKE_IDENTITIES='  1) AB "Developer ID Application: Other (OTHER00000)"\n',
        )
    assert caught.value.code == "ship.signing_identity_missing"
    assert sandbox.invoked("security")
    assert sandbox.godot.calls == []


def test_a_project_path_that_is_not_project_godot_is_rejected(sandbox: ShipSandbox) -> None:
    with pytest.raises(ShipError) as caught:
        run_ship("windows", sandbox.game, sandbox.release_dir, False, sandbox.env)
    assert caught.value.code == "ship.project_missing"


def test_missing_export_presets_is_reported(sandbox: ShipSandbox) -> None:
    (sandbox.game / "export_presets.cfg").unlink()
    with pytest.raises(ShipError) as caught:
        sandbox.ship("windows")
    assert caught.value.code == "ship.presets_missing"
    assert "/onboard-consumer" in caught.value.remediation


def test_a_missing_preset_is_named(sandbox: ShipSandbox) -> None:
    presets = sandbox.game / "export_presets.cfg"
    presets.write_text(
        presets.read_text(encoding="utf-8").replace('name="Web"', 'name="Browser"'),
        encoding="utf-8",
    )
    with pytest.raises(ShipError) as caught:
        sandbox.ship("all")
    assert caught.value.code == "ship.preset_missing"
    assert "Web" in caught.value.message
    assert sandbox.godot.calls == []


def _no_godot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make binary resolution fail, whatever Godot this machine has installed."""

    def not_found(*_args: object, **_kwargs: object) -> Path:
        raise PipelineError("godot.not_found", "Godot was not found.", "Install Godot 4.", "godot")

    monkeypatch.setattr(ship_runner, "resolve_godot", not_found)


def test_without_a_godot_binary_a_real_ship_fails_with_godot_not_found(
    sandbox: ShipSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_godot(monkeypatch)
    with pytest.raises(PipelineError) as caught:
        run_ship("windows", sandbox.project, sandbox.release_dir, False, sandbox.env)
    assert caught.value.code == "godot.not_found"


# Dry run ----------------------------------------------------------------------------------------


def test_dry_run_prints_every_command_and_runs_no_godot(
    sandbox: ShipSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    entries = sandbox.ship("all", dry_run=True)
    assert entries == []
    assert sandbox.godot.calls == []
    assert not sandbox.invoked("codesign")
    assert not sandbox.invoked("xcrun")
    output = _output(capsys)
    assert "DRY-RUN: godot --headless --audio-driver Dummy --path" in output
    assert "--check-only -s res://main.gd" in output
    assert "--export-release macOS" in output
    assert "--export-release 'Windows Desktop'" in output
    assert "GODOT_ANDROID_KEYSTORE_RELEASE_PASSWORD=***" in output
    assert _KEYSTORE_PASSWORD not in output
    assert _APP_PASSWORD not in output
    assert "DRY-RUN: security cms -D -i" in output
    assert "DRY-RUN: notarization pass (no submission) for team SMOKE00000" in output
    for platform in ("macos", "windows", "ios", "android", "web"):
        dry = (sandbox.release_dir / platform / "DRY-RUN.txt").read_text(encoding="utf-8")
        assert dry.splitlines()[0].startswith("DRY-RUN: godot --headless")
        assert "--export-release" in dry
    notes = (sandbox.release_dir / "RELEASE-NOTES.md").read_text(encoding="utf-8")
    assert "DRY RUN" in notes


def test_dry_run_keeps_an_earlier_artifact_and_the_presets(sandbox: ShipSandbox) -> None:
    sandbox.ship("windows")
    presets = (sandbox.game / "export_presets.cfg").read_bytes()
    sandbox.ship("all", dry_run=True)
    assert (sandbox.release_dir / "windows" / f"{APP}.exe").is_file()
    assert (sandbox.game / "export_presets.cfg").read_bytes() == presets


def test_dry_run_without_godot_prints_the_literal_godot(
    sandbox: ShipSandbox, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_godot(monkeypatch)
    run_ship("windows", sandbox.project, sandbox.release_dir, True, sandbox.env)
    assert "DRY-RUN: godot --headless" in _output(capsys)


# CLI --------------------------------------------------------------------------------------------


def test_cli_prints_the_code_and_remediation_and_exits_1(
    sandbox: ShipSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {key: value for key, value in sandbox.env.items() if key != "NOTARIZATION_TEAM_ID"}
    monkeypatch.setattr(os, "environ", env)
    code = ship_main(["macos", "--project", str(sandbox.project)])
    assert code == 1
    err = capsys.readouterr().err
    assert "ERROR [ship.env_missing]:" in err
    assert "Remediation:" in err


def test_cli_dry_run_defaults_the_release_folder_to_the_consumer_root(
    sandbox: ShipSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(os, "environ", dict(sandbox.env))
    _no_godot(monkeypatch)
    code = ship_main(["all", "--project", str(sandbox.project), "--dry-run"])
    assert code == 0
    assert "Release notes:" in capsys.readouterr().out
    assert (sandbox.game.parent / "release" / "RELEASE-NOTES.md").is_file()
    assert sandbox.calls() == []


def test_cli_rejects_an_unknown_target_with_argparse_exit_2(sandbox: ShipSandbox) -> None:
    with pytest.raises(SystemExit) as caught:
        ship_main(["linux", "--project", str(sandbox.project)])
    assert caught.value.code == 2
