# File: tests/bdd/features/convert_to_godot.feature
# Generated from: specs/249-replace-unreal-engine-with-godot-4-and-convert-existing-consumer-projects/requirements.md (AC11-AC13)
Feature: /convert-to-godot moves an Unreal consumer project to Godot

  @SCN011
  Scenario: Converting an Unreal consumer to Godot
    Given a clean Unreal consumer with finalized assets, SourceArt sources, WAVs, a scaffolded backlog, and an Unreal hook
    When /convert-to-godot runs
    Then every asset, audio file, and scaffolded entry is converted into game/
    And godot-conversion-report.md lists the converted and manual-port items
    And Content/, Source/, Config/, Plugins/, the .uproject, and the Unreal scripts are removed

  @SCN012
  Scenario: Partial conversion keeps Unreal and resumes
    Given a conversion in which one asset fails
    When /convert-to-godot finishes
    Then no Unreal file is deleted, the report lists the failure with its code and remediation, and the exit code is non-zero
    And a rerun converts only the failed asset

  @SCN013
  Scenario: Conversion guards and dry run
    Given a consumer with uncommitted changes
    When /convert-to-godot runs
    Then it stops with "convert.dirty_worktree" and writes nothing
    And on a clean consumer without a .uproject it stops with "convert.not_unreal"
    And with --dry-run on a valid consumer it prints every planned conversion and deletion and writes nothing
