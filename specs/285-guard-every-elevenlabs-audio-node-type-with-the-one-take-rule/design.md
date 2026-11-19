# Design: Guard every ElevenLabs audio node type with the one-take rule

**Issue**: #285
**Date**: 2026-11-19
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/242-add-a-generate-audio-skill-that-enforces-one-take-instrumental-brief-faithful-elevenlabs-generation/

## Overview

Widen the guard's audio set to every in-flow node type that produces audio, record the MCP's node-type list as a fixture the tests derive the set from, and document the identifiers in the skill and the consumer doc. `_is_audio_call` already tests membership in `AUDIO_NODE_TYPES`, so the hook change is the tuple alone.

## Architecture

- `hooks/generate_audio_guard.py`: `AUDIO_NODE_TYPES` becomes
  `("tts", "sfx", "music", "dubbing-audio", "voice-changer", "voice-isolator", "audio-effects", "video-to-music", "composition")`.
  The module docstring and `_is_audio_call` docstring stop naming only sfx, music, tts.
- `tests/fixtures/elevenlabs/flow_node_types.json`: a trimmed snapshot of `creative_get_flow_node_types`, one object per node type with `type` and `output_modality`, plus a top-level `captured` date (2026-11-19) and `source` (`creative_get_flow_node_types`). Recorded types: `image-generation` (image), `video-generation` (video), `tts` (audio), `sfx` (audio), `music` (audio), `llm` (text), `composition` (video), `image-transform` (image), `avatar` (image), `dubbing-audio` (audio), `voice-changer` (audio), `voice-isolator` (audio), `voice-creation` (voice), `audio-effects` (audio), `video-to-music` (audio), `speech-to-text` (text), `random` (text), `dubbing-video` (video).
- Derivation rule, used by the tests: audio types = every fixture entry with `output_modality == "audio"`, plus `composition`, which outputs a mixed audio file when only audio sources are connected.
- `docs/mcp/elevenlabs.md`, `## Generation rules`: the one-take bullet names the guarded set and points to a new `### Guarded node types` table (columns `node_type`, `Produces`). Rows: `tts` speech, `sfx` sound effect, `music` music, `video-to-music` music scored to a video, `audio-effects` processed audio, `voice-changer` converted voice, `voice-isolator` isolated voice, `dubbing-audio` dubbed audio, `composition` mixed audio (or video when a video source is connected). A sentence after the table names the unguarded types, including `voice-creation` (outputs a voice, not audio) and `dubbing-video`.
- `skills/generate-audio/SKILL.md`: step 5 (**One take.**) names the guarded in-flow node types by identifier and says `generations_count: 1` applies to each; the intro paragraph says the hook covers `creative_generate_speech` and every audio node type of `creative_generate_in_flow`.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `generate_audio_guard.py` PreToolUse on `creative_generate_in_flow` | `node_type` in the new set, `generations_count` missing or not int 1 | deny payload with `DENY_REASON` | newly denies the five added types |
| same | `node_type` in the new set, `generations_count` 1 | once-per-session `additionalContext` reminder | unchanged rule, wider set |
| same | any other `node_type` | empty stdout, no marker | unchanged |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Hard-coded tuple checked against a recorded fixture | Selected | The hook stays stdlib-only and offline; the fixture ties the set to the MCP's own list |
| Query `creative_get_flow_node_types` from the hook at run time | Rejected | A PreToolUse hook has no MCP client and must answer within its 10 s timeout |
| Guard only types whose declared modality is `audio` | Rejected | `composition` produces audio-only mixes and spends credits per take |
| Guard `voice-creation` | Rejected | It outputs a designed voice, not an audio file; voice design runs through `creative_design_voice` |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #285 | 2026-11-19 | Initial feature design |
