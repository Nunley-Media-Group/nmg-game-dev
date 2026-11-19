# Tasks: Scaffold an Audio system component that plays imported sounds by name and refresh its table after import_audio

**Issue**: #237
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Add NmgAudio and NmgAudioTable to the Godot add-on

**File(s)**: `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/audio/nmg_audio.gd`, `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/audio/nmg_audio_table.gd`
**Type**: Create
**Depends**: none
**Acceptance**:
- FR1/FR2: the classes, methods, and exports in design.md exist, statically typed, in Godot style
- FR3/AC5: unknown names play nothing and warn once per name
- FR4/AC6: music no-op, crossfade, loop-on-finished, and stinger ducking behave as designed; durations of 0 apply instantly
- FR5/AC7: volumes save to and load from `settings_path`
- `--check-only` passes on both scripts (`gate-godot-headless`)

### T002: Godot add-on tests for NmgAudio

**File(s)**: `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/tests/test_nmg_audio.gd`
**Type**: Create
**Depends**: T001
**Acceptance**:
- Tests build in-memory `AudioStreamWAV` resources, save them with `ResourceSaver` under `user://`, and map them in an `NmgAudioTable`, with `crossfade_seconds = 0` and a test `settings_path` under `user://`
- AC1: an `NmgAudio` has the six methods (`has_method`)
- AC5: two `sfx("NotYetImported", Vector3(1, 0, 0))` calls create no playing player and produce exactly one warning naming it
- AC6: a repeat `music("A")` keeps the same player and stream; `music("B")` leaves A's player stopped and B's playing; emitting B's `finished` makes it play again; `stinger("S")` lowers the music player's `volume_db` by `duck_db`, and emitting S's `finished` restores it
- AC7: after `set_volumes(0.8, 0.5, 1.0)`, a fresh `NmgAudio` with the same `settings_path` reads 0.8, 0.5, 1.0 in `_ready`
- `scripts/run-godot-tests.sh` passes (`gate-godot-headless`)

### T003: Write and refresh audio tables

**File(s)**: `src/nmg_game_dev/audio/tables.py`, `src/nmg_game_dev/audio/core.py`, `src/nmg_game_dev/audio/__main__.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- FR8/AC3: `render_table` and `refresh_tables` behave as in design.md; a second refresh leaves files byte-identical
- FR9/AC4: `import_audio` returns `refreshed_tables` and the new sound is in each table after a successful import
- `python -m nmg_game_dev.audio refresh` prints the JSON and exits 0, or exits 1 with `ERROR [audio.godot_project_missing]` when `game/project.godot` is missing

### T004: Validate and scaffold the audio template and region music

**File(s)**: `src/nmg_game_dev/design/parse.py`, `src/nmg_game_dev/design/scaffold.py`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- FR6/AC9: `template` other than `audio` on a system, or a `music` that is not a non-empty string on a region, gives `design.invalid_field` from sync
- FR7/AC1: `template: audio` scaffolds the script text in design.md and `audio_table.tres` from `render_table`
- AC2: systems without `template` render exactly as before, and existing script or table files are reported `unchanged` and not rewritten

### T005: Expose refresh_audio_table on the finalize MCP

**File(s)**: `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- AC3/FR8: `refresh_audio_table(project=None)` returns `{"refreshed_tables": [...]}` or the structured error
- `uv run python scripts/validate-mcp-tools.py` passes (`gate-mcp-schema`)

### T006: Document the audio component flow

**File(s)**: `docs/mcp/elevenlabs.md`, `docs/design-contract.md`, `docs/mcp/finalize.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T004, T005
**Acceptance**:
- AC8/FR10: `elevenlabs.md` has a section after the import flow describing scaffold → import → refresh → `sfx`/`music` calls and the six methods. `design-contract.md` §2 lists `template` and `music`, §8 lists the audio scaffold files, and §9 names the new `design.invalid_field` cases. `finalize.md` lists `refresh_audio_table` and the `refreshed_tables` result field
- `CHANGELOG.md` `[Unreleased]` has an `### Added` bullet describing the Audio component and table refresh that ends with `(#237)`

### T007: Python unit and BDD tests

**File(s)**: `tests/unit/audio/test_tables.py`, `tests/unit/audio/test_cli.py`, `tests/unit/audio/test_core.py`, `tests/unit/design/test_parse.py`, `tests/unit/design/test_scaffold.py`, `tests/unit/test_finalize_mcp.py`, `tests/bdd/features/audio_component.feature`, `tests/bdd/test_audio_component_bdd.py`
**Type**: Create
**Depends**: T003, T004, T005, T006
**Acceptance**:
- AC1/AC2 (scaffold), AC3 (refresh via CLI and MCP, byte-identical rerun), AC4 (`import_audio` with a fake Godot runner refreshes and reports the table), AC8 (docs contain the flow, fields, and tool), and AC9 (sync errors) are covered by unit tests
- `tests/bdd/features/audio_component.feature` carries SCN001–SCN009 from this spec's `feature.gherkin`. `tests/bdd/test_audio_component_bdd.py` binds SCN001–SCN004, SCN008, and SCN009 with file fixtures. SCN005–SCN007 are bound by asserting that `test_nmg_audio.gd` defines the matching test methods, whose execution `gate-godot-headless` proves
- `uv run pytest tests/unit tests/bdd -q` passes (`repository.tests`); `repository.lint`, `repository.format`, and `repository.types` pass

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #237 | 2026-11-18 | Initial feature tasks |
