---
name: generate-audio
description: Use whenever you generate ElevenLabs sound effects, music, or speech for a game, even for casual requests like "make a door creak" or "I need a battle theme". It runs exactly one take through the ElevenLabs MCP, keeps music instrumental unless vocals with lyrics are requested, builds the prompt only from the request and the design docs, and imports the result with import_audio.
required_mcp: [elevenlabs, finalize]
required_env: []
unattended_safe: true
---

# Generate Audio

Generates one sound effect, music track, or speech clip through the official ElevenLabs MCP and
imports the saved file into the game with `import_audio`. Every ElevenLabs audio generation runs
through this skill. The `generate_audio_guard` PreToolUse hook denies any audio call whose
`generations_count` is not the integer 1, and it points the agent here once per session. The
consumer reference is `docs/mcp/elevenlabs.md`.

## Flow

Run these steps in order. Do not generate until steps 1 to 4 are settled.

1. **Read the brief.** Read the developer's request and the matching entry in the project's design
   docs, for example `docs/design/systems/audio.md`. The request and that entry are the only
   sources for the prompt.
2. **Read the model.** Call `creative_get_model_guide` for the model you will use, and
   `creative_get_model_schema` for its parameters. For speech, take the `voice_id` from
   `creative_list_voices` or from the request. Never invent one.
3. **Write the prompt.** Build it only from the request and the design-doc entry, in the format the
   model guide describes. Add no genre, instrument, mood, or vocal element that neither source
   names. A request for a creaking wooden door does not license a tempo, an orchestra, or a choir:
   the models fill every gap with their own defaults, and those defaults are what the developer did
   not ask for.
4. **Music: instrumental by default.** For a music track, set the instrumental option that
   `creative_get_model_schema` names, before generating. Music models sing unless told not to. Keep
   it set unless the developer explicitly asked for vocals and supplied lyrics. When vocals are
   requested, pass only the developer's lyrics, unchanged, and add no lyric of your own.
5. **One take.** Pass `generations_count: 1` on every audio generation call. Never generate several
   takes to choose from. The generation tools default to several takes per call, and the hook
   denies every other value.
6. **Generate and wait.** Call the generation tool, then poll `creative_get_flow_run_status` with
   the returned `flow_id` and session ids. Wait the `poll_after_seconds` the call returns between
   polls, until the run reports `all_completed` or `has_failures`.
7. **Download and import.** Save the output locally, then call `import_audio` with a PascalCase
   `name`, `kind` set to `sfx` for sound effects or `music` for music, and `loop: true` when the
   brief asks for a looping sound or track. `import_audio` has no speech kind, so import a speech
   clip as `sfx`. Report the returned `godot_asset` path.

## Failure modes and remediation

- The hook denies a call because `generations_count` is missing or is not 1: set
  `generations_count: 1` on that call and retry it once. If the retry is denied too, stop and
  report the denial text. Do not try other values.
- The design docs have no entry for the sound: use the request alone and add nothing beyond it.
  Say in the reply that no design-doc entry exists, so the developer can add one. Do not invent a
  design entry to fill the gap.
- `creative_get_flow_run_status` reports `has_failures`: report the failed run. Do not start
  another generation to retry it. Each generation spends the developer's credits, so a retry needs
  their go-ahead.
- `import_audio` returns `audio.invalid_request`: the name is not PascalCase, the kind is not `sfx`
  or `music`, or the file does not exist. Fix the input and call it again.
- `import_audio` returns the `godot.not_found` warning: the WAV is stored but Godot did not import
  it. Report the warning. Once Godot is installed, call `import_audio` again with the same file,
  name, and kind: the bytes match the stored WAV, so the call re-finishes the sound with its stored
  settings and imports it. A different file under that name stops at `audio.asset_exists`.

## Test fixtures

The contract tests are `tests/unit/test_generate_audio_skill.py`, which checks the frontmatter and
the Flow rules, and `tests/bdd/test_generate_audio_bdd.py`, which runs the hook and skill scenarios
in `tests/bdd/features/generate_audio.feature`. The hook is `hooks/generate_audio_guard.py`.
