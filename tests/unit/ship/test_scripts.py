"""The macOS sign and notarize scripts, run for real against PATH shims (#6, FR4; #95; #249).

No test runs a real codesign, notarytool, or stapler. The shims record argv and write the outputs
the scripts expect. The app is the ``.app`` a Godot macOS export writes into ``release/macos/``.
"""

from __future__ import annotations

from tests.ship_fakes import ShipSandbox, run_script


def test_sign_macos_runs_codesign_then_verify(sandbox: ShipSandbox) -> None:
    app = sandbox.release_dir / "macos" / "DogfoodGame.app"
    app.mkdir(parents=True)
    result = run_script(sandbox, "sign-macos.sh", str(app), "--identity", "Example Identity")
    assert result.returncode == 0, result.stderr
    first, second = sandbox.calls("codesign")
    assert first[:8] == [
        "--force",
        "--deep",
        "--options",
        "runtime",
        "--timestamp",
        "--sign",
        "Example Identity",
        str(app),
    ]
    assert second[:3] == ["--verify", "--strict", "--verbose=2"]


def test_sign_macos_failure_exits_1(sandbox: ShipSandbox) -> None:
    app = sandbox.release_dir / "macos" / "DogfoodGame.app"
    app.mkdir(parents=True)
    result = run_script(
        sandbox,
        "sign-macos.sh",
        str(app),
        "--identity",
        "Example Identity",
        extra_env={"NMG_SHIP_FAKE_CODESIGN_FAIL": "1"},
    )
    assert result.returncode == 1
    assert "Remediation:" in result.stderr


def test_notarize_dry_run_reports_a_pass_and_submits_nothing(sandbox: ShipSandbox) -> None:
    app = sandbox.release_dir / "macos" / "DogfoodGame.app"
    result = run_script(sandbox, "notarize-macos.sh", str(app), "--dry-run")
    assert result.returncode == 0
    assert "DRY-RUN: notarization pass (no submission) for team SMOKE00000" in result.stdout
    assert sandbox.calls() == []


def test_notarize_submits_waits_and_staples(sandbox: ShipSandbox) -> None:
    app = sandbox.release_dir / "macos" / "DogfoodGame.app"
    app.mkdir(parents=True)
    result = run_script(sandbox, "notarize-macos.sh", str(app))
    assert result.returncode == 0, result.stderr
    (submit,) = [call for call in sandbox.calls("xcrun") if call[:2] == ["notarytool", "submit"]]
    assert "--team-id" in submit
    assert submit[submit.index("--team-id") + 1] == "SMOKE00000"
    assert "--wait" in submit
    assert ["stapler", "staple", str(app)] in sandbox.calls("xcrun")
    assert "placeholder-app-password" not in result.stdout + result.stderr


def test_notarize_rejected_status_exits_1_and_does_not_staple(sandbox: ShipSandbox) -> None:
    app = sandbox.release_dir / "macos" / "DogfoodGame.app"
    app.mkdir(parents=True)
    result = run_script(
        sandbox,
        "notarize-macos.sh",
        str(app),
        extra_env={"NMG_SHIP_FAKE_NOTARY_FAIL": "1"},
    )
    assert result.returncode == 1
    assert ["stapler", "staple", str(app)] not in sandbox.calls("xcrun")


def test_notarize_missing_team_exits_2_naming_the_variable(sandbox: ShipSandbox) -> None:
    app = sandbox.release_dir / "macos" / "DogfoodGame.app"
    app.mkdir(parents=True)
    result = run_script(sandbox, "notarize-macos.sh", str(app), without=("NOTARIZATION_TEAM_ID",))
    assert result.returncode == 2
    assert "NOTARIZATION_TEAM_ID" in result.stderr
    assert "placeholder-app-password" not in result.stderr


_APPLE_ID_PAIR_AND_TEAM = (
    "NOTARIZATION_APPLE_ID",
    "NOTARIZATION_APP_SPECIFIC_PASSWORD",
    "NOTARIZATION_TEAM_ID",
)


def test_notarize_keychain_profile_submits_with_no_apple_id_or_password(
    sandbox: ShipSandbox,
) -> None:
    app = sandbox.release_dir / "macos" / "DogfoodGame.app"
    app.mkdir(parents=True)
    result = run_script(
        sandbox,
        "notarize-macos.sh",
        str(app),
        extra_env={"NOTARIZATION_KEYCHAIN_PROFILE": "nmg-notary"},
        without=_APPLE_ID_PAIR_AND_TEAM,
    )
    assert result.returncode == 0, result.stderr
    (submit,) = [call for call in sandbox.calls("xcrun") if call[:2] == ["notarytool", "submit"]]
    assert submit[submit.index("--keychain-profile") + 1] == "nmg-notary"
    assert "--wait" in submit
    assert "--apple-id" not in submit
    assert "--password" not in submit
    assert "--keychain-profile nmg-notary" in result.stdout
    assert ["stapler", "staple", str(app)] in sandbox.calls("xcrun")
    assert "WARNING" not in result.stderr
    assert "placeholder-app-password" not in result.stdout + result.stderr


def test_notarize_password_path_still_submits_and_warns_about_arguments(
    sandbox: ShipSandbox,
) -> None:
    app = sandbox.release_dir / "macos" / "DogfoodGame.app"
    app.mkdir(parents=True)
    result = run_script(sandbox, "notarize-macos.sh", str(app))
    assert result.returncode == 0, result.stderr
    assert "WARNING: the app-specific password is visible in process arguments" in result.stderr
    assert "NOTARIZATION_KEYCHAIN_PROFILE" in result.stderr
    assert "placeholder-app-password" not in result.stdout + result.stderr
    (submit,) = [call for call in sandbox.calls("xcrun") if call[:2] == ["notarytool", "submit"]]
    assert submit[submit.index("--apple-id") + 1] == "ship-test@example.invalid"
    assert submit[submit.index("--password") + 1] == "placeholder-app-password"
    assert submit[submit.index("--team-id") + 1] == "SMOKE00000"


def test_notarize_dry_run_with_keychain_profile_submits_nothing(sandbox: ShipSandbox) -> None:
    app = sandbox.release_dir / "macos" / "DogfoodGame.app"
    result = run_script(
        sandbox,
        "notarize-macos.sh",
        str(app),
        "--dry-run",
        extra_env={"NOTARIZATION_KEYCHAIN_PROFILE": "nmg-notary"},
        without=_APPLE_ID_PAIR_AND_TEAM,
    )
    assert result.returncode == 0, result.stderr
    assert "DRY-RUN: notarization pass (no submission)" in result.stdout
    assert sandbox.calls() == []
