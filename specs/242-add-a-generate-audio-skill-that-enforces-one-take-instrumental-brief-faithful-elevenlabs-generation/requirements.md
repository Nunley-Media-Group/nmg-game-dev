# Requirements: Add a generate-audio skill that enforces one-take, instrumental, brief-faithful ElevenLabs generation

**Issue**: #242
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/130-route-blender-asset-authoring-to-model-asset-automatically/

## User Story

**As a** game developer generating sound effects, music, and speech with the ElevenLabs MCP in an nmg-game-dev project
**I want** a `generate-audio` skill that every audio generation runs through, backed by a hook that enforces one take per call
**So that** each generation produces the audio the brief describes, once, ready for `import_audio`

## Background

`docs/mcp/elevenlabs.md` documents generate → save → `import_audio` through the official ElevenLabs MCP, but nothing steers the generation itself. The MCP's generation tools default to several takes per call. Music models produce vocals unless their instrumental option is set. An agent may also add styles to a prompt that the brief never asked for.

`hooks/hooks.json` registers one PreToolUse hook, `hooks/model_asset_reminder.py`, which reminds once per session to use `/model-asset` before `execute_blender_code`, never blocks, and fails open. This issue adds a second hook in the same style for ElevenLabs audio generation, plus the skill it points to.

ElevenLabs audio generation arrives as `creative_generate_speech` (speech) or `creative_generate_in_flow` with `node_type` `sfx`, `music`, or `tts`.

## Acceptance Criteria

### AC1: The hook routes ElevenLabs audio generation to the skill

**Given** nmg-game-dev's hooks are installed and no reminder has been shown in session "s-1"
**When** a PreToolUse event arrives for an ElevenLabs `creative_generate_speech` call, or a `creative_generate_in_flow` call with `node_type` `sfx`, `music`, or `tts`, with `generations_count: 1`
**Then** the hook exits 0 and prints `hookSpecificOutput` whose `additionalContext` names `/generate-audio` (`nmg-game-dev:generate-audio`) as the way to run the generation, with no permission decision
**And** the `hooks/hooks.json` matcher matches `mcp__elevenlabs__creative_generate_in_flow`, `mcp__elevenlabs__creative_generate_speech`, and `mcp__claude_ai_ElevenLabs__creative_generate_speech`, and does not match `mcp__elevenlabs__creative_generate_image` or `mcp__elevenlabs__creative_list_voices`

### AC2: Multi-take audio calls are denied

**Given** an ElevenLabs audio generation call (`creative_generate_speech`, or `creative_generate_in_flow` with `node_type` `sfx`, `music`, or `tts`)
**When** its `tool_input.generations_count` is missing, or is anything other than the integer 1 (for example `2`, `0`, `"1"`, or `true`)
**Then** the hook exits 0 and prints `hookSpecificOutput` with `permissionDecision: "deny"` and a `permissionDecisionReason` stating that game audio is generated one take at a time with `generations_count: 1` and naming `/generate-audio`

### AC3: Single-take audio calls pass

**Given** the same audio generation call with `generations_count: 1`
**When** the hook runs a second time for the same session
**Then** it exits 0 with empty stdout, allowing the call
**And** a call for a different session id gets the reminder once

### AC4: Unreadable input fails open

**Given** hook input that is not valid JSON, is not a JSON object, or has no `tool_input` object
**When** the hook runs
**Then** it exits 0 with empty stdout and does not block the call

### AC5: Music is instrumental unless the user asks for vocals with lyrics

**Given** `skills/generate-audio/SKILL.md`
**When** its flow is read for a music track
**Then** it directs reading the music model's schema with `creative_get_model_schema` and setting that model's instrumental option before generating, unless the user explicitly asked for vocals and supplied lyrics
**And** it directs using only the user's lyrics when vocals are requested

### AC6: Prompts come only from the brief

**Given** `skills/generate-audio/SKILL.md`
**When** its flow is read for any sound
**Then** it directs reading the model's prompt guide with `creative_get_model_guide`, building the prompt only from the user's request and the matching design-doc entry (for example `docs/design/systems/audio.md`), and adding no genre, instrument, mood, or vocal element absent from them
**And** it directs one take with `generations_count: 1`, downloading the result, and importing it with `import_audio`

### AC7: Other ElevenLabs generation is left alone

**Given** a `creative_generate_in_flow` call whose `node_type` is not `sfx`, `music`, or `tts` (for example `image`), with any `generations_count`
**When** the hook runs
**Then** it exits 0 with empty stdout and writes no reminder marker

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Add `skills/generate-audio/SKILL.md` with frontmatter `name: generate-audio`, a one-line description that names its trigger (any ElevenLabs sound-effect, music, or speech generation), `required_mcp: [elevenlabs, finalize]`, `required_env: []`, and `unattended_safe: true`. Its flow: read the request and design-doc entry, read the model guide and schema, set one take, set instrumental for music unless vocals with user lyrics are requested, generate, download, and import with `import_audio`. | Must |
| FR2 | Add `hooks/generate_audio_guard.py`, registered in `hooks/hooks.json` as a second PreToolUse command hook with matcher `^mcp__.*[Ee]leven[Ll]abs.*__creative_(generate_in_flow\|generate_speech)$`. It denies audio generation calls whose `generations_count` is not the integer 1. | Must |
| FR3 | On an allowed audio call, the hook adds a once-per-session `additionalContext` reminder naming `/generate-audio`. It reuses the exclusive-create marker approach of `hooks/model_asset_reminder.py`, with markers under `<NMG_GAME_DEV_HOOK_STATE_DIR or temp>/…/generate-audio-reminder`. | Must |
| FR4 | The hook fails open (exit 0, no output) on unreadable or unexpected input, on a state-directory error, and on any unexpected exception. | Must |
| FR5 | `docs/mcp/elevenlabs.md` documents the one-take, instrumental-by-default, and brief-only prompt rules, the hook's deny behavior, and points to `/generate-audio`. | Should |
| FR6 | Unit and BDD tests cover the matcher and the deny, allow, reminder-once, non-audio, and fail-open hook paths. A skill-content test asserts SKILL.md carries the one-take, instrumental, and prompt-sourcing rules. | Must |
| FR7 | `creative_generate_in_flow` calls with a non-audio `node_type` get no deny and no reminder. | Must |

## Out of Scope

- Generating audio or calling the ElevenLabs API from nmg-game-dev code; the official MCP still generates.
- Changes to `import_audio` behavior.
- Image, video, and 3D generation rules.
- Changes to the `/model-asset` reminder's behavior.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #242 | 2026-11-18 | Initial feature spec |
