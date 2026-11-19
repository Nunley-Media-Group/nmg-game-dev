# Tasks: Add launch options, a headless autoplay smoke run, and on-demand game screenshots for Godot games

**Issue**: #251
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/249-replace-unreal-engine-with-godot-4-and-convert-existing-consumer-projects/

## Implementation Tasks

### T001: Add the NmgLaunch autoload to the add-on

**File(s)**: `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/nmg_launch.gd`, `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/plugin.gd`, `tests/godot/fixture/project.godot`
**Type**: Create
**Depends**: none
**Acceptance**:
- FR1, AC1: `configure`, `get_option`, and `has_option` parse `--name=value` user arguments and the URL hash as in design.md; a bare flag reads `"true"`, an absent option returns the default, and the web hash is read through `JavaScriptBridge` only on the `web` feature.
- FR1, AC2: with `--nmg-autoplay`, `autoplay_requested` is emitted once after `current_scene` is set; `request_autoplay()` emits at most once.
- FR2, AC5: `--nmg-shot=<path>` with `--nmg-shot-after=<s>` saves the root viewport PNG and quits 0, or pushes an error and quits 1 when saving fails.
- AC7: `save_dir()` returns `user://nmg-test/` (folder created) with `--nmg-test-saves`, else `user://`.
- `plugin.gd` registers and removes `NmgLaunch`; the fixture project lists the `NmgLaunch` autoload. No per-frame hook is added.

### T002: Test NmgLaunch in the headless add-on runner

**File(s)**: `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/tests/test_nmg_launch.gd`, `scripts/run-godot-tests.sh`, `tests/unit/test_run_godot_tests.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- AC1: tests `test_cmdline_options`, `test_web_hash_options`, `test_flag_reads_true`, and `test_absent_option_returns_default` check the same values from `--hour=12 --at=Forest` and `#hour=12&at=Forest`.
- AC2: `test_autoplay_emits_once` connects to `autoplay_requested`, calls `request_autoplay()` twice, and counts one emission.
- AC7: `test_save_dir_with_test_saves` and `test_save_dir_default`.
- `scripts/run-godot-tests.sh` adds those test names to `required_tests`, and `tests/unit/test_run_godot_tests.py` is updated so its fake godot prints PASS lines for them.
- Evidence: `gate-godot-headless` (`scripts/run-godot-tests.sh`) passes; `gate-shellcheck` passes; `uv run pytest tests/unit/test_run_godot_tests.py -q`.

### T003: Add the smoke and shot commands to the Godot boundary

**File(s)**: `src/nmg_game_dev/godot/runner.py`, `src/nmg_game_dev/godot/smoke.py`, `src/nmg_game_dev/godot/shot.py`, `src/nmg_game_dev/godot/__main__.py`, `src/nmg_game_dev/godot/__init__.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- FR3, AC2: `python -m nmg_game_dev.godot smoke --frames 600` passes `--fixed-fps 60 --quit-after 600 -- --nmg-autoplay --nmg-test-saves` to the runner (which prepends `--headless --audio-driver Dummy --path <game>`), prints `smoke passed (600 frames)`, and exits 0.
- AC3: a `SCRIPT ERROR`, `Parse Error`, or `ERROR:` line or a non-zero exit gives exit 1 with `smoke.runtime_error`, at most the first 20 error lines, and a `Remediation:` line; exit 124 gives `smoke.timeout`.
- FR4, AC5: `shot <path> --after 3 -- <options>` runs with `headless=False`, passes the options plus `--nmg-test-saves --nmg-shot=<abs> --nmg-shot-after=3`, uses timeout `after + 60`, and prints `{"path","width","height"}` read from the PNG header.
- AC6: no PNG gives exit 1 with `shot.no_image` and the last 20 output lines; an unresolvable binary gives `godot.not_found`; a missing project gives `godot.project_missing`.
- `SubprocessGodotRunner(headless=False).argv()` omits `--headless`; the default argv is unchanged.

### T004: Add the game_screenshot finalize MCP tool

**File(s)**: `src/nmg_game_dev/finalize/mcp_tools.py`, `src/nmg_game_dev/finalize/__init__.py`, `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- FR4, AC5: `game_screenshot(path, after=3, options=None)` resolves `game/project.godot` under the consumer root, calls `take_shot`, and returns `{path, width, height}`.
- AC6: failures return `{"error": {code, message, remediation, stage}}` with `shot.no_image`, `godot.not_found`, or `shot.invalid_after` (after outside 0–60).
- Evidence: `gate-mcp-schema` (`uv run python scripts/validate-mcp-tools.py`) passes with the new tool in `tools.json`.

### T005: Gate /ship on the smoke run

**File(s)**: `src/nmg_game_dev/ship/runner.py`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- FR5, AC4: `run_ship` runs the smoke command after `res://tests/run_tests.gd` and before the mobile budget gate and every export; a smoke failure raises `ship.smoke_failed` and no `--export-release` runs; `--dry-run` prints `DRY-RUN: godot --headless --audio-driver Dummy --path <game> --fixed-fps 60 --quit-after 600 -- --nmg-autoplay --nmg-test-saves` into each `DRY-RUN.txt` and runs no Godot.
- Evidence: `gate-ship-smoke` (`scripts/ship-smoke.sh`) passes.

### T006: Register the NmgLaunch autoload during onboarding

**File(s)**: `src/nmg_game_dev/onboard/godot.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- FR8, AC8: a new `game/project.godot` holds `NmgLaunch="*res://addons/nmg_game_dev/nmg_launch.gd"`; an existing file without it gets the key reported as refreshed; a different value is reported as drift and left alone unless `refresh`.

### T007: Python unit tests for smoke, shot, the MCP tool, the ship gate, and onboarding

**File(s)**: `tests/unit/godot/test_smoke.py`, `tests/unit/godot/test_shot.py`, `tests/unit/godot/test_cli.py`, `tests/unit/godot/test_boundary.py`, `tests/unit/test_finalize_mcp_tools.py`, `tests/unit/ship/test_runner.py`, `tests/unit/onboard/test_runner.py`
**Type**: Create
**Depends**: T003, T004, T005, T006
**Acceptance**:
- AC2, AC3: `FakeGodotRunner` responses keyed `"--fixed-fps"` cover the clean run, each error-line kind, a non-zero exit, exit 124, and the 20-line cap.
- AC5, AC6: a fake response that writes a PNG gives the JSON with its width and height; no PNG gives `shot.no_image`; `forbid_godot` plus an empty env gives `godot.not_found`; `SubprocessGodotRunner(headless=False).argv` omits `--headless`.
- AC4: the ship runner records the smoke call between the tests call and the first export, a failing smoke raises `ship.smoke_failed` with no export call, and the dry run lists the smoke `DRY-RUN:` line; existing ship call-sequence assertions are updated for the new gate.
- AC8: onboarding writes, refreshes, and drift-reports the `NmgLaunch` key.
- Evidence: `uv run pytest tests/unit -q` (`repository.tests`), plus `repository.lint`, `repository.format`, and `repository.types`.

### T008: BDD scenarios for launch options, smoke, shot, ship, and onboarding

**File(s)**: `tests/bdd/features/game_runs.feature`, `tests/bdd/test_game_runs_bdd.py`
**Type**: Create
**Depends**: T002, T007
**Acceptance**:
- `game_runs.feature` holds SCN001–SCN008, one per AC1–AC8, bound in `test_game_runs_bdd.py` with `FakeGodotRunner`, `forbid_godot`, the ship sandbox from `tests/ship_fakes.py`, and the onboarding fakes; SCN001 and SCN007 run `scripts/run-godot-tests.sh` with a fake godot and assert it requires the `test_nmg_launch.gd` tests.
- Evidence: `uv run pytest tests/bdd -q` (`repository.tests`).

### T009: Document launch options, the smoke run, and screenshots

**File(s)**: `docs/onboarding/run-and-capture.md`, `docs/onboarding/index.md`, `docs/onboarding/first-ship.md`, `docs/skills/ship.md`, `skills/ship/SKILL.md`, `docs/mcp/finalize.md`, `skills/onboard-consumer/references/install-steps.md`, `CHANGELOG.md`, `tests/unit/onboard/test_docs_and_skill.py`
**Type**: Modify
**Depends**: T005
**Acceptance**:
- FR7: `docs/onboarding/run-and-capture.md` (linked from `index.md`) documents `NmgLaunch` options on desktop (`-- --name=value`) and web (`#name=value`), `autoplay_requested`, `save_dir()`, the smoke command, and the shot command and `game_screenshot` tool; the ship docs and skill list the smoke gate and `ship.smoke_failed` in their flow and failure codes; `docs/mcp/finalize.md` documents `game_screenshot`; the onboarding install steps list the `NmgLaunch` autoload.
- `CHANGELOG.md` `[Unreleased]` has bullets for this issue, each ending with `(#251)`.
- A docs test asserts these strings appear; evidence `uv run pytest tests/unit/onboard -q` and `plugin.validate` (`claude plugin validate .`) passes.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #251 | 2026-11-18 | Initial feature tasks |
