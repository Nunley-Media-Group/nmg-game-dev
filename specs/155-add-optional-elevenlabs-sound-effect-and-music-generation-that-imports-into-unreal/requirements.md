# Requirements: Import generated audio into Unreal (sound effects and music from the official ElevenLabs MCP)

**Issue**: #155
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As an** NMG game developer working in Claude Code
**I want** the agent to generate sound effects and music with the official ElevenLabs MCP server and bring the result into my project
**So that** a generated sound lands under `SourceArt/Audio/` and is imported into Unreal as a SoundWave I can use in the game

## Background

nmg-game-dev has no audio support beyond the `*.wav` Git LFS pattern in `src/nmg_game_dev/onboard/lfs.py`.

The official ElevenLabs MCP server already generates sound effects and music and saves them as local audio files, MP3 by default. The developer installs it and configures it with their own key. So nmg-game-dev adds no ElevenLabs client and no MCP server entry. It adds the missing half: an import that turns a saved audio file into project source art and an Unreal SoundWave.

Unreal imports run through `UnrealMcpClient` (`src/nmg_game_dev/pipeline/clients/unreal_mcp.py`). The UE Python they run prints one `NMG_RESULT {json}` line, which `src/nmg_game_dev/unreal/import_asset.parse_nmg_result` parses.

## Acceptance Criteria

### AC1: A WAV sound effect is stored and imported

**Given** a local file `/tmp/out/door.wav` saved from the official ElevenLabs MCP, a reachable Unreal MCP, and no existing `SourceArt/Audio/SFX/DoorCreak.wav`
**When** the agent calls `import_audio(file="/tmp/out/door.wav", name="DoorCreak", kind="sfx")`
**Then** the file is copied to `<project>/SourceArt/Audio/SFX/DoorCreak.wav`
**And** it is imported into Unreal as SoundWave `/Game/Audio/SFX/SW_DoorCreak` with looping off
**And** the result reports `source_art`, `unreal_asset`, `converted: false`, `looping: false`, and `imported_to_unreal: true`

### AC2: MP3, OGG, and FLAC input is converted to WAV

**Given** a local MP3, OGG Vorbis, or FLAC file
**When** it is imported with `kind="music"` and `name="ForestTheme"`
**Then** it is decoded and written as a 16-bit PCM WAV at `SourceArt/Audio/Music/ForestTheme.wav`, keeping its sample rate and channel count
**And** the WAV is imported as `/Game/Audio/Music/SW_ForestTheme`
**And** the result reports `converted: true` and the source format

### AC3: Looping on request

**Given** a valid audio file
**When** it is imported with `loop=true`
**Then** the imported SoundWave has `looping` enabled and the result reports `looping: true`
**And** when `loop` is omitted, `looping` stays off

### AC4: Unreal unreachable keeps the file

**Given** a valid audio file
**When** the Unreal MCP is unreachable at import time
**Then** the call succeeds with `imported_to_unreal: false`, the `source_art` path, and a `warning` with code `mcp.unreal.unreachable` and its remediation
**And** the WAV stays under `SourceArt/Audio/`

### AC5: Invalid requests are rejected before any file is written

**Given** any of these:
- a `name` that is not PascalCase (`^[A-Z][A-Za-z0-9]*$`), or that starts with `SFX_` or `MUS_`;
- a `kind` other than `sfx` or `music`;
- a `file` that does not exist;
- an extension other than `.wav`, `.mp3`, `.ogg`, or `.flac`;
- a target `SourceArt/Audio/<SFX|Music>/<Name>.wav` that already exists.

**When** `import_audio` is called
**Then** it returns `audio.invalid_request`, `audio.unsupported_format`, or `audio.asset_exists` with a remediation
**And** nothing is written and no Unreal call is made

### AC6: Undecodable audio fails cleanly

**Given** a file with a supported extension whose contents cannot be decoded
**When** it is imported
**Then** it returns `audio.decode_failed` with a remediation
**And** no partial file is left under `SourceArt/Audio/`, and no Unreal call is made

### AC7: One implementation through the CLI and an existing MCP server

**Given** the same inputs
**When** the developer runs `python -m nmg_game_dev.audio import --file F --name N --kind sfx|music [--loop]`, or the agent calls the `import_audio` tool on the existing `finalize` MCP server
**Then** both run the same function and return the same result JSON
**And** an error prints `ERROR [code] …` and exits 1 on the CLI, or returns `{"error": {code, message, remediation}}` from the tool

### AC8: No ElevenLabs integration ships with nmg-game-dev

**Given** the repository
**When** the unit guard tests run
**Then** the root `.mcp.json` has no `elevenlabs` entry and no `ELEVENLABS` text
**And** no nmg-game-dev module or MCP server calls the ElevenLabs API or reads an ElevenLabs key

### AC9: Docs teach the official-MCP-then-import flow

**Given** the repository docs
**When** a developer or agent reads them
**Then** `docs/mcp/elevenlabs.md` describes the flow:
1. generate a sound effect or music track with the official ElevenLabs MCP tools;
2. save the output to a local file;
3. call `import_audio` with a PascalCase name, the kind, and an optional loop flag.

**And** it lists the supported formats, the result fields, and the error codes
**And** it says the developer installs the official server at its latest version and configures its key
**And** the onboarding docs carry an optional-audio note pointing to it
**And** onboarding still prompts for no API key and installs no ElevenLabs server

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | A new package `nmg_game_dev.audio` provides `import_audio(file, name, kind, loop=False, *, project_root, unreal_client)`, which returns the result shape in AC1 | Must |
| FR2 | It validates the name, kind, file existence, extension, and target non-existence before any write | Must |
| FR3 | It copies WAV input as-is. It decodes MP3, OGG, and FLAC with `miniaudio` to a 16-bit PCM WAV at the source rate and channel count, writing to a temporary file and renaming it into place | Must |
| FR4 | It imports the WAV through the Unreal MCP as SoundWave `SW_<Name>` under `/Game/Audio/SFX/` or `/Game/Audio/Music/`, with `looping` set from `loop`. When the editor is unreachable, it keeps the file and warns `mcp.unreal.unreachable` | Must |
| FR5 | `python -m nmg_game_dev.audio import` and the `finalize` MCP tool `import_audio` (declared in `mcp-servers/finalize/tools.json`) share the implementation | Must |
| FR6 | `miniaudio` is a root project dependency declared as a floor, not an exact pin, and every affected `uv.lock` is regenerated | Must |
| FR7 | Guards keep any ElevenLabs entry and text out of `.mcp.json` | Must |
| FR8 | `docs/mcp/elevenlabs.md`, a `docs/mcp/finalize.md` entry for `import_audio`, and an onboarding note document the flow | Must |
| FR9 | Unit and BDD tests use a fake Unreal client, the fake `unreal` module, and small committed WAV, MP3, OGG, and FLAC fixtures | Must |

## Out of Scope

- Calling the ElevenLabs API, or shipping, configuring, or pinning any ElevenLabs MCP server
- Handling ElevenLabs API keys
- Text-to-speech, voice cloning, and dialogue
- SoundCue, MetaSound, attenuation, or sound-class authoring in Unreal
- Per-platform (Desktop/Mobile) audio variants or compression settings
- Overwriting an existing imported sound in place

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #155 | 2026-11-11 | Initial feature spec |
