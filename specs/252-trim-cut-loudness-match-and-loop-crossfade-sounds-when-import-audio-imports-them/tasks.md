# Tasks: Trim, cut, loudness-match, and loop-crossfade sounds when import_audio imports them

**Issue**: #252
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/249-replace-unreal-engine-with-godot-4-and-convert-existing-consumer-projects/

## Implementation Tasks

### T001: Add the numpy finishing module

**File(s)**: `src/nmg_game_dev/audio/finish.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- AC1: leading frames at or below −50 dBFS are dropped; an all-silent sound is untrimmed and reports `silent: true`.
- AC2: `max_seconds` keeps `round(max_seconds × rate)` frames and, without `loop`, applies a linear 20 ms fade to zero.
- AC4: with `loop`, the tail is crossfaded into the head over `min(loop_crossfade_ms, length/4)` so the seam step equals an existing adjacent step.
- AC3: `integrated_loudness` implements BS.1770-4 (K-weighting, 400 ms blocks with 75 % overlap, −70 LUFS absolute and −10 LU relative gates); gain reaches the target, or stops at a −1 dBFS peak and reports `loudness_capped`.
- AC5: `finish_wav` output is byte-identical for identical input and settings.

### T002: Store per-sound settings in audio.json

**File(s)**: `src/nmg_game_dev/audio/settings.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- FR3, AC5, AC7: `resolve` picks explicit values, then the stored entry, then the kind's defaults (−16 / −18 LUFS, 500 ms, finish true); `save` upserts the entry as sorted, indented JSON; invalid values raise `audio.invalid_request`; an unreadable file raises `audio.settings_invalid`.

### T003: Finish the game copy in import_audio and add refinish

**File(s)**: `src/nmg_game_dev/audio/core.py`, `src/nmg_game_dev/audio/godot_import.py`, `src/nmg_game_dev/audio/__main__.py`, `src/nmg_game_dev/audio/__init__.py`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- FR1, AC1–AC4: with finishing on, the finished WAV is what `import_wav` copies and what `import_ogg` encodes; the `SourceArt` WAV stays byte-identical to the input.
- AC5: a byte-identical re-import re-finishes with `replace=True` and yields a byte-identical game copy; a different source fails `audio.asset_exists`; `refinish --all` and `refinish <Name>` re-finish from SourceArt with stored settings; an unknown name fails `audio.unknown_sound`.
- AC6, FR4: SFX imports never resolve ffmpeg; music without ffmpeg fails `audio.ffmpeg_not_found` before any write.
- AC7: `finish: false` imports the stored WAV unchanged and stores `finish: false`.
- FR2: the `import` CLI accepts `--max-seconds`, `--loudness-lufs`, `--loop-crossfade-ms`, and `--no-finish`; the result has `finish` and `settings`.
- `convert/runner.py` callers keep the default `replace=False`, unchanged.

### T004: Expose the finishing settings on the finalize MCP tool

**File(s)**: `src/nmg_game_dev/finalize/mcp_tools.py`, `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- FR2: `import_audio` passes `max_seconds`, `loudness_lufs`, `loop_crossfade_ms`, and `finish` through; `tools.json` declares them as optional with the bounds in design.md.
- Evidence: `gate-mcp-schema` (`uv run python scripts/validate-mcp-tools.py`).

### T005: Unit tests for finishing, settings, import, refinish, CLI, and the MCP tool

**File(s)**: `tests/unit/audio/test_finish.py`, `tests/unit/audio/test_settings.py`, `tests/unit/audio/test_core.py`, `tests/unit/audio/test_cli.py`, `tests/unit/audio/conftest.py`, `tests/unit/test_finalize_mcp_tools.py`
**Type**: Create
**Depends**: T003, T004
**Acceptance**:
- AC3: a full-scale 1 kHz mono sine at 48 kHz measures −3.01 LUFS ± 0.1 with `integrated_loudness` (reference check), and imported sine fixtures at −30 and −6 LUFS land at −16 (SFX) and −18 (music) ± 1 LU; a capped case reports `loudness_capped` with peak ≤ −1 dBFS.
- AC1: a 400 ms silence + tone fixture starts within 10 ms of the tone; the SourceArt file equals the input bytes.
- AC2: a 4 s fixture with `max_seconds=1.5` is 1.5 s ± 10 ms and its last 20 ms fade to zero.
- AC4: a looping fixture's seam step is ≤ the largest internal adjacent step.
- AC5: two imports of identical bytes give identical game copies; `refinish --all` reproduces them; a different source fails `audio.asset_exists`; settings persist and are reused.
- AC6: music with ffmpeg resolution failing gives `audio.ffmpeg_not_found` and no game file; SFX succeeds with ffmpeg resolution forbidden.
- AC7: `finish=false` gives a byte copy of the stored WAV.
- Existing `audio.asset_exists` tests are kept for different-source cases.
- Evidence: `uv run pytest tests/unit -q` (`repository.tests`), `repository.lint`, `repository.format`, `repository.types`.

### T006: BDD scenarios for audio finishing

**File(s)**: `tests/bdd/features/audio_finishing.feature`, `tests/bdd/test_audio_finishing_bdd.py`
**Type**: Create
**Depends**: T005
**Acceptance**:
- SCN001–SCN007 bind AC1–AC7 using generated numpy fixtures, `FakeFfmpeg`, and `FakeGodotRunner` with `audio_probe`.
- Evidence: `uv run pytest tests/bdd -q` (`repository.tests`).

### T007: Document finishing

**File(s)**: `docs/mcp/elevenlabs.md`, `docs/mcp/finalize.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- FR6: `docs/mcp/elevenlabs.md` documents the four settings and their defaults, `audio.json`, re-import and `refinish`, the `finish` result block, and the `audio.unknown_sound` and `audio.settings_invalid` codes; `docs/mcp/finalize.md`'s `import_audio` section lists the new parameters.
- `CHANGELOG.md` `[Unreleased]` bullets for this issue each end with `(#252)`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #252 | 2026-11-18 | Initial feature tasks |
