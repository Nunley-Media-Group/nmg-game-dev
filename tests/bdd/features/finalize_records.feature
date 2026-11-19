# File: tests/bdd/features/finalize_records.feature
# Generated from: specs/247-keep-a-per-asset-finalize-record-and-logs-under-the-unreal-project-s-saved-directory-and-add-a-cheap-up-to-date-check/feature.gherkin
Feature: Per-asset finalize records and an up-to-date check

  @SCN001
  Scenario: A finished run writes a per-asset record
    Given a consumer project with game/project.godot and a finalize request for Props/Crate from Crate.blend
    When the finalize job succeeds
    Then ".nmg/finalize/Props/Crate.json" holds the state, times, version, full_run, steps with cache hits, source, imported res:// paths, content hash, logs, and a null error

  @SCN002
  Scenario: The run's logs are kept beside the record
    Given the same finished run
    When the job directory under the cache root is deleted
    Then ".nmg/finalize/Props/Crate.logs/" still holds job.log and each blender step log named in the record

  @SCN003
  Scenario: Each batch item gets its own record
    Given a fail-fast batch of Crate, Barrel, and Lamp where Barrel fails and Lamp has an earlier record
    When the batch runs
    Then Crate's record is written before Barrel starts
    And Barrel's record has state "failed"
    And Lamp's earlier record is unchanged

  @SCN004
  Scenario: A new run replaces the last record
    Given Props/Crate has a record and logs from an earlier run
    When Props/Crate is finalized again
    Then the record names the new job id and the logs directory holds only the new run's logs

  @SCN005
  Scenario: The CLI answers whether an asset is up to date
    Given Props/Crate has an up-to-date record
    When "python -m nmg_game_dev.finalize check --category Props --collection Crate --json" runs
    Then it prints up_to_date true with reason "up_to_date" and exits 0

  @SCN006
  Scenario: The MCP tool answers for a list of assets
    Given Props/Crate is up to date and Props/Barrel has no record
    When check_finalized is called with both assets
    Then Crate reports up_to_date true and Barrel reports reason "no_record" with a null record summary

  @SCN007
  Scenario: A clean full run newer than the source is up to date
    Given a succeeded full-run record whose .blend is older than its start and whose imported files and .import files exist
    When the check runs
    Then it reports up_to_date true

  @SCN008
  Scenario Outline: Every other case is not up to date, with a reason
    Given a record set up so that <case>
    When the check runs
    Then it reports up_to_date false with reason "<reason>"

    Examples:
      | case                                   | reason            |
      | no record exists                       | no_record         |
      | the record is not valid JSON           | record_unreadable |
      | the last run failed                    | last_run_failed   |
      | the last run was one step              | not_full_run      |
      | the run had no source .blend           | no_source_blend   |
      | the .blend was deleted                 | source_missing    |
      | the .blend changed after the run began | source_newer      |
      | the Mobile .glb.import is missing      | import_missing    |
      | no project.godot can be found          | project_missing   |

  @SCN009
  Scenario: The check is cheap and has no side effects
    Given another finalize job holds the cache lock
    When the check runs for Props/Crate
    Then it answers and the project and cache trees are unchanged

  @SCN010
  Scenario: Record writing never changes a run's result
    Given ".nmg/finalize" is a file, so no record can be written
    When the finalize job succeeds
    Then its state is "succeeded" and its result carries a "finalize.record_not_written" warning

  @SCN011
  Scenario: Batches can skip up-to-date assets
    Given a batch of Crate and Barrel with skip_up_to_date where only Crate is up to date
    When the batch runs
    Then Crate's item state is "up_to_date", no step ran for it, and its record is unchanged
    And Barrel runs every step

  @SCN012
  Scenario: The record and the check are documented
    Given docs/mcp/finalize.md and skills/finalize-asset/SKILL.md
    When a reader looks up finalize records
    Then they describe the record path and fields, the logs, check and check_finalized, the reasons, skip_up_to_date, and the modification-time caveat

  @SCN013
  Scenario: Onboarding ignores the records
    Given a consumer .gitignore without ".nmg/"
    When the gitignore_env onboarding step runs
    Then the .gitignore contains ".nmg/"
