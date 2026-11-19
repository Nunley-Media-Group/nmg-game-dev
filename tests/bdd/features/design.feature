# File: tests/bdd/features/design.feature
# Generated from: the #112 requirements (markdown design docs)
# Updated for: the #249 requirements (AC7, design scaffolding writes Godot files)
Feature: Markdown design docs drive finalization and Godot scaffolding

  @SCN001
  Scenario: Design docs parse into a sorted backlog
    Given a project whose docs/design holds a prop "Crate", a region "Old Town", and a mission "First Light"
    When design sync runs
    Then docs/design/backlog.json lists Crate, OldTown, and FirstLight sorted by type then asset name with status planned
    And one planned line is printed per entry

  @SCN002
  Scenario: Re-sync keeps progress and marks removed docs orphaned
    Given a backlog where Crate is finalized and OldTown is scaffolded
    When the Crate doc is edited, a system doc "Stamina" is added, and the First Light doc is deleted, and sync runs
    Then Crate stays finalized with its new fields, OldTown stays scaffolded, Stamina is planned, and FirstLight is orphaned
    And syncing again without changes writes a byte-identical backlog

  @SCN003
  Scenario: Invalid design docs are reported and the backlog is kept
    Given a doc with no frontmatter, a prop with no asset_class, and a mission whose region names no entry
    When design sync runs
    Then it reports design.frontmatter_missing, design.missing_field, and design.unknown_reference with each file and field
    And it exits 1 and the existing backlog is unchanged

  @SCN004
  Scenario: finalize_asset takes category and class from the backlog
    Given a backlog prop entry Crate with category Props and asset_class standard_prop
    When finalize_asset is called for collection Crate without category or asset_class and the job succeeds
    Then the request used Props and standard_prop
    And the Crate entry's status is finalized

  @SCN005
  Scenario: Regions, missions, and systems are scaffolded as Godot files
    Given planned entries OldTown (region), FirstLight (mission in OldTown), and Stamina (system)
    When design scaffold runs against the Godot project
    Then it creates game/levels/OldTown/OldTown.tscn, game/missions/FirstLight.tres, and game/systems/Stamina/stamina.gd
    And the three entries are scaffolded
    And a second scaffold leaves every file unchanged

  @SCN006
  Scenario: Existing scaffold targets are left alone
    Given game/levels/OldTown/OldTown.tscn already exists
    When design scaffold runs
    Then it prints unchanged for OldTown without modifying the level
    And the other entries still scaffold

  @SCN007
  Scenario: Onboarding installs the design contract
    Given a consumer project with a docs/design folder that already holds a file
    When onboard-consumer runs
    Then docs/nmg-game-dev/design-contract.md is installed and the existing docs/design file is untouched
    And the CLAUDE.md nmg-game-dev block links the design contract
