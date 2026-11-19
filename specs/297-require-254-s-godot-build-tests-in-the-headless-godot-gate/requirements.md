# Requirements: Require #254's Godot build tests in the headless Godot gate

**Issue**: #297
**Date**: 2026-11-19
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/254-version-each-game-build-in-ship-show-the-version-in-game-and-require-a-player-changelog-entry/

## User Story

**As a** maintainer of the nmg-game-dev Godot add-on
**I want** `gate-godot-headless` to require every `NmgBuild` and `NmgVersionLabel` test
**So that** deleting or renaming one of those tests fails the gate instead of passing silently

## Background

`scripts/run-godot-tests.sh` runs the add-on's `tests/run_tests.gd` and then fails with exit 5 (`add-on tests failed: no PASS line for <name>`) for each entry of its `required_tests` array that has no `PASS <file>::<test>` line. #254 added `test_nmg_build.gd` with six tests (`test_version_reads_the_project_setting`, `test_version_is_empty_without_a_setting`, `test_version_matches_the_running_project`, `test_version_label_shows_the_prefixed_version`, `test_version_label_is_empty_without_a_version`, `test_version_label_defaults_its_prefix_to_v`), none of which are in `required_tests`.

## Acceptance Criteria

### AC1: #254's Godot tests are required

**Given** `scripts/run-godot-tests.sh`
**When** its `required_tests` array is read
**Then** it lists `test_nmg_build.gd::<name>` for every `func test_*` in `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/tests/test_nmg_build.gd`

### AC2: A missing required test fails the gate

**Given** a Godot add-on test run whose output has a PASS line for every required test except one `test_nmg_build.gd` test
**When** `scripts/run-godot-tests.sh` runs
**Then** it exits 5 and stderr names the missing `test_nmg_build.gd::<name>`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `required_tests` in `scripts/run-godot-tests.sh` contains the six `test_nmg_build.gd` tests, and the script's header comment names the NmgBuild tests among the required ones | Must |
| FR2 | A repository test fails when a `func test_*` in `test_nmg_build.gd` is not listed in `required_tests` | Must |
| FR3 | The fake `godot` used by `tests/unit/test_run_godot_tests.py` prints PASS lines for the six build tests, and has a mode that omits one of them | Must |

## Out of Scope

- New or changed GDScript test behaviour
- Requiring the `test_nmg_variant_scene.gd` or `test_mission_definition.gd` tests

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #297 | 2026-11-19 | Initial feature spec |
