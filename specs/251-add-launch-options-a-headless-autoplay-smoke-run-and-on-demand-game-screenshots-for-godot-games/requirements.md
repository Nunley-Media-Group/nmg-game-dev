# Requirements: Add launch options, a headless autoplay smoke run, and on-demand game screenshots for Godot games

**Issue**: #251
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/249-replace-unreal-engine-with-godot-4-and-convert-existing-consumer-projects/

## User Story

**As a** game developer building a Godot game with nmg-game-dev
**I want** one set of launch options that works on desktop and web, a headless autoplay run that fails on script errors, and a command that saves a screenshot of the running game
**So that** Claude can start the game at a chosen state, catch runtime errors before shipping, and review how finalized assets look in the engine

## Background

Unit tests and `--check-only` cannot catch a missing resource, a removed node, or a crash during play; only running the game does. `/model-asset` reviews renders from Blender, but nothing shows an asset under the game's own lighting and materials.

Since #249 the add-on `addons/nmg_game_dev` ships the `NmgAssets` autoload and `NmgMissionDefinition` with a headless test runner. `/ship` runs `--import`, `--check-only` on every `.gd`, and `game/tests/run_tests.gd` before export. The Godot boundary `src/nmg_game_dev/godot/` provides `resolve_godot` (`godot.not_found`) and the injectable `GodotRunner`. No launch-option parsing, autoplay hook, game smoke run, or game screenshot exists.

## Acceptance Criteria

### AC1: Launch options read the same on desktop and web

**Given** the add-on's `NmgLaunch` autoload
**When** the game starts with the user arguments `--hour=12 --at=Forest` on desktop, or with the URL hash `#hour=12&at=Forest` in a web export
**Then** `NmgLaunch.get_option("hour", "")` returns `"12"` and `NmgLaunch.get_option("at", "")` returns `"Forest"` in both cases, `has_option` reports both as present, a flag with no value (`--nmg-autoplay` or `#nmg-autoplay`) reads as `"true"`, and an absent option returns the given default

### AC2: The smoke run passes a clean game

**Given** a consumer Godot project whose main scene runs without errors
**When** `python -m nmg_game_dev.godot smoke --frames 600` runs
**Then** it runs Godot with `--headless --audio-driver Dummy --path <game> --fixed-fps 60 --quit-after 600 -- --nmg-autoplay --nmg-test-saves`, `NmgLaunch` emits `autoplay_requested` exactly once after the main scene loads, and the command prints `smoke passed (600 frames)` and exits 0

### AC3: The smoke run fails on runtime errors

**Given** a game run whose output contains a `SCRIPT ERROR`, `Parse Error`, or `ERROR:` line, or that exits non-zero, or that does not exit within its timeout
**When** the smoke run runs
**Then** it exits 1 with `smoke.runtime_error` (or `smoke.timeout` for the timeout), prints up to the first 20 error lines, and prints a `Remediation:` line

### AC4: `/ship` gates on the smoke run

**Given** `/ship <target>` for any target
**When** the pre-export gates run
**Then** the smoke run runs after the project tests and before the mobile budget gate and any export; a failure stops the ship with `ship.smoke_failed` and no export runs; `--dry-run` prints the smoke command with the `DRY-RUN:` prefix and runs no Godot

### AC5: A screenshot is saved on demand

**Given** a consumer Godot project
**When** `python -m nmg_game_dev.godot shot build/shots/forest.png --after 3 -- --at=Forest --hour=18` runs, or the finalize MCP tool `game_screenshot` is called with `path="build/shots/forest.png"`, `after=3`, and `options=["--at=Forest", "--hour=18"]`
**Then** Godot runs without `--headless` with those launch options plus `--nmg-test-saves`, `--nmg-shot=<absolute path>`, and `--nmg-shot-after=3`; `NmgLaunch` saves the root viewport as a PNG at that path after 3 seconds and quits; and the command prints (the tool returns) JSON with `path`, `width`, and `height` and exits 0

### AC6: A failed screenshot is reported

**Given** the game exits, or runs past `after` plus 60 seconds, without writing the PNG
**When** the shot command or the `game_screenshot` tool finishes
**Then** it fails with `shot.no_image` and the last 20 lines of the game's output (the CLI exits 1; the tool returns `{"error": {...}}`); a missing Godot binary gives `godot.not_found`

### AC7: Test runs use their own save folder

**Given** game code that saves through `NmgLaunch.save_dir()`
**When** the game runs with `--nmg-test-saves`
**Then** `save_dir()` returns `user://nmg-test/` and that folder exists, and without the flag it returns `user://`

### AC8: Onboarding registers the NmgLaunch autoload

**Given** a consumer `game/project.godot` that `/onboard-consumer` creates, or an existing one that has only the `NmgAssets` autoload
**When** onboarding runs
**Then** `[autoload]` holds `NmgLaunch="*res://addons/nmg_game_dev/nmg_launch.gd"`; on the existing file the key is added and reported as refreshed, and a different value is reported as drift

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Add an `NmgLaunch` autoload (`nmg_launch.gd`) to the add-on: it parses `OS.get_cmdline_user_args()` and, on web, `window.location.hash` through `JavaScriptBridge`, and exposes `get_option`, `has_option`, `save_dir`, and the `autoplay_requested` signal, emitted once after the main scene loads when `--nmg-autoplay` is set | Must |
| FR2 | `NmgLaunch` handles `--nmg-shot=<path>` and `--nmg-shot-after=<seconds>` by saving the root viewport image to the path and quitting | Must |
| FR3 | Add `python -m nmg_game_dev.godot smoke` with `--frames` (default 600), `--project`, and error-line detection | Must |
| FR4 | Add `python -m nmg_game_dev.godot shot` and the finalize-server MCP tool `game_screenshot` | Must |
| FR5 | `/ship` runs the smoke run as a gate before the mobile budget gate and export | Must |
| FR6 | Add-on tests cover option parsing, defaults, flags, the single autoplay emission, and `save_dir`; Python tests cover smoke, shot, the MCP tool, onboarding, and the ship gate with `FakeGodotRunner` | Must |
| FR7 | Document launch options, the smoke run, and screenshots in the onboarding, ship, and finalize MCP docs | Should |
| FR8 | `/onboard-consumer` writes and drift-checks the `NmgLaunch` autoload in `game/project.godot` | Must |

## Out of Scope

- Autoplay behavior itself; each game decides what its player does when `autoplay_requested` fires.
- Screenshots during `/ship`.
- Comparing screenshots against reference images.
- Running the real game in `gate-godot-headless`; the gate runs only the add-on tests.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #251 | 2026-11-18 | Initial feature spec |
