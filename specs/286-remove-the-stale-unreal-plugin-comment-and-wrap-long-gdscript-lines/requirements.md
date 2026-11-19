# Requirements: Remove the stale Unreal plugin comment and wrap long GDScript lines

**Issue**: #286
**Date**: 2026-11-19
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/251-add-launch-options-a-headless-autoplay-smoke-run-and-on-demand-game-screenshots-for-godot-games/

## User Story

**As a** nmg-game-dev maintainer
**I want** the Blender test runner to stop naming the removed Unreal plugin and the Godot add-on's GDScript to fit 100 columns
**So that** the source describes the current layout and keeps the add-on's line-length style

## Background

`tests/blender/_runner.py` explains that the hyphenated add-on directory is kept "for layout consistency with nmg-game-dev-ue-plugin", a directory that no longer exists. `tests/unit/test_no_unreal_references.py` does not catch it, because none of its patterns match the lowercase `ue-plugin`.

The add-on's GDScript keeps a 100-column style. Four lines exceed it: `addons/nmg_game_dev/nmg_launch.gd:13` (158 characters), `addons/nmg_game_dev/tests/test_nmg_launch.gd:7` (102), and `addons/nmg_game_dev/tests/test_nmg_variant_scene.gd:46` and `:47` (105 and 102), all under `plugins/nmg-game-dev-godot-addon/`.

## Acceptance Criteria

### AC1: No Unreal plugin references remain in the Blender test runner

**Given** `tests/blender/_runner.py`
**When** it is searched for `ue-plugin`
**Then** nothing matches
**And** its comment explains the hyphenated directory by the current `plugins/` layout
**And** the retired-engine guard in `tests/unit/test_no_unreal_references.py` flags any tracked, non-exempt file that contains `ue-plugin`

### AC2: GDScript lines fit 100 columns

**Given** every `.gd` file under `plugins/nmg-game-dev-godot-addon/`
**When** line lengths are measured in characters, a tab counting as one
**Then** no line is longer than 100 characters
**And** the add-on's headless tests still pass

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | The comment above `_REPO_ROOT` in `tests/blender/_runner.py` no longer names `nmg-game-dev-ue-plugin` and states that the directory is hyphenated like the other `plugins/` directories, while the Blender module id must be snake_case | Must |
| FR2 | `references_engine` in `tests/unit/test_no_unreal_references.py` also matches `ue-plugin`, case-insensitively, and the matcher test covers it | Must |
| FR3 | The four over-long lines are rewrapped with no change in behavior: the `nmg_launch.gd` doc comment is reflowed, and the `preload` and `check_eq` calls are split inside their parentheses | Must |
| FR4 | A unit test fails when any `.gd` file under `plugins/nmg-game-dev-godot-addon/` has a line longer than 100 characters | Must |

## Out of Scope

- Behavior changes to the add-on, its tests, or the Blender test runner
- Line length of GDScript outside `plugins/nmg-game-dev-godot-addon/` (for example `src/nmg_game_dev/godot/gd/`)

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #286 | 2026-11-19 | Initial feature spec |
