# Requirements: Match sound files case-insensitively, report duplicate sound names, and document refresh errors

**Issue**: #302
**Date**: 2026-11-19
**Status**: Approved
**Author**: Claude (nmg-sdlc write-spec)

---

## User Story

**As an** NMG game developer using the Audio component
**I want** the sound table refresh to find every sound file regardless of extension case, to stop
with a clear error when two files share a sound name, and the tool and skill docs to name every
refresh error
**So that** no sound is silently dropped or replaced and I know how to fix a failed refresh

---

## Background

`src/nmg_game_dev/audio/tables.py` builds the `NmgAudioTable` sound map keyed by file stem from
`game/assets/Audio/`. It accepts only lowercase `.wav`/`.ogg`, so `.WAV`/`.OGG` files are skipped,
and a `.wav` and an `.ogg` sharing a stem silently replace one another. The `refresh_audio_table`
MCP tool description lists only `audio.godot_project_missing`, though the refresh can also return
`audio.backlog_invalid`, `audio.table_unreadable`, and `audio.table_unwritable`. `import_audio`
returns `refresh_warning` when the table refresh fails, but `skills/generate-audio/SKILL.md` does
not say what to do with it.

---

## Acceptance Criteria

### AC1: Extensions are matched case-insensitively

**Given** `game/assets/Audio/Click.WAV`
**When** the sound table is refreshed
**Then** the table maps `Click` to `res://assets/Audio/Click.WAV`

### AC2: Duplicate stems are reported, not silently collapsed

**Given** `Theme.wav` and `Theme.ogg` both under `game/assets/Audio/` and an existing Audio name table
**When** the sound table is refreshed
**Then** the refresh fails with error code `audio.duplicate_sound` whose message names both `Theme.ogg` and `Theme.wav`
**And** the name table file is not rewritten
**And** the error's remediation says to keep one file per sound name by renaming or deleting the extra file, then refresh again
**And** `docs/mcp/finalize.md` documents `audio.duplicate_sound` and that resolution

### AC3: Tool descriptions list every error code

**Given** the `refresh_audio_table` tool description in `mcp-servers/finalize/tools.json`
**When** it is read
**Then** it names `audio.godot_project_missing`, `audio.backlog_invalid`, `audio.table_unreadable`, `audio.table_unwritable`, and `audio.duplicate_sound`

### AC4: The skill handles refresh_warning

**Given** `skills/generate-audio/SKILL.md`
**When** its import step is read
**Then** it says to report `refresh_warning` to the user with its remediation, and that the sound is still imported

---

## Functional Requirements

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR1 | `_sounds` accepts a file whose suffix lowercased is `.wav` or `.ogg`, keyed by its exact stem, with the `res://` path keeping the file's real name | Must | AC1 |
| FR2 | When two or more files under `game/assets/Audio/` share a stem, building the table raises `AudioError` code `audio.duplicate_sound` naming every such file, before any table is written | Must | AC2 |
| FR3 | `refresh_audio_table` returns `audio.duplicate_sound` as its `{"error": ...}` object, and `import_audio` reports it as `refresh_warning` while still importing the sound | Must | AC2 |
| FR4 | The `refresh_audio_table` description in `tools.json` names all five refresh error codes | Must | AC3 |
| FR5 | `docs/mcp/finalize.md` (refresh_audio_table and import_audio sections) and `docs/mcp/elevenlabs.md` document `audio.duplicate_sound` and its resolution | Must | AC2 |
| FR6 | `skills/generate-audio/SKILL.md` import step and failure modes say to report `refresh_warning` and its remediation, and that the sound is still imported | Must | AC4 |

---

## Non-Functional Requirements

| Aspect | Requirement |
|--------|-------------|
| Determinism | Table output stays a pure function of the files present and the backlog; a second refresh writes the same bytes |
| Errors | `audio.duplicate_sound` follows the AudioError contract (`code`, `message`, `remediation`, `stage: audio`) |

---

## Dependencies

### Internal Dependencies
- [x] #237 Audio component and sound-table refresh (`src/nmg_game_dev/audio/tables.py`)

---

## Out of Scope

- Changes to audio finishing
- Changing how `import_audio` names or stores files
- Treating stems that differ only in letter case (`theme.wav` and `Theme.ogg`) as duplicates

---

## Validation Checklist

- [x] User story follows "As a / I want / So that" format
- [x] All acceptance criteria use Given/When/Then format
- [x] No implementation details in requirements
- [x] All criteria are testable and unambiguous
- [x] Edge cases and error states are specified
- [x] Dependencies are identified
- [x] Out of scope is defined

---

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #302 | 2026-11-19 | Initial feature spec |
