# Design: Import generated audio into Unreal (sound effects and music from the official ElevenLabs MCP)

**Issue**: #155
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Overview

Generation stays entirely in the official ElevenLabs MCP server, which the developer installs. nmg-game-dev adds one synchronous function, `nmg_game_dev.audio.import_audio`. It validates the request, stores a WAV under `SourceArt/Audio/<SFX|Music>/`, and imports it through the Unreal MCP as a SoundWave.

The function is exposed as a CLI and as one more tool on the existing `finalize` MCP server, so `.mcp.json` does not change. A short local copy plus one UE import fits easily inside a single MCP call, so there is no background job.

## Architecture

### Package `src/nmg_game_dev/audio/`

- `errors.py`: `AudioError(PipelineError)` with `stage="audio"` and these codes:
  - `audio.invalid_request`
  - `audio.unsupported_format`
  - `audio.asset_exists`
  - `audio.decode_failed`
  - `audio.import_failed`
- `request.py`:
  - `KINDS = {"sfx": "SFX", "music": "Music"}`.
  - `NAME_RE = ^[A-Z][A-Za-z0-9]*$`.
  - `RESERVED_PREFIXES = ("SFX_", "MUS_")`. `NAME_RE` already rejects `_`, so the prefixes are checked explicitly only to give a clearer error message.
  - `FORMATS = {".wav", ".mp3", ".ogg", ".flac"}`.
  - `AudioRequest(file, name, kind, loop)` is a frozen dataclass. `validate()` raises the AC5 codes.
- `paths.py`:
  - `source_art(root, kind, name)` returns `<root>/SourceArt/Audio/<SFX|Music>/<Name>.wav`.
  - `unreal_asset(kind, name)` returns `/Game/Audio/<SFX|Music>/SW_<Name>`.
  - The project root is `CLAUDE_PROJECT_DIR`, else the current directory, using the existing `nmg_game_dev.meshy.config.project_root`.
- `convert.py`: `store_wav(src, dest)` returns `{"converted": bool, "source_format": str, "sample_rate": int, "channels": int, "duration_seconds": float}`.
  - A `.wav` input is checked with stdlib `wave.open` and copied.
  - Other formats are decoded with `miniaudio.decode_file(path, output_format=miniaudio.SampleFormat.SIGNED16)`, keeping the source rate and channels, and written with stdlib `wave`.
  - Writes go to `dest.with_suffix(".wav.tmp")`, then `os.replace` moves the file into place.
  - A `miniaudio.DecodeError`, `wave.Error`, or `EOFError` removes the temporary file and raises `audio.decode_failed`.
- `unreal_import.py`:
  - `build_audio_import_code(wav, dest_folder, asset_name, loop) -> str` produces UE Python that does the following:
    - runs `unreal.AssetImportTask(filename, destination_path, destination_name, automated=True, replace_existing=False, save=True)` through `unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])`;
    - loads the asset and requires `isinstance(asset, unreal.SoundWave)`;
    - calls `set_editor_property("looping", loop)` and saves with `EditorAssetLibrary.save_loaded_asset`;
    - always prints one `NMG_RESULT {"ok", "asset", "looping", "error"}` line.
  - `run_import(client, …)` parses that line with `parse_nmg_result`. When `ok` is false, it raises `audio.import_failed`.
- `core.py`: `import_audio(file, name, kind, loop=False, *, project_root=None, unreal_client=None) -> dict`.
  1. Validate the request.
  2. Store the WAV.
  3. Run the Unreal import, creating `UnrealMcpClient()` only if no client was passed in. A `PipelineError` whose code is `mcp.unreal.unreachable` becomes `imported_to_unreal: false` plus a `warning`.
  4. Return `{"kind", "name", "source_art", "unreal_asset", "converted", "source_format", "sample_rate", "channels", "duration_seconds", "looping", "imported_to_unreal", "warning"?}`.

  An `audio.import_failed` error leaves the stored WAV in place and propagates.
- `__main__.py`: `python -m nmg_game_dev.audio import --file F --name N --kind {sfx,music} [--loop] [--project DIR] [--url URL]`.
  - On success it prints the result JSON and exits 0.
  - On an error it prints `ERROR [code] message` and a remediation line, then exits 1.
  - On an argument error it exits 2.

### MCP tool on the existing finalize server

- `src/nmg_game_dev/finalize/mcp_tools.py` gains `import_audio(file, name, kind, loop=False) -> dict`. It returns the result, or `{"error": error_dict(e)}`.
- `mcp-servers/finalize/src/finalize_mcp/server.py` registers `@mcp.tool(name="import_audio")`. `mcp-servers/finalize/tools.json` declares it, so `gate-mcp-schema` covers it.

### Dependency

- The root `pyproject.toml` `[project] dependencies` gain `miniaudio>=1.59`. It is a floor because third-party packages track latest.
- `uv.lock` and the finalize server's `mcp-servers/finalize/uv.lock` (which depends on the root package) are regenerated. `tests/unit/test_lockfiles.py` keeps them in sync.

### Guards, steering, docs

- `tests/unit/test_scaffold_guards.py` gains a test asserting that `.mcp.json` has no `elevenlabs` key and no `ELEVENLABS` text, and that the existing entries are unchanged.
- `steering/snippets/project-product.md`: the Won't Have line still says the framework ships no paid generation service other than the optional Meshy source. It adds that developers may run the official ElevenLabs MCP themselves, and that nmg-game-dev imports its saved audio.
- `docs/mcp/elevenlabs.md` (new) describes the flow:
  1. use the official server's sound-effect and music tools, saving the output into a local folder;
  2. call `import_audio(file, name, kind, loop)`.

  It also lists the supported formats, the result fields, the error codes, and the unreachable-Unreal behavior.
- `docs/mcp/finalize.md` gains an `import_audio` section.
- `docs/onboarding/index.md` and `docs/onboarding/first-asset.md` gain an "Optional: generated audio" note.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Official ElevenLabs MCP, plus an nmg import | Selected (user) | No key handling or API client to maintain. The official server tracks latest |
| A custom ElevenLabs REST client and an `elevenlabs`/`audio-gen` MCP server | Rejected (user) | It duplicates the official server. A root `.mcp.json` entry ships to every consumer and collides with `elevenlabs` |
| `miniaudio` decode | Selected (user) | Decodes in-process with no system tool, and can be tested on fixtures |
| `ffmpeg` on PATH | Rejected (user) | It would be a host prerequisite on every machine |
| Background job for import | Rejected | A short local copy plus one UE import call fits within one MCP call |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #155 | 2026-11-11 | Initial feature design |
