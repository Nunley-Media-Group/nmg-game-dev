"""The ship's bash scripts, run for real against PATH shims (#6; FR3-FR5, FR10; AC2, AC3, AC5, AC9).

No test runs a real UAT, codesign, notarytool, stapler, ssh, or scp. The shims record argv and
write the outputs the scripts expect.
"""

from __future__ import annotations

from pathlib import Path

from tests.ship_fakes import ShipSandbox, run_script

_PASSWORD = "placeholder-keystore-password"


def test_build_macos_dry_run_prints_the_uat_command_and_runs_nothing(sandbox: ShipSandbox) -> None:
    archive = sandbox.project.parent / "archive"
    result = run_script(
        sandbox,
        "build-macos.sh",
        "--project",
        str(sandbox.project),
        "--archive",
        str(archive),
        "--dry-run",
    )
    assert result.returncode == 0, result.stderr
    assert "DRY-RUN:" in result.stdout
    assert "-platform=Mac" in result.stdout
    assert "-clientconfig=Shipping" in result.stdout
    assert sandbox.calls() == []
    assert not archive.exists()


def test_build_macos_runs_uat_with_the_package_flags(sandbox: ShipSandbox) -> None:
    archive = sandbox.project.parent / "archive"
    result = run_script(
        sandbox,
        "build-macos.sh",
        "--project",
        str(sandbox.project),
        "--archive",
        str(archive),
    )
    assert result.returncode == 0, result.stderr
    (argv,) = sandbox.calls("RunUAT.sh")
    for flag in ("BuildCookRun", "-platform=Mac", "-clientconfig=Shipping", "-cook", "-stage"):
        assert flag in argv
    for flag in ("-pak", "-package", "-archive"):
        assert flag in argv
    assert (archive / "Mac" / "Dogfood.app").is_dir()


def test_build_macos_without_run_uat_exits_2_naming_ue_root(sandbox: ShipSandbox) -> None:
    result = run_script(
        sandbox,
        "build-macos.sh",
        "--project",
        str(sandbox.project),
        "--archive",
        str(sandbox.project.parent / "archive"),
        extra_env={"UE_ROOT": str(sandbox.project.parent / "missing-engine")},
    )
    assert result.returncode == 2
    assert "UE_ROOT" in result.stderr
    assert "Remediation:" in result.stderr


def test_build_macos_uat_failure_exits_1_with_remediation(sandbox: ShipSandbox) -> None:
    result = run_script(
        sandbox,
        "build-macos.sh",
        "--project",
        str(sandbox.project),
        "--archive",
        str(sandbox.project.parent / "archive"),
        extra_env={"NMG_SHIP_FAKE_UAT_FAIL": "1"},
    )
    assert result.returncode == 1
    assert "Remediation:" in result.stderr


def test_build_ios_requires_the_provisioning_profile(sandbox: ShipSandbox) -> None:
    result = run_script(
        sandbox,
        "build-ios.sh",
        "--project",
        str(sandbox.project),
        "--archive",
        str(sandbox.project.parent / "archive"),
        without=("IOS_PROVISIONING_PROFILE",),
    )
    assert result.returncode == 2
    assert "IOS_PROVISIONING_PROFILE" in result.stderr


def test_build_android_masks_the_keystore_password_in_output(sandbox: ShipSandbox) -> None:
    archive = sandbox.project.parent / "archive"
    result = run_script(
        sandbox,
        "build-android.sh",
        "--project",
        str(sandbox.project),
        "--archive",
        str(archive),
    )
    assert result.returncode == 0, result.stderr
    assert "KeyStorePassword=***" in result.stdout
    assert _PASSWORD not in result.stdout + result.stderr
    (argv,) = sandbox.calls("RunUAT.sh")
    assert any(_PASSWORD in arg for arg in argv)
    assert (archive / "Android" / "Dogfood.aab").is_file()


def test_build_android_dry_run_shows_the_mask_and_runs_nothing(sandbox: ShipSandbox) -> None:
    result = run_script(
        sandbox,
        "build-android.sh",
        "--project",
        str(sandbox.project),
        "--archive",
        str(sandbox.project.parent / "archive"),
        "--dry-run",
    )
    assert result.returncode == 0
    assert "KeyStorePassword=***" in result.stdout
    assert _PASSWORD not in result.stdout
    assert sandbox.calls() == []


def test_build_windows_runs_ssh_and_copies_the_package_back(sandbox: ShipSandbox) -> None:
    archive = sandbox.project.parent / "archive"
    listing = sandbox.project.parent / "listing.txt"
    result = run_script(
        sandbox,
        "build-windows.sh",
        "--archive",
        str(archive),
        "--listing",
        str(listing),
    )
    assert result.returncode == 0, result.stderr
    ssh_calls = sandbox.calls("ssh")
    assert len(ssh_calls) == 2
    assert "-platform=Win64" in ssh_calls[0][-1]
    assert "BuildCookRun" in ssh_calls[0][-1]
    assert "Common.uasset" in listing.read_text(encoding="utf-8")
    assert (archive / "Windows" / "Dogfood.exe").is_file()
    assert sandbox.invoked("scp")


def test_build_windows_dry_run_prints_ssh_lines_and_runs_nothing(sandbox: ShipSandbox) -> None:
    result = run_script(
        sandbox,
        "build-windows.sh",
        "--archive",
        str(sandbox.project.parent / "archive"),
        "--listing",
        str(sandbox.project.parent / "listing.txt"),
        "--dry-run",
    )
    assert result.returncode == 0
    assert result.stdout.count("DRY-RUN:") == 3
    assert sandbox.calls() == []


def test_sign_macos_runs_codesign_then_verify(sandbox: ShipSandbox) -> None:
    app = sandbox.project.parent / "archive" / "Mac" / "Dogfood.app"
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
    app = sandbox.project.parent / "archive" / "Mac" / "Dogfood.app"
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
    app = sandbox.project.parent / "archive" / "Mac" / "Dogfood.app"
    result = run_script(sandbox, "notarize-macos.sh", str(app), "--dry-run")
    assert result.returncode == 0
    assert "DRY-RUN: notarization pass (no submission) for team SMOKE00000" in result.stdout
    assert sandbox.calls() == []


def test_notarize_submits_waits_and_staples(sandbox: ShipSandbox) -> None:
    app = sandbox.project.parent / "archive" / "Mac" / "Dogfood.app"
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
    app = sandbox.project.parent / "archive" / "Mac" / "Dogfood.app"
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
    app = sandbox.project.parent / "archive" / "Mac" / "Dogfood.app"
    app.mkdir(parents=True)
    result = run_script(sandbox, "notarize-macos.sh", str(app), without=("NOTARIZATION_TEAM_ID",))
    assert result.returncode == 2
    assert "NOTARIZATION_TEAM_ID" in result.stderr
    assert "placeholder-app-password" not in result.stderr


def test_verify_cook_manifest_passes_a_clean_directory(sandbox: ShipSandbox) -> None:
    cooked = sandbox.project.parent / "cooked"
    (cooked / "Content" / "Shared").mkdir(parents=True)
    (cooked / "Content" / "Shared" / "Common.uasset").write_bytes(b"x")
    result = run_script(sandbox, "verify-cook-manifest.sh", "--variant", "mobile", str(cooked))
    assert result.returncode == 0
    assert "PASS" in result.stdout


def test_verify_cook_manifest_blocks_desktop_paths_in_mobile(sandbox: ShipSandbox) -> None:
    cooked = sandbox.project.parent / "cooked"
    (cooked / "Content" / "Props" / "Crate" / "Desktop").mkdir(parents=True)
    (cooked / "Content" / "Props" / "Crate" / "Desktop" / "SM_Crate.uasset").write_bytes(b"x")
    result = run_script(sandbox, "verify-cook-manifest.sh", "--variant", "mobile", str(cooked))
    assert result.returncode == 1
    assert "Content/Props/Crate/Desktop/SM_Crate.uasset" in result.stdout
    assert "Remediation:" in result.stderr


def test_verify_cook_manifest_blocks_mobile_paths_in_desktop_listing(sandbox: ShipSandbox) -> None:
    listing = sandbox.project.parent / "listing.txt"
    listing.write_text(
        "C:\\build\\Dogfood\\Content\\Props\\Crate\\Mobile\\SM_Crate.uasset\r\n", encoding="utf-8"
    )
    result = run_script(sandbox, "verify-cook-manifest.sh", "--variant", "desktop", str(listing))
    assert result.returncode == 1
    assert "Mobile/SM_Crate.uasset" in result.stdout


def test_verify_cook_manifest_bad_arguments_exit_2(sandbox: ShipSandbox) -> None:
    result = run_script(sandbox, "verify-cook-manifest.sh", "--variant", "tablet", "/tmp")
    assert result.returncode == 2
    assert "Remediation:" in result.stderr
    missing = run_script(
        sandbox, "verify-cook-manifest.sh", "--variant", "desktop", str(Path("/no/such/dir"))
    )
    assert missing.returncode == 2


def test_verify_cook_manifest_dry_run_does_not_read_the_package(sandbox: ShipSandbox) -> None:
    cooked = sandbox.project.parent / "cooked"
    (cooked / "Content" / "Props" / "Crate" / "Desktop").mkdir(parents=True)
    (cooked / "Content" / "Props" / "Crate" / "Desktop" / "SM.uasset").write_bytes(b"x")
    result = run_script(
        sandbox, "verify-cook-manifest.sh", "--variant", "mobile", "--dry-run", str(cooked)
    )
    assert result.returncode == 0
    assert "DRY-RUN" in result.stdout
