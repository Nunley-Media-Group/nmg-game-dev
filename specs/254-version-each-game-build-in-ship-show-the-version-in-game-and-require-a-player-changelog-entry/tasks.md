# Tasks: Version each game build in /ship, show the version in game, and require a player changelog entry

**Issue**: #254
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/249-replace-unreal-engine-with-godot-4-and-convert-existing-consumer-projects/

## Implementation Tasks

### T001: Resolve and write the build version

**File(s)**: `src/nmg_game_dev/ship/version.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- AC1, FR2: `resolve` handles `--bump` and `--version`; `write` sets `application/config/version` and every preset's version keys (Android `version/code` + 1, Windows `X.Y.Z.0`), and every other byte of both files is unchanged.
- AC2: `ship.version_invalid`, `ship.version_not_increased`, and `ship.version_missing` are raised before any write.

### T002: Find the changelog section

**File(s)**: `src/nmg_game_dev/ship/changelog.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- AC3, FR3: `## X.Y.Z` / `## [X.Y.Z]` headings with optional trailing text are found; the section text up to the next `## ` is returned; a missing file, missing section, or blank section raises `ship.changelog_missing`.

### T003: Wire versioning, the changelog gate, and gate results into /ship

**File(s)**: `src/nmg_game_dev/ship/runner.py`, `src/nmg_game_dev/ship/__main__.py`, `src/nmg_game_dev/ship/release_notes.py`, `skills/ship/SKILL.md`, `tests/godot/fixture/project.godot`, `tests/godot/CHANGELOG.md`, `tests/ship_fakes.py`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- FR1: the CLI accepts mutually exclusive `--bump` and `--version` and passes them to `run_ship`.
- AC2, AC3: the version and changelog checks run before any Godot command.
- AC1: version files are written after the gates and before the first export, and the exports see the new version; without a flag, nothing is written.
- AC4, FR4: `RELEASE-NOTES.md` carries the version heading, `## Changes`, `## Gates` with each gate's result (including the tests summary line), and the artifact table.
- AC6: a dry run prints and records the planned version and changelog lines and writes no project, preset, or changelog file.
- The fixture project has version `1.0.0` and `tests/godot/CHANGELOG.md` has a `## 1.0.0` entry. Evidence: `gate-ship-smoke` (`scripts/ship-smoke.sh`) and `plugin.validate` (`claude plugin validate .`).

### T004: Add NmgBuild and NmgVersionLabel to the add-on

**File(s)**: `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/nmg_build.gd`, `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/nmg_version_label.gd`, `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/tests/test_nmg_build.gd`
**Type**: Create
**Depends**: none
**Acceptance**:
- AC5, FR5: `NmgBuild.version()` returns `application/config/version`; an `NmgVersionLabel` shows `prefix + version` after `_ready` (tests set the setting to `1.3.0` and check `"1.3.0"` and `"v1.3.0"`, then restore it).
- Evidence: `gate-godot-headless` (`scripts/run-godot-tests.sh`).

### T005: Python tests for versioning, the changelog gate, release notes, and dry run

**File(s)**: `tests/unit/ship/test_version.py`, `tests/unit/ship/test_changelog.py`, `tests/unit/ship/test_runner.py`, `tests/unit/ship/test_release_notes.py`
**Type**: Create
**Depends**: T003
**Acceptance**:
- AC1: with `ShipSandbox`, `--bump minor` from `1.2.3` writes `1.3.0` everywhere, Android `version/code` goes from 4 to 5, the diff of both files touches only version lines, and the export saw the new presets; no flag leaves both files byte-identical.
- AC2: `--version 1.2.3` / `1.0.0` give `ship.version_not_increased`; `1.3` gives `ship.version_invalid`; an unversioned project gives `ship.version_missing`; none ran Godot or wrote a file.
- AC3: no `CHANGELOG.md`, no section, and a blank section each give `ship.changelog_missing` with no Godot call; `## [1.3.0] - 2026-11-18` is accepted.
- AC4: the release notes heading, Changes text, Gates lines (including `tests: 42 passed, 0 failed` from scripted test output), and artifact table.
- AC6: a dry run prints the `DRY-RUN:` version and changelog lines and leaves all three files byte-identical.
- Evidence: `uv run pytest tests/unit -q` (`repository.tests`), `repository.lint`, `repository.format`, `repository.types`.

### T006: BDD scenarios

**File(s)**: `tests/bdd/features/ship_versioning.feature`, `tests/bdd/test_ship_versioning_bdd.py`
**Type**: Create
**Depends**: T004, T005
**Acceptance**:
- SCN001–SCN006 bind AC1–AC6 with `ShipSandbox`; SCN005 runs `scripts/run-godot-tests.sh` with a fake godot (as `tests/unit/test_run_godot_tests.py` does) and asserts the add-on ships `nmg_build.gd`, `nmg_version_label.gd`, and `test_nmg_build.gd`.
- Evidence: `uv run pytest tests/bdd -q` (`repository.tests`).

### T007: Document the release flow

**File(s)**: `docs/skills/ship.md`, `docs/onboarding/first-ship.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- FR6: `docs/skills/ship.md` documents `--bump` / `--version`, the version keys per platform, the changelog section format, the new failure codes, the release notes layout, and `NmgBuild` / `NmgVersionLabel`; `docs/onboarding/first-ship.md` tells a new consumer to add `CHANGELOG.md` and pass `--version` on the first ship.
- `CHANGELOG.md` `[Unreleased]` bullets for this issue each end with `(#254)`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #254 | 2026-11-18 | Initial feature tasks |
