"""The ship runner end to end against a fake Godot and PATH shims (#6; #249 FR9, AC9).

No test runs Godot, contacts Apple, Google, or a store, reads a keychain, or reads a real
credential. Each run uses the sandbox's placeholder environment. Godot is a ``FakeGodotRunner``
whose export writes the artifact, and every other tool is a shim that records its argv.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from nmg_game_dev.godot.project import parse_config
from nmg_game_dev.godot.runner import CommandResult
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.ship import runner as ship_runner
from nmg_game_dev.ship.__main__ import main as ship_main
from nmg_game_dev.ship.artifacts import artifact_sha256
from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.runner import (
    EXPORT_TIMEOUT_S,
    WEB_PACK_LIMIT,
    app_name,
    patch_preset_options,
    project_scripts,
    run_ship,
)
from nmg_game_dev.ship.version import patch_preset_literals
from tests.ship_fakes import (
    APP,
    VERSION_KEYS,
    ShipSandbox,
    changed_keys,
    consumer_bytes,
    write_mobile_report,
)

_KEYSTORE_PASSWORD = "placeholder-keystore-password"
_APP_PASSWORD = "placeholder-app-password"
_IDENTITY = "Developer ID Application: Example Studio (SMOKE00000)"
_PROFILE_UUID = "11111111-2222-3333-4444-555555555555"
_CRATE = {"class": "standard_prop", "tris": 2800, "max_texture_px": 1024, "materials": 1}


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    return captured.out + captured.err


# Order of the gates and exports -----------------------------------------------------------------


def test_all_runs_import_then_script_check_then_tests_then_budget_then_every_export(
    sandbox: ShipSandbox,
) -> None:
    (sandbox.game / "tests").mkdir()
    (sandbox.game / "tests" / "run_tests.gd").write_text("extends SceneTree\n", encoding="utf-8")
    write_mobile_report(sandbox.game, "Props/Crate", _CRATE)

    entries = sandbox.ship("all")

    commands = sandbox.godot_commands()
    assert commands[0] == ["--import"]
    checks = [call for call in commands if call[:1] == ["--check-only"]]
    assert commands[1 : 1 + len(checks)] == checks
    assert [call[2] for call in checks] == [
        "res://main.gd",
        "res://scripts/player.gd",
        "res://tests/run_tests.gd",
    ]
    assert all(call[1] == "-s" for call in checks)
    assert commands[1 + len(checks)] == ["-s", "res://tests/run_tests.gd"]
    assert commands[2 + len(checks)] == _SMOKE_ARGS
    assert sandbox.exports() == ["macOS", "Windows Desktop", "iOS", "Android", "Web"]
    first_export = next(i for i, call in enumerate(commands) if call[0] == "--export-release")
    assert first_export == len(checks) + 3
    assert [entry.platform for entry in entries] == ["macos", "windows", "ios", "android", "web"]


_SMOKE_ARGS = [
    "--fixed-fps",
    "60",
    "--quit-after",
    "600",
    "--",
    "--nmg-autoplay",
    "--nmg-test-saves",
]


def test_a_failing_smoke_run_stops_the_ship_before_any_export(sandbox: ShipSandbox) -> None:
    sandbox.godot.responses["--fixed-fps"] = CommandResult(
        0, stdout="SCRIPT ERROR: Invalid call. Nonexistent function 'boom'.\n"
    )
    with pytest.raises(ShipError) as caught:
        sandbox.ship("all")
    error = caught.value
    assert error.code == "ship.smoke_failed"
    assert error.stage == "smoke"
    assert "smoke.runtime_error" in error.message
    assert "SCRIPT ERROR: Invalid call" in error.message
    assert error.remediation.startswith("Fix the first error above")
    assert sandbox.exports() == []


def test_a_clean_smoke_run_lets_the_export_proceed(sandbox: ShipSandbox) -> None:
    sandbox.godot.responses["--fixed-fps"] = CommandResult(0, stdout="Godot Engine v4\n")
    sandbox.ship("windows")
    assert sandbox.godot_commands("--fixed-fps") == [_SMOKE_ARGS]
    assert sandbox.exports() == ["Windows Desktop"]


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


@pytest.mark.parametrize(
    "result",
    [
        CommandResult(0, stdout="ERROR: Failed loading resource: res://broken.glb\n"),
        CommandResult(1, stderr="import crashed\n"),
    ],
)
def test_a_failed_import_stops_before_the_script_check(
    sandbox: ShipSandbox, result: CommandResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Godot's --import usually exits 0 on a broken resource; the ERROR: line is the signal.
    calls: list[list[str]] = []
    original = sandbox.godot.run

    def run(args: list[str], **kwargs: object) -> CommandResult:
        calls.append(list(args))
        if args[:1] == ["--import"]:
            return result
        return original(args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sandbox.godot, "run", run)
    with pytest.raises(ShipError) as caught:
        sandbox.ship("windows")
    assert caught.value.code == "ship.import_failed"
    assert calls == [["--import"]]


def test_a_fresh_checkout_is_imported_before_class_name_scripts_are_checked(
    sandbox: ShipSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh clone has no .godot/ global class cache until --import builds it.

    The fake reproduces Godot 4: --check-only on a script naming a class_name type fails with
    'Could not find type' until an --import has run in that project.
    """
    (sandbox.game / "scripts" / "thing.gd").write_text(
        "class_name FooThing\nextends Node\n", encoding="utf-8"
    )
    (sandbox.game / "scripts" / "user.gd").write_text(
        "extends Node\nvar thing: FooThing\n", encoding="utf-8"
    )
    imported: list[Path] = []
    original = sandbox.godot.run

    def run(args: list[str], *, project: Path, **kwargs: object) -> CommandResult:
        if args[:1] == ["--import"]:
            imported.append(project)
        if args[:1] == ["--check-only"] and args[2] == "res://scripts/user.gd" and not imported:
            return CommandResult(
                1, stderr='SCRIPT ERROR: Parse Error: Could not find type "FooThing".\n'
            )
        return original(args, project=project, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sandbox.godot, "run", run)
    entries = sandbox.ship("windows")
    assert [entry.platform for entry in entries] == ["windows"]
    assert imported == [sandbox.game.absolute()]


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
    # No keystore value is printed: path, alias, and password are all masked.
    assert _KEYSTORE_PASSWORD not in output
    assert sandbox.env["ANDROID_KEYSTORE"] not in output
    assert "release-key" not in output
    for name in ("PATH", "USER", "PASSWORD"):
        assert f"GODOT_ANDROID_KEYSTORE_RELEASE_{name}=***" in output


def test_exports_get_the_long_export_timeout_and_gates_the_default(sandbox: ShipSandbox) -> None:
    sandbox.ship("android")
    for call, timeout in zip(sandbox.godot.calls, sandbox.godot.timeouts, strict=True):
        if call[0] == "--export-release":
            assert timeout == EXPORT_TIMEOUT_S
        else:
            assert timeout is None, call


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


def test_patch_preset_options_escapes_quotes_and_backslashes() -> None:
    text = '[preset.1]\n\nname="iOS"\n\n[preset.1.options]\n\napplication/app_store_team_id=""\n'
    patched = patch_preset_options(text, 1, {"application/app_store_team_id": 'AB"C\\D'})
    assert 'application/app_store_team_id="AB\\"C\\\\D"\n' in patched
    assert read_back(patched) == 'AB"C\\D'


def read_back(text: str) -> str:
    """The team id Godot would read back from the patched preset text."""
    raw = parse_config(text)[("preset.1.options", "application/app_store_team_id")]
    value = json.loads(raw)
    assert isinstance(value, str)
    return value


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
    assert output.index(" --import") < output.index("--check-only -s res://main.gd")
    assert "--export-release macOS" in output
    assert "--export-release 'Windows Desktop'" in output
    assert "GODOT_ANDROID_KEYSTORE_RELEASE_PASSWORD=***" in output
    assert "GODOT_ANDROID_KEYSTORE_RELEASE_PATH=***" in output
    assert "GODOT_ANDROID_KEYSTORE_RELEASE_USER=***" in output
    assert _KEYSTORE_PASSWORD not in output
    assert _APP_PASSWORD not in output
    assert "DRY-RUN: security cms -D -i" in output
    assert "DRY-RUN: notarization pass (no submission) for team SMOKE00000" in output
    for platform in ("macos", "windows", "ios", "android", "web"):
        dry = (sandbox.release_dir / platform / "DRY-RUN.txt").read_text(encoding="utf-8")
        assert dry.splitlines()[0] == "secrets: no matches"
        assert dry.splitlines()[1].startswith("DRY-RUN: godot --headless")
        assert "--export-release" in dry
    notes = (sandbox.release_dir / "RELEASE-NOTES.md").read_text(encoding="utf-8")
    assert "DRY RUN" in notes


def test_dry_run_prints_the_smoke_command_and_runs_no_godot(
    sandbox: ShipSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox.ship("windows", dry_run=True)
    output = _output(capsys)
    assert "DRY-RUN: godot --headless --audio-driver Dummy --path" in output
    assert "--fixed-fps 60 --quit-after 600 -- --nmg-autoplay --nmg-test-saves" in output
    assert sandbox.godot.calls == []
    dry = (sandbox.release_dir / "windows" / "DRY-RUN.txt").read_text(encoding="utf-8")
    assert "--nmg-autoplay --nmg-test-saves" in dry


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


# Build version, changelog, and release notes (#254) -----------------------------------------------

_ANDROID_INDEX = 2
"""The Android preset's ``[preset.N]`` index in ``render_export_presets``."""


def _add_changelog_section(
    sandbox: ShipSandbox, heading: str, text: str = "- Faster loading."
) -> None:
    """Append a ``## <heading>`` section with ``text`` to the consumer's CHANGELOG.md."""
    path = sandbox.game.parent / "CHANGELOG.md"
    path.write_text(
        path.read_text(encoding="utf-8") + f"\n## {heading}\n\n{text}\n", encoding="utf-8"
    )


def _set_android_version_code(sandbox: ShipSandbox, code: str) -> None:
    presets = sandbox.game / "export_presets.cfg"
    text = presets.read_text(encoding="utf-8")
    presets.write_text(patch_preset_literals(text, _ANDROID_INDEX, {"version/code": code}))


def _add_project_tests(sandbox: ShipSandbox, summary: str = "42 passed, 0 failed") -> None:
    """Give the sandbox a project test runner whose output ends with ``summary``."""
    tests = sandbox.game / "tests"
    tests.mkdir()
    (tests / "run_tests.gd").write_text("extends SceneTree\n", encoding="utf-8")
    sandbox.godot.responses["-s"] = lambda args, project: CommandResult(0, stdout=f"{summary}\n")


def test_bump_minor_writes_the_version_to_the_project_and_every_preset(
    sandbox: ShipSandbox,
) -> None:
    _add_changelog_section(sandbox, "1.3.0")
    _set_android_version_code(sandbox, "4")
    presets = sandbox.game / "export_presets.cfg"
    project_before = sandbox.project.read_text(encoding="utf-8")
    presets_before = presets.read_text(encoding="utf-8")

    sandbox.ship("all", bump="minor")

    project_after = sandbox.project.read_text(encoding="utf-8")
    presets_after = presets.read_text(encoding="utf-8")
    assert parse_config(project_after)[("application", "config/version")] == '"1.3.0"'
    assert changed_keys(project_before, project_after) == {"config/version"}
    assert changed_keys(presets_before, presets_after) <= VERSION_KEYS
    options = parse_config(presets_after)
    assert options[("preset.2.options", "version/name")] == '"1.3.0"'
    assert options[("preset.2.options", "version/code")] == "5"
    assert options[("preset.3.options", "application/file_version")] == '"1.3.0.0"'
    seen = sandbox.presets_at_export
    assert 'application/short_version="1.3.0"' in seen["macOS"]
    assert 'application/version="1.3.0"' in seen["iOS"]
    assert "version/code=5" in seen["Android"]
    assert 'application/product_version="1.3.0.0"' in seen["Windows Desktop"]


def test_no_version_flag_leaves_both_files_byte_identical(sandbox: ShipSandbox) -> None:
    before = consumer_bytes(sandbox)
    sandbox.ship("windows")
    assert consumer_bytes(sandbox) == before


@pytest.mark.parametrize(
    ("flags", "code"),
    [
        ({"version": "1.2.3"}, "ship.version_not_increased"),
        ({"version": "1.0.0"}, "ship.version_not_increased"),
        ({"version": "1.3"}, "ship.version_invalid"),
        ({"bump": "minor", "version": "1.3.0"}, "ship.version_invalid"),
    ],
)
def test_a_refused_version_stops_before_any_godot_command_or_write(
    sandbox: ShipSandbox, flags: dict[str, str], code: str
) -> None:
    _add_changelog_section(sandbox, "1.3.0")
    before = consumer_bytes(sandbox)
    with pytest.raises(ShipError) as caught:
        sandbox.ship("all", bump=flags.get("bump"), version=flags.get("version"))
    assert caught.value.code == code
    assert sandbox.godot.calls == []
    assert consumer_bytes(sandbox) == before
    assert not sandbox.release_dir.exists()


def test_a_project_with_no_version_stops_with_version_missing(sandbox: ShipSandbox) -> None:
    sandbox.project.write_text(
        sandbox.project.read_text(encoding="utf-8").replace('config/version="1.2.3"\n', ""),
        encoding="utf-8",
    )
    before = consumer_bytes(sandbox)
    with pytest.raises(ShipError) as caught:
        sandbox.ship("windows")
    assert caught.value.code == "ship.version_missing"
    assert sandbox.godot.calls == []
    assert consumer_bytes(sandbox) == before


def test_a_missing_changelog_section_stops_before_any_godot_or_tool(sandbox: ShipSandbox) -> None:
    before = consumer_bytes(sandbox)
    with pytest.raises(ShipError) as caught:
        sandbox.ship("macos", version="1.3.0")
    assert caught.value.code == "ship.changelog_missing"
    assert sandbox.godot.calls == []
    assert sandbox.calls() == []
    assert consumer_bytes(sandbox) == before


@pytest.mark.parametrize("heading", ["1.3.0", "[1.3.0] - 2026-11-18"])
def test_a_changelog_heading_may_carry_brackets_and_a_date(
    sandbox: ShipSandbox, heading: str
) -> None:
    _add_changelog_section(sandbox, heading)
    entries = sandbox.ship("windows", bump="minor")
    assert [entry.platform for entry in entries] == ["windows"]


def test_a_failing_gate_writes_no_version_and_exports_nothing(sandbox: ShipSandbox) -> None:
    _add_changelog_section(sandbox, "1.3.0")
    sandbox.godot.responses["--check-only"] = CommandResult(1, stderr="SCRIPT ERROR: Parse Error\n")
    before = consumer_bytes(sandbox)
    with pytest.raises(ShipError) as caught:
        sandbox.ship("windows", version="1.3.0")
    assert caught.value.code == "ship.script_check_failed"
    assert consumer_bytes(sandbox) == before
    assert sandbox.exports() == []


def test_release_notes_carry_the_version_changes_and_gate_results(sandbox: ShipSandbox) -> None:
    _add_changelog_section(sandbox, "1.3.0", "- Faster loading.")
    _add_project_tests(sandbox, "42 passed, 0 failed")
    sandbox.ship("macos", version="1.3.0")
    notes = (sandbox.release_dir / "RELEASE-NOTES.md").read_text(encoding="utf-8")
    assert notes.startswith("# Release notes — 1.3.0\n")
    assert "## Changes\n\n- Faster loading.\n" in notes
    assert "- version: 1.2.3 -> 1.3.0\n" in notes
    assert "- changelog: ## 1.3.0 found\n" in notes
    assert "- tests: 42 passed, 0 failed\n" in notes
    assert "- smoke: passed\n" in notes
    assert "- mobile budgets: not applicable\n" in notes
    assert f"| macos | `macos/{APP}.app` | `" in notes
    assert notes.index("## Changes") < notes.index("## Gates") < notes.index("## Artifacts")


def test_a_project_without_tests_records_tests_not_present(sandbox: ShipSandbox) -> None:
    sandbox.ship("windows")
    notes = (sandbox.release_dir / "RELEASE-NOTES.md").read_text(encoding="utf-8")
    assert "- tests: not present\n" in notes


def test_a_dry_run_records_the_version_and_changelog_lines_in_each_dry_run_file(
    sandbox: ShipSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    _add_changelog_section(sandbox, "1.2.4")
    before = consumer_bytes(sandbox)
    entries = sandbox.ship("all", bump="patch", dry_run=True)
    assert entries == []
    assert sandbox.godot.calls == []
    assert consumer_bytes(sandbox) == before
    output = _output(capsys)
    assert "DRY-RUN: version 1.2.3 -> 1.2.4" in output
    assert "DRY-RUN: changelog ## 1.2.4 found in " in output
    for platform in ("macos", "windows", "ios", "android", "web"):
        dry = (sandbox.release_dir / platform / "DRY-RUN.txt").read_text(encoding="utf-8")
        assert dry.splitlines()[0] == "secrets: no matches"
        assert dry.splitlines()[1].startswith("DRY-RUN: godot --headless")
        assert "DRY-RUN: version 1.2.3 -> 1.2.4" in dry
        assert "DRY-RUN: changelog ## 1.2.4 found in " in dry


def test_cli_takes_bump_and_version_and_refuses_both(
    sandbox: ShipSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    _add_changelog_section(sandbox, "1.3.0")
    release = sandbox.game.parent / "release"
    args = ["windows", "--project", str(sandbox.project), "--release-dir", str(release)]
    assert ship_main([*args, "--dry-run", "--bump", "minor"]) == 0
    assert "DRY-RUN: version 1.2.3 -> 1.3.0" in _output(capsys)
    with pytest.raises(SystemExit) as caught:
        ship_main([*args, "--bump", "minor", "--version", "1.3.0"])
    assert caught.value.code == 2


# The secret scan gate (#255 AC4, FR3) -------------------------------------------------------------

_LEAKED_KEY = "msy_" + "Ab3dEf6hIj9kLm2nOp5q"


def _plant_key(sandbox: ShipSandbox, rel: str = "scripts/player.gd") -> None:
    path = sandbox.game / rel
    path.write_text(path.read_text(encoding="utf-8") + f'var key = "{_LEAKED_KEY}"\n')


def test_a_key_in_a_non_git_consumer_stops_the_ship_before_any_godot_call(
    sandbox: ShipSandbox,
) -> None:
    """AC4: outside a git work tree every regular file under the consumer is scanned."""
    _plant_key(sandbox)

    with pytest.raises(ShipError) as caught:
        sandbox.ship("macos")

    assert caught.value.code == "ship.secret_found"
    digest = hashlib.sha256(_LEAKED_KEY.encode()).hexdigest()
    assert f"scripts/player.gd:2: meshy msy_… (sha256:{digest})" in caught.value.message
    assert _LEAKED_KEY not in caught.value.message
    assert sandbox.godot.calls == []
    assert not sandbox.invoked("codesign")


def test_a_key_also_stops_a_dry_run_before_any_godot_call(
    sandbox: ShipSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    _plant_key(sandbox)

    with pytest.raises(ShipError) as caught:
        sandbox.ship("all", dry_run=True)

    assert caught.value.code == "ship.secret_found"
    assert sandbox.godot.calls == []
    assert not sandbox.release_dir.exists()
    assert _LEAKED_KEY not in _output(capsys)


def test_a_git_consumer_scans_tracked_files_only(sandbox: ShipSandbox) -> None:
    """AC4: in a git work tree only tracked files are scanned, so an untracked key passes."""
    consumer = sandbox.game.parent
    subprocess.run(["git", "-C", str(consumer), "init", "-q"], check=True, capture_output=True)
    _plant_key(sandbox)

    assert sandbox.ship("windows", dry_run=True) == []

    subprocess.run(
        ["git", "-C", str(consumer), "add", "game/scripts/player.gd"],
        check=True,
        capture_output=True,
    )
    with pytest.raises(ShipError) as caught:
        sandbox.ship("windows", dry_run=True)
    assert caught.value.code == "ship.secret_found"
    assert sandbox.godot.calls == []


def test_the_allow_file_suppresses_a_reviewed_false_positive(sandbox: ShipSandbox) -> None:
    _plant_key(sandbox)
    allow = sandbox.game.parent / ".nmg" / "secret-scan-allow"
    allow.parent.mkdir()
    digest = hashlib.sha256(_LEAKED_KEY.encode()).hexdigest()
    allow.write_text(f"sha256:{digest}\n", encoding="utf-8")

    entries = sandbox.ship("windows", dry_run=True)

    assert entries == []
    assert (sandbox.release_dir / "windows" / "DRY-RUN.txt").is_file()
