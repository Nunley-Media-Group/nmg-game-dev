# Requirements: Guard every ElevenLabs audio node type with the one-take rule

**Issue**: #285
**Date**: 2026-11-19
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/242-add-a-generate-audio-skill-that-enforces-one-take-instrumental-brief-faithful-elevenlabs-generation/

## User Story

**As a** game developer generating audio with the ElevenLabs MCP through nmg-game-dev
**I want** the one-take guard and the `/generate-audio` reminder to cover every audio node type the in-flow generator offers
**So that** no audio generation runs several paid takes by default

## Background

`hooks/generate_audio_guard.py` denies an ElevenLabs `creative_generate_speech` call, or a `creative_generate_in_flow` call whose `node_type` is in `AUDIO_NODE_TYPES`, when `generations_count` is not the integer 1. An allowed audio call gets a once-per-session reminder naming `/generate-audio`. `AUDIO_NODE_TYPES` is `("sfx", "music", "tts")`.

The ElevenLabs MCP's `creative_get_flow_node_types` lists each node type with an `output_port.modality`. The types whose modality is `audio` are `tts`, `sfx`, `music`, `dubbing-audio`, `voice-changer`, `voice-isolator`, `audio-effects`, and `video-to-music`. `composition` declares `video` modality but outputs a mixed audio file when only audio sources are connected. Five of these audio types are not guarded today.

## Acceptance Criteria

### AC1: Every audio node type is guarded

**Given** a `creative_generate_in_flow` call whose `node_type` is any of `tts`, `sfx`, `music`, `dubbing-audio`, `voice-changer`, `voice-isolator`, `audio-effects`, `video-to-music`, or `composition`
**When** its `generations_count` is missing or is not the integer 1
**Then** the hook denies it with the same one-take reason that names `generations_count: 1` and `/generate-audio`
**And** the same call with `generations_count` 1 is allowed and gets the once-per-session reminder

### AC2: The set of audio node types comes from the MCP

**Given** the checked-in snapshot of the ElevenLabs MCP's `creative_get_flow_node_types` output at `tests/fixtures/elevenlabs/flow_node_types.json`
**When** the audio node types are derived from it as every type whose `output_port.modality` is `audio`, plus `composition`
**Then** that set equals the hook's `AUDIO_NODE_TYPES`
**And** `docs/mcp/elevenlabs.md` lists exactly those identifiers

### AC3: Non-audio node types are still left alone

**Given** a `creative_generate_in_flow` call whose `node_type` is `image-generation`, `video-generation`, `image-transform`, `dubbing-video`, `voice-creation`, `speech-to-text`, or `llm`
**When** the hook runs with any `generations_count`
**Then** it exits 0 with empty stdout and writes no reminder marker

### AC4: Skill and docs cover the new types

**Given** `skills/generate-audio/SKILL.md` and `docs/mcp/elevenlabs.md`
**When** they are read
**Then** each names every guarded audio node type identifier
**And** each states that every guarded audio generation runs with `generations_count: 1`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `AUDIO_NODE_TYPES` in `hooks/generate_audio_guard.py` contains exactly `tts`, `sfx`, `music`, `dubbing-audio`, `voice-changer`, `voice-isolator`, `audio-effects`, `video-to-music`, and `composition`; deny, reminder, and fail-open behavior is unchanged | Must |
| FR2 | `tests/fixtures/elevenlabs/flow_node_types.json` records each MCP node type's `type` and `output_port.modality`, and a test derives the audio set from it and compares it with `AUDIO_NODE_TYPES` | Must |
| FR3 | `docs/mcp/elevenlabs.md` documents the guarded node types in a table of exact identifiers, notes why `composition` is included, and names the unguarded types | Must |
| FR4 | `skills/generate-audio/SKILL.md` names every guarded node type in its one-take rule | Must |
| FR5 | Unit and BDD tests cover AC1-AC4 | Must |

## Out of Scope

- Image, video, and 3D generation rules
- Changes to `import_audio`
- Changing the hook's matcher in `hooks/hooks.json`, its deny or reminder text, or its marker storage
- Querying the ElevenLabs MCP at test time

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #285 | 2026-11-19 | Initial feature spec |
