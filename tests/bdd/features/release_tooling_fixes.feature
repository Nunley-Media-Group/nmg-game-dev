# Generated from: specs/95-fix-the-always-green-blender-gate-re-import-entry-lookup-notarization-secret-exposure-and-stale-lockfiles/feature.gherkin
# Issue #95. SCN002 and SCN003 (re-import entry lookup) run headless in tests/blender/test_reimport_entry.py.
Feature: Release and ship tooling report failures, find their entry scripts, keep secrets out of argv, and keep lockfiles in sync

  @SCN001 @regression
  Scenario: The Blender gate fails when a Blender test fails
    Given a Blender test suite with one failing test
    When scripts/run-blender-tests.sh runs against it
    Then it exits non-zero
    And it exits 0 against a suite whose tests all pass

  @SCN004 @regression
  Scenario: Notarization with a keychain profile keeps secrets out of argv
    Given NOTARIZATION_KEYCHAIN_PROFILE is set and the Apple ID and app-specific password are unset
    When scripts/notarize-macos.sh runs on a signed app
    Then notarytool is called with --keychain-profile and the profile name
    And notarytool is called without --apple-id or --password

  @SCN005 @regression
  Scenario: The password path still submits and warns
    Given NOTARIZATION_KEYCHAIN_PROFILE is unset and the Apple ID, app-specific password and team ID are set
    When scripts/notarize-macos.sh runs on a signed app
    Then notarytool is called with the Apple ID, password and team ID as before
    And the password does not appear in the output
    And a warning says the password is visible in process arguments and names NOTARIZATION_KEYCHAIN_PROFILE

  @SCN006 @regression
  Scenario: A version bump leaves every lockfile in sync
    Given copies of the root and both MCP sub-projects with their committed lockfiles
    When VERSION changes to a new semver value
    Then uv lock --check passes in the root and in both MCP sub-projects
    And the installed nmg-game-dev package reports the new version

  @SCN007 @regression
  Scenario: Lock drift is reported with the project name
    Given a project whose pyproject.toml no longer matches its lockfile
    When the lockfile check runs
    Then it fails and names that project as needing uv lock

  @SCN008 @regression
  Scenario: Existing ship and MCP server behavior is preserved
    Given the committed finalize and texture-gen MCP sub-projects
    When each server module is resolved through uv run --project as a consumer launches it
    Then both import successfully
    And notarize-macos.sh --dry-run submits nothing
