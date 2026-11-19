# Tasks: Remove the stale Unreal plugin comment and wrap long GDScript lines

**Issue**: #286
**Date**: 2026-11-19
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/251-add-launch-options-a-headless-autoplay-smoke-run-and-on-demand-game-screenshots-for-godot-games/

## Implementation Tasks

### T001: Rewrite the Blender test runner comment

**File(s)**: `tests/blender/_runner.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- FR1 / AC1: the file contains no `ue-plugin`; the comment explains the hyphenated directory by the current `plugins/` layout; no code changes

### T002: Flag `ue-plugin` in the retired-engine guard

**File(s)**: `tests/unit/test_no_unreal_references.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- FR2 / AC1: `INSENSITIVE` matches `ue-plugin` in any case; the docstring names it; the matcher test asserts `references_engine("nmg-game-dev-ue-plugin")`
- `uv run pytest tests/unit/test_no_unreal_references.py -q` passes

### T003: Wrap the over-long GDScript lines

**File(s)**: `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/nmg_launch.gd`, `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/tests/test_nmg_launch.gd`, `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/tests/test_nmg_variant_scene.gd`
**Type**: Modify
**Depends**: none
**Acceptance**:
- FR3 / AC2: every line in these files is 100 characters or fewer; the doc comment keeps its wording; the `preload` and `check_eq` calls keep their arguments
- `gate-godot-headless` (`scripts/run-godot-tests.sh`) passes

### T004: Guard the add-on's 100-column limit

**File(s)**: `tests/unit/test_godot_addon_line_length.py`
**Type**: Create
**Depends**: T003
**Acceptance**:
- FR4 / AC2: the test scans every `.gd` under `plugins/nmg-game-dev-godot-addon/`, fails with `path:line: length` for any line over 100 characters, and fails when no `.gd` file is found
- `uv run pytest tests/unit/test_godot_addon_line_length.py -q` passes

### T005: BDD scenarios for #286

**File(s)**: `tests/bdd/features/source_hygiene.feature`, `tests/bdd/test_source_hygiene_bdd.py`
**Type**: Create
**Depends**: T001, T002, T003
**Acceptance**:
- The feature file carries SCN001-SCN002 from this spec's `feature.gherkin`, with a header naming the spec and `# Issue: #286`
- SCN001 reads `tests/blender/_runner.py`, checks that it has no `ue-plugin` and that its comment names `plugins/`, and checks that `references_engine` flags `ue-plugin`; SCN002 measures every add-on `.gd` line
- `repository.tests`, `repository.lint`, `repository.format`, `repository.types`, and `gate-blender-headless` pass

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #286 | 2026-11-19 | Initial feature tasks |
