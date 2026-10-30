"""The ship runner end to end, against PATH shims (#6, FR1, FR2, FR7, FR9; AC1-AC9).

No test contacts Apple, Google, or a store, reads a keychain, or reads a real credential. Each run
uses the sandbox's placeholder environment, and every tool is a shim that records its argv.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from nmg_game_dev.ship.__main__ import main as ship_main
from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.runner import run_ship
from tests.ship_fakes import ShipSandbox

_PASSWORD = "placeholder-keystore-password"
_IDENTITY = "Developer ID Application: Example Studio (SMOKE00000)"


def _write_report(root: Path, rel_dir: str, report: dict[str, object]) -> None:
    folder = root / "Content" / rel_dir / "Mobile"
    folder.mkdir(parents=True)
    (folder / "nmg-asset.json").write_text(json.dumps(report), encoding="utf-8")


def test_macos_dry_run_plans_without_running_any_tool(sandbox: ShipSandbox) -> None:
    entries = run_ship("macos", sandbox.project, sandbox.release_dir, True, sandbox.env)
    assert entries == []
    assert sandbox.calls() == []
    dry = (sandbox.release_dir / "macos" / "DRY-RUN.txt").read_text(encoding="utf-8")
    assert "DRY-RUN:" in dry
    assert "DRY-RUN: notarization pass (no submission) for team SMOKE00000" in dry
    notes = (sandbox.release_dir / "RELEASE-NOTES.md").read_text(encoding="utf-8")
    assert "DRY RUN" in notes


def test_macos_ship_signs_notarizes_and_publishes(sandbox: ShipSandbox) -> None:
    entries = run_ship("macos", sandbox.project, sandbox.release_dir, False, sandbox.env)

    app = sandbox.release_dir / "macos" / "Dogfood.app"
    assert app.is_dir()
    (entry,) = entries
    assert entry.platform == "macos"
    assert entry.path == "macos/Dogfood.app"
    assert len(entry.sha256) == 64

    (uat,) = sandbox.calls("RunUAT.sh")
    for flag in ("BuildCookRun", "-platform=Mac", "-clientconfig=Shipping", "-cook", "-stage"):
        assert flag in uat
    sign_calls = sandbox.calls("codesign")
    assert ["--sign", _IDENTITY] == [sign_calls[0][5], sign_calls[0][6]]
    submit = [call for call in sandbox.calls("xcrun") if call[:2] == ["notarytool", "submit"]]
    assert submit[0][submit[0].index("--team-id") + 1] == "SMOKE00000"
    # Sign and notarize run on the archived app; the stapled, signed copy is what gets published.
    archived = sandbox.project.parent / "Saved" / "NmgShip" / "macos" / "Mac" / "Dogfood.app"
    assert ["stapler", "staple", str(archived)] in sandbox.calls("xcrun")

    notes = (sandbox.release_dir / "RELEASE-NOTES.md").read_text(encoding="utf-8")
    assert "macos/Dogfood.app" in notes
    assert entry.sha256 in notes


def test_rerun_replaces_an_earlier_artifact(sandbox: ShipSandbox) -> None:
    old = sandbox.release_dir / "macos" / "old-build.txt"
    old.parent.mkdir(parents=True)
    old.write_text("stale", encoding="utf-8")
    run_ship("macos", sandbox.project, sandbox.release_dir, False, sandbox.env)
    assert not old.exists()
    assert (sandbox.release_dir / "macos" / "Dogfood.app").is_dir()


def test_cook_leak_in_ios_blocks_the_platform_and_leaves_no_artifact(
    sandbox: ShipSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    env = {**sandbox.env, "NMG_SHIP_FAKE_COOK_LEAK": "Content/Props/Crate/Desktop/SM_Crate.uasset"}
    with pytest.raises(ShipError) as caught:
        run_ship("ios", sandbox.project, sandbox.release_dir, False, env)
    assert caught.value.code == "ship.cook_manifest_failed"
    assert "Content/Props/Crate/Desktop/SM_Crate.uasset" in capsys.readouterr().out
    assert not (sandbox.release_dir / "ios").exists()


def test_mobile_leak_in_macos_blocks_before_signing(sandbox: ShipSandbox) -> None:
    env = {**sandbox.env, "NMG_SHIP_FAKE_COOK_LEAK": "Content/Props/Crate/Mobile/SM_Crate.uasset"}
    with pytest.raises(ShipError) as caught:
        run_ship("macos", sandbox.project, sandbox.release_dir, False, env)
    assert caught.value.code == "ship.cook_manifest_failed"
    assert not (sandbox.release_dir / "macos" / "Dogfood.app").exists()
    assert not sandbox.invoked("codesign")
    assert not sandbox.invoked("xcrun")


def test_over_budget_mobile_asset_stops_before_any_build(sandbox: ShipSandbox) -> None:
    _write_report(
        sandbox.project.parent,
        "Props/Crate",
        {"class": "standard_prop", "tris": 4200, "max_texture_px": 1024, "materials": 1},
    )
    with pytest.raises(ShipError) as caught:
        run_ship("mobile", sandbox.project, sandbox.release_dir, False, sandbox.env)
    error = caught.value
    assert error.code == "ship.mobile_budget_exceeded"
    assert "Props/Crate: tris 4200 > 3000 (+1200)" in error.remediation
    assert not sandbox.invoked("RunUAT.sh")
    assert not (sandbox.release_dir / "ios").exists()
    assert not (sandbox.release_dir / "android").exists()


def test_mobile_variant_without_a_report_names_the_asset(sandbox: ShipSandbox) -> None:
    (sandbox.project.parent / "Content" / "Props" / "Lamp" / "Mobile").mkdir(parents=True)
    with pytest.raises(ShipError) as caught:
        run_ship("mobile", sandbox.project, sandbox.release_dir, False, sandbox.env)
    assert caught.value.code == "ship.budget_report_missing"
    assert "finalize Props/Lamp" in caught.value.remediation
    assert not sandbox.invoked("RunUAT.sh")


def test_mobile_ship_publishes_an_ipa_and_an_aab_without_leaking_the_keystore_password(
    sandbox: ShipSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    entries = run_ship("mobile", sandbox.project, sandbox.release_dir, False, sandbox.env)
    assert [entry.platform for entry in entries] == ["ios", "android"]
    assert (sandbox.release_dir / "ios" / "Dogfood.ipa").is_file()
    assert (sandbox.release_dir / "android" / "Dogfood.aab").is_file()
    platforms = [
        next(arg for arg in call if arg.startswith("-platform="))
        for call in sandbox.calls("RunUAT.sh")
    ]
    assert platforms == ["-platform=IOS", "-platform=Android"]
    output = capsys.readouterr()
    assert _PASSWORD not in output.out + output.err


def test_windows_ship_runs_the_remote_build_and_publishes_the_exe(sandbox: ShipSandbox) -> None:
    entries = run_ship("windows", sandbox.project, sandbox.release_dir, False, sandbox.env)
    assert [entry.path for entry in entries] == ["windows/Dogfood.exe"]
    assert (sandbox.release_dir / "windows" / "Dogfood.exe").is_file()
    remote_build = sandbox.calls("ssh")[0][-1]
    assert "BuildCookRun" in remote_build
    assert "-platform=Win64" in remote_build
    assert sandbox.invoked("scp")


def test_missing_notarization_team_fails_before_any_uat_and_leaks_no_secret(
    sandbox: ShipSandbox,
) -> None:
    env = {key: value for key, value in sandbox.env.items() if key != "NOTARIZATION_TEAM_ID"}
    with pytest.raises(ShipError) as caught:
        run_ship("macos", sandbox.project, sandbox.release_dir, False, env)
    error = caught.value
    assert error.code == "ship.env_missing"
    assert "NOTARIZATION_TEAM_ID" in error.message
    assert "placeholder-app-password" not in error.message + error.remediation
    assert not sandbox.invoked("RunUAT.sh")


def test_no_identity_for_the_team_fails_before_any_build(sandbox: ShipSandbox) -> None:
    env = {
        **sandbox.env,
        "NMG_SHIP_FAKE_IDENTITIES": '  1) AB "Developer ID Application: Other (OTHER00000)"\n',
    }
    with pytest.raises(ShipError) as caught:
        run_ship("macos", sandbox.project, sandbox.release_dir, False, env)
    assert caught.value.code == "ship.signing_identity_missing"
    assert sandbox.invoked("security")
    assert not sandbox.invoked("RunUAT.sh")


def test_cli_prints_the_code_and_remediation_and_exits_1(
    sandbox: ShipSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {key: value for key, value in sandbox.env.items() if key != "NOTARIZATION_TEAM_ID"}
    monkeypatch.setattr(os, "environ", env)
    code = ship_main(
        ["macos", "--project", str(sandbox.project), "--release-dir", str(sandbox.release_dir)]
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "ERROR [ship.env_missing]:" in err
    assert "Remediation:" in err


def test_cli_dry_run_exits_0_and_names_the_notes(
    sandbox: ShipSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(os, "environ", dict(sandbox.env))
    code = ship_main(
        [
            "all",
            "--project",
            str(sandbox.project),
            "--release-dir",
            str(sandbox.release_dir),
            "--dry-run",
        ]
    )
    assert code == 0
    assert "Release notes:" in capsys.readouterr().out
    assert sandbox.calls() == []


def test_cli_rejects_an_unknown_target_with_argparse_exit_2(sandbox: ShipSandbox) -> None:
    with pytest.raises(SystemExit) as caught:
        ship_main(["linux", "--project", str(sandbox.project)])
    assert caught.value.code == 2
