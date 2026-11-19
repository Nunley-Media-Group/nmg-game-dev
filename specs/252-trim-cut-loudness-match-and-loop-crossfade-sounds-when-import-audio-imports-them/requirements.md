# Requirements: Trim, cut, loudness-match, and loop-crossfade sounds when import_audio imports them

**Issue**: #252
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/249-replace-unreal-engine-with-godot-4-and-convert-existing-consumer-projects/

## User Story

**As a** game developer importing generated sound effects and music
**I want** `import_audio` to trim leading silence, cut to a length, match loudness, and crossfade loop seams
**So that** every sound starts on time, no effect is louder than the rest, and loops play without a click

## Background

Generated takes often start with silence, run longer than needed, and vary in loudness, and a loop whose end does not match its start clicks at the seam. `import_audio` stores the input as a WAV under `SourceArt/Audio/<SFX|Music>/` and copies it (sound effects) or encodes it to Ogg Vorbis with ffmpeg (music) into `game/assets/Audio/` without changing any samples. A name that already exists fails with `audio.asset_exists`.

Finishing changes only the game copy. The `SourceArt/Audio/` file stays the untouched source. Finishing runs in Python on the decoded samples, so sound effects need no ffmpeg; music still needs ffmpeg to encode Ogg Vorbis. For music, loudness and the loop seam are defined on the finished WAV that is handed to the Ogg encoder.

## Acceptance Criteria

### AC1: Leading silence is trimmed

**Given** a sound effect that starts with 400 ms below −50 dBFS
**When** `import_audio` imports it with default settings
**Then** the game copy starts within 10 ms of the first sample above −50 dBFS, and the `SourceArt/Audio/` copy is byte-identical to the input WAV

### AC2: A sound is cut to a maximum length

**Given** a 4-second take imported with `max_seconds: 1.5` and `loop: false`
**When** the import runs
**Then** the game copy is 1.5 s ± 10 ms long and its last 20 ms fade linearly to zero

### AC3: Loudness matches the target

**Given** sounds imported with default settings
**When** each import finishes
**Then** each SFX game copy measures −16 LUFS ± 1 LU and each music finished WAV measures −18 LUFS ± 1 LU of integrated loudness (ITU-R BS.1770), `loudness_lufs` overrides the target per sound, and when reaching the target would push the peak above −1 dBFS the gain stops at a −1 dBFS peak and the result reports `loudness_capped: true`

### AC4: Loops are crossfaded

**Given** a sound imported with `loop: true`
**When** the import runs
**Then** the finished audio's tail is crossfaded into its head over `loop_crossfade_ms` (default 500 ms, capped at one quarter of the length), so the step between its last and first sample is no larger than the largest step between adjacent samples inside the sound

### AC5: Finishing is repeatable

**Given** a sound imported once
**When** it is imported again with a byte-identical source and the same settings, or `python -m nmg_game_dev.audio refinish --all` (or `refinish <Name>`) runs
**Then** the game copy is byte-identical to the first import, the settings used are stored per sound in `SourceArt/Audio/audio.json` and reused when no setting is passed, and a different source under the same name still fails with `audio.asset_exists`

### AC6: Missing ffmpeg is reported

**Given** ffmpeg is not on PATH and `FFMPEG_BIN` is unset
**When** `import_audio` imports music
**Then** it fails with `audio.ffmpeg_not_found` and a remediation line and writes no game copy, while a sound-effect import finishes and imports without ffmpeg

### AC7: Finishing can be turned off per sound

**Given** a sound imported with `finish: false`
**When** the import runs
**Then** the game copy holds the source samples unchanged (the sound effect is a byte copy of the stored WAV; music is encoded from the stored WAV), and `finish: false` is stored in `audio.json`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Add a finishing stage to `import_audio` between storing the source and writing the game copy: trim leading silence, cut to `max_seconds` with a fade-out, crossfade the loop seam, then match loudness | Must |
| FR2 | Add `max_seconds`, `loudness_lufs`, `loop_crossfade_ms`, and `finish` to the `import` CLI and the finalize MCP `import_audio` tool, and report the finishing applied in the result | Must |
| FR3 | Persist per-sound settings in `SourceArt/Audio/audio.json`, reuse them when a setting is omitted, re-finish on a byte-identical re-import, and add `python -m nmg_game_dev.audio refinish [--all \| <Name>]` | Must |
| FR4 | Keep resolving ffmpeg from `FFMPEG_BIN`, then PATH, for music encoding, failing with `audio.ffmpeg_not_found` before any write; sound-effect finishing needs no ffmpeg | Must |
| FR5 | Tests cover each AC with generated sine and silence fixtures, a BS.1770 reference measurement, and the fake ffmpeg and Godot runners | Must |
| FR6 | Document finishing settings, `audio.json`, and `refinish` in `docs/mcp/elevenlabs.md` | Should |

## Out of Scope

- Generating audio or choosing between takes.
- Voice- or speech-specific processing.
- Finishing the stored WAVs that `/convert-to-godot` imports.
- A finalize MCP tool for `refinish`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #252 | 2026-11-18 | Initial feature spec |
