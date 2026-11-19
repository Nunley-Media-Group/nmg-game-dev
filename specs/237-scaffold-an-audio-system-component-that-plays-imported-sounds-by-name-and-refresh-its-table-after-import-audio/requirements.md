# Requirements: Scaffold an Audio system component that plays imported sounds by name and refresh its table after import_audio

**Issue**: #237
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As a** developer building a game with nmg-game-dev
**I want** `design scaffold` to create a ready-to-use Audio component, and its sound table to stay current as `import_audio` adds sounds
**So that** gameplay can play sounds and music by name from day one

## Background

`import_audio` stores each sound under `SourceArt/Audio/<SFX|Music>/` and imports it into the Godot project as `game/assets/Audio/<Name>.wav` (`AudioStreamWAV`, sound effects) or `game/assets/Audio/<Name>.ogg` (`AudioStreamOggVorbis`, music). `design scaffold` turns a `system` entry into an empty component script, `game/systems/<Name>/<snake_name>.gd`. Nothing connects imported sounds to gameplay.

This adds a runtime `NmgAudio` component and `NmgAudioTable` resource to the Godot add-on, an opt-in `template: audio` scaffold, a region `music` field, and a table refresh that runs from a CLI, an MCP tool, and after every successful `import_audio`.

## Acceptance Criteria

### AC1: Scaffold creates an Audio component

**Given** a `system` design entry named Audio with `template: audio`
**When** `design scaffold` runs
**Then** `game/systems/Audio/audio.gd` exists, declares `class_name AudioComponent` and `extends NmgAudio`, and assigns `res://systems/Audio/audio_table.tres` to `table`
**And** `game/systems/Audio/audio_table.tres` exists as an `NmgAudioTable` resource
**And** `NmgAudio` defines `sfx`, `ui`, `music`, `stinger`, `region_music`, and `set_volumes`

### AC2: Existing systems are unchanged

**Given** a `system` entry without `template`, or a component script or table that already exists
**When** `design scaffold` runs
**Then** the entry without `template` gets today's plain `extends Node` component, and no existing file is overwritten

### AC3: Refresh fills the name table

**Given** `game/assets/Audio/PunchLight.wav` and `game/assets/Audio/ForestTheme.ogg`, and a region entry `Forest` with `music: ForestTheme`
**When** the refresh runs through `python -m nmg_game_dev.audio refresh` or the `refresh_audio_table` MCP tool
**Then** the Audio component's table maps `PunchLight` to `res://assets/Audio/PunchLight.wav`, `ForestTheme` to `res://assets/Audio/ForestTheme.ogg`, and theme `Forest` to `ForestTheme`
**And** running it again leaves the file byte-identical

### AC4: import_audio refreshes automatically

**Given** a project with an Audio component table
**When** `import_audio` imports a new sound successfully
**Then** that sound is in the table without a separate refresh call, and the result's `refreshed_tables` lists the table

### AC5: Calling a missing sound is safe

**Given** an `NmgAudio` whose table has no sound named `NotYetImported`
**When** gameplay calls `sfx("NotYetImported", Vector3(1, 0, 0))` twice
**Then** nothing plays, no error is raised, and exactly one warning naming `NotYetImported` is pushed

### AC6: Music behavior

**Given** `music("A")` is playing
**When** `music("A")` is called again
**Then** the playing player and its stream do not change
**When** `music("B")` is called
**Then** A fades out and stops while B fades in, and B starts again when it finishes
**When** `stinger("S")` is called
**Then** the music is lowered by `duck_db` while S plays and returns to its volume when S finishes

### AC7: Volumes persist

**Given** `set_volumes(0.8, 0.5, 1.0)` was called
**When** a new `NmgAudio` with the same settings path enters the tree
**Then** its master, music, and sfx volumes are 0.8, 0.5, and 1.0

### AC8: The flow and fields are documented

**Given** `docs/mcp/elevenlabs.md`, `docs/design-contract.md`, and `docs/mcp/finalize.md`
**When** a reader looks up the audio component
**Then** `elevenlabs.md` describes scaffold → import → refresh → gameplay `sfx`/`music` calls, `design-contract.md` documents the `template` and `music` fields and the audio scaffold files, and `finalize.md` lists `refresh_audio_table`

### AC9: Sync validates the new fields

**Given** a `system` entry with `template: lights`, or a region entry whose `music` is not a non-empty string
**When** `design sync` runs
**Then** it reports `design.invalid_field` for that field

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Add `addons/nmg_game_dev/audio/nmg_audio.gd` (`class_name NmgAudio extends Node`) with `sfx(name, position := Vector3.ZERO)`, `ui(name)`, `music(name)`, `stinger(name)`, `region_music()`, `set_volumes(master, music, sfx)`, and `@export var table: NmgAudioTable` | Must |
| FR2 | Add `addons/nmg_game_dev/audio/nmg_audio_table.gd` (`class_name NmgAudioTable extends Resource`) with `@export var sounds: Dictionary` (name → `res://` path) and `@export var themes: Dictionary` (scene name → theme name) | Must |
| FR3 | `sfx` plays non-positionally when `position` is `Vector3.ZERO`, otherwise through an `AudioStreamPlayer3D` at the position, with pitch scaled by a random factor in `1 ± pitch_jitter`. An unknown name plays nothing and pushes one warning per name | Must |
| FR4 | `music` does nothing for the playing track, otherwise crossfades over `crossfade_seconds` and replays the track on `finished`. `stinger` lowers the music by `duck_db` until the stinger finishes. `region_music` plays `themes[current scene root name]` when present | Must |
| FR5 | `set_volumes` applies and saves the three volumes in a `ConfigFile` at `settings_path` (default `user://nmg_audio.cfg`), section `volumes`. `_ready` loads them | Must |
| FR6 | System entries accept optional `template` (only `audio`); region entries accept optional `music` (non-empty string). Sync reports `design.invalid_field` otherwise | Must |
| FR7 | `design scaffold` with `template: audio` writes the `extends NmgAudio` script and `audio_table.tres` (sounds from `game/assets/Audio/`, themes from the backlog), each only when absent | Must |
| FR8 | `refresh_tables(root)` rewrites every `game/systems/*/audio_table.tres` whose header declares `script_class="NmgAudioTable"`, from a scan of `game/assets/Audio/*.wav` and `*.ogg` and the backlog's region `music` fields, deterministically. It is exposed as `python -m nmg_game_dev.audio refresh` and the finalize MCP tool `refresh_audio_table` | Must |
| FR9 | A successful `import_audio` calls `refresh_tables` and returns `refreshed_tables` | Must |
| FR10 | `docs/mcp/elevenlabs.md`, `docs/design-contract.md`, and `docs/mcp/finalize.md` document the flow, fields, files, and tool | Must |

## Out of Scope

- Generating audio
- Audio bus layout and effects beyond the three volume channels
- Removing table entries by hand-editing; refresh rebuilds the sounds from the files present

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #237 | 2026-11-18 | Initial feature spec |
