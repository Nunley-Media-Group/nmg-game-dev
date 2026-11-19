# File: tests/bdd/features/ship_versioning.feature
# Generated from: specs/254-version-each-game-build-in-ship-show-the-version-in-game-and-require-a-player-changelog-entry/requirements.md
Feature: Versioned game builds with a player changelog

  @SCN001
  Scenario: /ship sets the version
    Given a consumer at version "1.2.3" whose Android preset has version/code 4 and a CHANGELOG.md with a "## 1.3.0" section
    When "/ship all --bump minor" runs
    Then game/project.godot has application/config/version "1.3.0"
    And the macOS and iOS presets have version "1.3.0", the Android preset has version/name "1.3.0" and version/code 5, and the Windows preset has "1.3.0.0"
    And no other line of either file changed

  @SCN002
  Scenario Outline: The version must increase
    Given a consumer at version "1.2.3"
    When /ship runs with <flags>
    Then it stops with "<code>" and no Godot command ran and no file changed

    Examples:
      | flags             | code                     |
      | --version 1.2.3   | ship.version_not_increased |
      | --version 1.0.0   | ship.version_not_increased |
      | --version 1.3     | ship.version_invalid     |

  @SCN003
  Scenario: A changelog entry is required
    Given a consumer at version "1.2.3" whose CHANGELOG.md has no "## 1.3.0" section
    When "/ship macos --version 1.3.0" runs
    Then it stops with "ship.changelog_missing" before any Godot command

  @SCN004
  Scenario: Release notes carry the version, changes, and gate results
    Given a consumer at version "1.2.3" with a "## 1.3.0" changelog section "Faster loading."
    And the project tests print "42 passed, 0 failed"
    When "/ship macos --version 1.3.0" succeeds
    Then release/RELEASE-NOTES.md is headed "# Release notes — 1.3.0"
    And it includes "Faster loading." under "## Changes"
    And it lists "tests: 42 passed, 0 failed" under "## Gates"
    And it keeps the artifact SHA-256 table

  @SCN005
  Scenario: The game shows its version
    Given the add-on with NmgBuild and NmgVersionLabel
    When the add-on tests run in headless Godot
    Then NmgBuild.version() returns the project version and an NmgVersionLabel shows "v" followed by it

  @SCN006
  Scenario: Dry run changes nothing
    Given a consumer at version "1.2.3" with a "## 1.2.4" changelog section
    When "/ship all --bump patch --dry-run" runs
    Then it prints "DRY-RUN: version 1.2.3 -> 1.2.4" and "DRY-RUN: changelog ## 1.2.4 found"
    And project.godot, export_presets.cfg, and CHANGELOG.md are byte-identical
