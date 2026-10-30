# Generated from: specs/6-ship-skills-per-platform-build-sign-notarize-package/requirements.md
# Spec: specs/6-ship-skills-per-platform-build-sign-notarize-package/feature.gherkin (Issue #6)
Feature: Ship an NMG game per platform

  @SCN001
  Scenario: Ship macOS packages, signs, notarizes, and releases the app
    Given a consumer project, a UE_ROOT with RunUAT.sh, and notarization variables set
    When "ship macos" runs
    Then RunUAT BuildCookRun is invoked with -platform=Mac and Shipping package flags
    And the .app is codesigned with the team's signing identity
    And the .app is submitted with notarytool for the team and stapled
    And the signed .app is in release/macos/ replacing any earlier .app
    And release/RELEASE-NOTES.md lists the .app with its SHA-256

  @SCN002
  Scenario: Dry-run ship reports the plan without building
    Given a consumer project with notarization variables set and no Unreal Engine installed
    When "ship macos --dry-run" runs
    Then no UAT, codesign, security, or xcrun process runs
    And each planned command is printed with a "DRY-RUN:" prefix including a notarization dry-run pass
    And release/macos/DRY-RUN.txt records the plan and the command exits 0

  @SCN003
  Scenario: Ship mobile produces an .ipa and an .aab
    Given iOS and Android signing variables are set and every Mobile variant is within budget
    When "ship mobile" runs
    Then UAT is invoked for IOS and for Android
    And an .ipa is in release/ios/ and an .aab is in release/android/
    And the mobile cook-manifest gate passed for both platforms
    And the Android keystore password does not appear in the output

  @SCN004
  Scenario: Cook-manifest gate blocks cross-variant leakage
    Given the iOS cooked content contains "Content/Props/Crate/Desktop/SM_Crate.uasset"
    When "ship ios" runs
    Then verify-cook-manifest.sh reports the Desktop path
    And the ship exits non-zero with a remediation
    And no artifact is in release/ios/

  @SCN005
  Scenario: Windows build runs on the remote host
    Given the Windows build host, user, SSH key, and remote project path are set
    When "ship windows" runs
    Then ssh invokes RunUAT.bat BuildCookRun with -platform=Win64 on the remote project
    And the remote cooked listing passes the desktop cook-manifest gate
    And a .exe is copied back into release/windows/

  @SCN006
  Scenario: Mobile budget gate blocks an over-budget asset before any build
    Given "Content/Props/Crate/Mobile/nmg-asset.json" reports a standard_prop with 4200 tris
    When "ship mobile" runs
    Then gate-mobile-budgets fails before any UAT invocation
    And no artifact is in release/ios/ or release/android/
    And the remediation names "Props/Crate", tris, 4200, budget 3000, and overage 1200

  @SCN007
  Scenario: A Mobile variant without a report fails the budget gate
    Given "Content/Props/Lamp/Mobile/" has no nmg-asset.json
    When gate-mobile-budgets runs
    Then it fails with code "ship.budget_report_missing" telling the developer to finalize "Props/Lamp"

  @SCN008
  Scenario: Consumer budget overrides apply
    Given nmg-budgets.json sets standard_prop tris to 5000
    And "Content/Props/Crate/Mobile/nmg-asset.json" reports a standard_prop with 4200 tris
    When gate-mobile-budgets runs
    Then the gate passes

  @SCN009
  Scenario: Missing prerequisites fail fast without leaking secrets
    Given NOTARIZATION_TEAM_ID is unset and the other notarization variables hold secret values
    When "ship macos" runs
    Then it exits 1 before any UAT invocation naming NOTARIZATION_TEAM_ID
    And no secret value appears in the output

  @SCN010
  Scenario: Ship smoke dry-run succeeds on the fixture project
    Given the repository checkout with no Unreal Engine install
    When scripts/ship-smoke.sh runs
    Then a dry-run "all" ship of fixtures/dogfood.uproject exits 0

  @SCN011
  Scenario: The ship skill is the single Claude Code entry point
    Given the plugin checkout
    When skills/ship/SKILL.md is parsed
    Then its frontmatter has name "ship", a description, required_mcp, required_env, and unattended_safe true
    And its flow invokes "python -m nmg_game_dev.ship"
