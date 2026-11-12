# Tasks: Import generated audio into Unreal (sound effects and music from the official ElevenLabs MCP)

**Issue**: #155
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: miniaudio dependency

**File(s)**: `pyproject.toml`, `uv.lock`, `mcp-servers/finalize/uv.lock`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `miniaudio>=1.59` (a floor, not `==`) is added to the root `[project] dependencies`. Both lockfiles are regenerated, and `tests/unit/test_lockfiles.py` passes (FR6).

### T002: Audio package core

**File(s)**: `src/nmg_game_dev/audio/__init__.py`, `src/nmg_game_dev/audio/errors.py`, `src/nmg_game_dev/audio/request.py`, `src/nmg_game_dev/audio/paths.py`, `src/nmg_game_dev/audio/convert.py`, `src/nmg_game_dev/audio/unreal_import.py`, `src/nmg_game_dev/audio/core.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- Validation rejects every AC5 case before any write (AC5, FR2).
- WAV input is copied. MP3, OGG, and FLAC are decoded to a 16-bit PCM WAV at the source rate and channel count. The write is atomic. Undecodable input fails with `audio.decode_failed` and leaves no file behind (AC1, AC2, AC6, FR3).
- The UE code imports `SW_<Name>` into the kind's folder, sets `looping`, saves, and prints one `NMG_RESULT` line (AC1, AC2, AC3, FR4).
- An unreachable editor returns `imported_to_unreal: false` with the `mcp.unreal.unreachable` warning, and the WAV is kept (AC4).
- `import_audio` returns the design's result shape (FR1).

### T003: CLI and finalize MCP tool

**File(s)**: `src/nmg_game_dev/audio/__main__.py`, `src/nmg_game_dev/finalize/mcp_tools.py`, `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- `python -m nmg_game_dev.audio import` and the `finalize` tool `import_audio` both call `import_audio` and return the same JSON. Errors behave as AC7 states (AC7, FR5).
- `.mcp.json` is unchanged, and `gate-mcp-schema` passes.

### T004: Guards, steering, and docs

**File(s)**: `tests/unit/test_scaffold_guards.py`, `steering/snippets/project-product.md`, `docs/mcp/elevenlabs.md`, `docs/mcp/finalize.md`, `docs/onboarding/index.md`, `docs/onboarding/first-asset.md`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- The guard asserts that `.mcp.json` has no `elevenlabs` entry and no `ELEVENLABS` text (AC8, FR7).
- The steering describes the official ElevenLabs MCP as something the developer runs, with nmg-game-dev importing its output.
- The docs cover the AC9 flow, the formats, the result fields, and the error codes. Onboarding still prompts for no key and installs no ElevenLabs server (AC9, FR8).

### T005: Tests

**File(s)**: `tests/fixtures/audio/tone.wav`, `tests/fixtures/audio/tone.mp3`, `tests/fixtures/audio/tone.ogg`, `tests/fixtures/audio/tone.flac`, `tests/fixtures/audio/corrupt.mp3`, `tests/fixtures/audio/README.md`, `tests/unit/audio/__init__.py`, `tests/unit/audio/test_request.py`, `tests/unit/audio/test_convert.py`, `tests/unit/audio/test_unreal_import.py`, `tests/unit/audio/test_core.py`, `tests/unit/audio/test_cli.py`, `tests/unit/test_finalize_mcp.py`, `tests/unit/fake_unreal.py`, `tests/bdd/features/audio_import.feature`, `tests/bdd/test_audio_import_bdd.py`
**Type**: Create
**Depends**: T002, T003, T004
**Acceptance**:
- The fixtures are short tones, each under 50 KB, and the README records how each was made.
- A fake `UnrealPythonClient` either runs the generated code against the fake `unreal` module or raises `mcp.unreal.unreachable`. No live editor and no ElevenLabs call are used (FR9).
- The tests cover:
  - AC1: the WAV is copied byte-for-byte, the asset path is right, `imported_to_unreal` is true, and `looping` is false.
  - AC2: each of MP3, OGG, and FLAC becomes a WAV that `wave` reads as 16-bit at the source rate and channel count, with `converted` true.
  - AC3: `looping` is true or false as requested.
  - AC4: an unreachable editor returns the warning, and the file is kept.
  - AC5: each invalid case writes nothing and makes no Unreal call.
  - AC6: a corrupt MP3 fails with `audio.decode_failed` and leaves no `.wav` or `.wav.tmp`.
  - AC7: the CLI and the MCP tool return the same JSON, the CLI exit codes are right, and the tool returns errors as `{"error": …}`.
  - AC8: the guard.
- BDD scenarios SCN001–SCN008 are bound to the same fakes and fixtures.
- Evidence:
  - `uv run pytest tests/unit tests/bdd -q` (`repository.tests`);
  - `repository.lint`, `repository.format`, and `repository.types`;
  - `gate-mcp-schema`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #155 | 2026-11-11 | Initial feature tasks |
