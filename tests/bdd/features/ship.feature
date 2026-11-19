# Generated from: specs/6-ship-skills-per-platform-build-sign-notarize-package/requirements.md
# Reworked for Godot by issue #249 (AC9, SCN009)
Feature: Ship an NMG Godot game per platform

  @SCN001
  Scenario: Ship macOS exports, signs, notarizes, and releases the app
    Given a consumer Godot project with notarization variables set and an earlier macOS build
    When "ship macos" runs
    Then Godot exports the "macOS" preset headless
    And the .app is codesigned with the team's signing identity
    And the .app is submitted with notarytool for the team and stapled
    And the signed .app is in release/macos/ replacing any earlier build
    And release/RELEASE-NOTES.md lists the .app with its SHA-256

  @SCN002
  Scenario: Dry-run ship reports the plan without exporting
    Given a consumer Godot project with notarization variables set
    When "ship macos --dry-run" runs
    Then no Godot, codesign, or xcrun process runs
    And each planned command is printed with a "DRY-RUN:" prefix including a notarization dry-run pass
    And release/macos/DRY-RUN.txt records the plan

  @SCN003
  Scenario: Ship exports every target through Godot
    Given a consumer Godot project with project tests and the environment for target "all"
    When "ship all" runs
    Then the script check, the project tests, and the mobile budget gate run before any export
    And release/ holds the macOS .app, the .ipa, the .aab, the .exe, and the web folder, each with SHA-256 in RELEASE-NOTES.md
    And no WINDOWS_BUILD_* variable was required
    And the Android keystore password does not appear in the output

  @SCN004
  Scenario: A script that does not parse stops the ship
    Given "scripts/player.gd" in the consumer project does not parse
    When "ship windows" runs
    Then the ship fails with code "ship.script_check_failed" naming "scripts/player.gd"
    And no preset is exported

  @SCN005
  Scenario: A large web pack warns
    Given the web export writes an index.pck of 40 MiB
    When "ship web" runs
    Then the output warns "WARNING [ship.web_pack_large]: index.pck is 40.0 MB, over 38 MB"
    And release/web/ is listed in RELEASE-NOTES.md

  @SCN006
  Scenario: Mobile budget gate blocks an over-budget asset before any export
    Given "assets/Props/Crate/Mobile/nmg-asset.json" reports a standard_prop with 4200 tris
    When "ship mobile" runs
    Then the mobile budget gate fails before any export
    And no artifact is in release/ios/ or release/android/
    And the remediation names "Props/Crate", tris, 4200, budget 3000, and overage 1200

  @SCN007
  Scenario: A Mobile variant without a report fails the budget gate
    Given "assets/Props/Lamp/Mobile/" has no nmg-asset.json
    When the mobile budget gate runs
    Then it fails with code "ship.budget_report_missing" telling the developer to finalize "Props/Lamp"

  @SCN008
  Scenario: Consumer budget overrides apply
    Given nmg-budgets.json sets standard_prop tris to 5000
    And "assets/Props/Crate/Mobile/nmg-asset.json" reports a standard_prop with 4200 tris
    When the mobile budget gate runs
    Then the gate passes

  @SCN009
  Scenario: Missing prerequisites fail fast without leaking secrets
    Given NOTARIZATION_TEAM_ID is unset and the other notarization variables hold secret values
    When "ship macos" runs
    Then it fails before any Godot command naming NOTARIZATION_TEAM_ID
    And no secret value appears in the output

  @SCN010
  Scenario: Ship smoke dry-run succeeds on the fixture project
    Given the repository checkout with no Godot install required
    When scripts/ship-smoke.sh runs
    Then a dry-run "all" ship of tests/godot/fixture/project.godot exits 0

  @SCN011
  Scenario: The ship skill is the single Claude Code entry point
    Given the plugin checkout
    When skills/ship/SKILL.md is parsed
    Then its frontmatter has name "ship", a description, required_mcp, required_env, and unattended_safe true
    And its flow invokes "python -m nmg_game_dev.ship"
