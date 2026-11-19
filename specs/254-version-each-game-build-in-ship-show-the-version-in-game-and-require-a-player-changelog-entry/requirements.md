# Requirements: Version each game build in /ship, show the version in game, and require a player changelog entry

**Issue**: #254
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/249-replace-unreal-engine-with-godot-4-and-convert-existing-consumer-projects/

## User Story

**As a** game developer shipping builds of a Godot game
**I want** `/ship` to set the build's version everywhere, the game to show that version, and the release notes to carry a player-facing changelog entry
**So that** anyone can tell which build is on screen and what changed in it

## Background

`/ship` runs its gates, exports each platform, and writes `release/RELEASE-NOTES.md` with each artifact's SHA-256. It does not read or set `application/config/version` or the export presets' version fields, does not read a consumer `CHANGELOG.md`, and the add-on exposes no version. The consumer root is the folder above `game/`; its `CHANGELOG.md` holds one `## X.Y.Z` section per release.

## Acceptance Criteria

### AC1: `/ship` sets the version

**Given** a consumer project whose `application/config/version` is `1.2.3`
**When** `/ship <target> --bump minor` (or `--version 1.3.0`) runs
**Then** `application/config/version` in `game/project.godot` becomes `1.3.0` and every preset's version fields in `game/export_presets.cfg` are set to match: macOS and iOS `application/short_version` and `application/version`, Android `version/name` with `version/code` incremented by one, and Windows `application/file_version` and `application/product_version` as `1.3.0.0`. Every other byte of both files is unchanged, and the files are written after the gates pass and before the first export. With neither flag, the current version is shipped and neither file is changed.

### AC2: The version must increase

**Given** `--version` names a version not greater than the current one, an invalid `X.Y.Z` value, or both flags together
**When** `/ship` runs
**Then** it stops with `ship.version_not_increased` (or `ship.version_invalid`) before running a gate or writing anything, and a project with no version shipped without either flag stops with `ship.version_missing`

### AC3: A changelog entry is required

**Given** the version to ship is `1.3.0`
**When** `/ship` runs its gates
**Then** it requires a section headed `## 1.3.0` (also accepted: `## [1.3.0]`, optionally followed by text such as a date) with at least one non-blank line before the next `## ` heading in the consumer's root `CHANGELOG.md`, and stops with `ship.changelog_missing` before any Godot command when there is none

### AC4: Release notes carry the version, changes, and gate results

**Given** a successful ship
**When** `release/RELEASE-NOTES.md` is written
**Then** it is headed `# Release notes — 1.3.0`, includes the changelog section text under `## Changes`, lists under `## Gates` each gate that ran with its result (for example `tests: 42 passed, 0 failed` from the project test runner's summary line), and keeps the artifact SHA-256 table

### AC5: The game shows its version

**Given** the add-on is installed
**When** game code calls `NmgBuild.version()` or adds an `NmgVersionLabel` node
**Then** it returns, or displays (with an exported `prefix`, default `"v"`), the `application/config/version` value of the running build

### AC6: Dry run changes nothing

**Given** `--dry-run`
**When** `/ship <target> --bump patch --dry-run` runs
**Then** it prints `DRY-RUN: version 1.2.3 -> 1.2.4` with each planned file change and `DRY-RUN: changelog ## 1.2.4 found in <path>`, records those lines in each `DRY-RUN.txt`, and leaves `project.godot`, `export_presets.cfg`, and `CHANGELOG.md` byte-identical

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Add `--bump major\|minor\|patch` and `--version X.Y.Z` to `/ship` and `python -m nmg_game_dev.ship` | Must |
| FR2 | Write the version to `project.godot` and every preset's version fields, incrementing the Android version code, changing only those keys | Must |
| FR3 | Gate on a matching `CHANGELOG.md` section | Must |
| FR4 | Extend `RELEASE-NOTES.md` with the version, the changelog text, and gate results | Must |
| FR5 | Add `NmgBuild.version()` and `NmgVersionLabel` to the add-on, with add-on tests | Must |
| FR6 | Document the release flow in `docs/skills/ship.md` and the ship skill | Should |

## Out of Scope

- Committing, tagging, or pushing in the consumer repository.
- Writing the changelog entry's text.
- Setting a version during `/onboard-consumer`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #254 | 2026-11-18 | Initial feature spec |
