# Tasks: Add a generate-audio skill that enforces one-take, instrumental, brief-faithful ElevenLabs generation

**Issue**: #242
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/130-route-blender-asset-authoring-to-model-asset-automatically/

## Implementation Tasks

### T001: Add the generate-audio skill

**File(s)**: `skills/generate-audio/SKILL.md`
**Type**: Create
**Depends**: none
**Acceptance**:
- FR1: frontmatter has `name: generate-audio`, a one-line `description` naming ElevenLabs sound-effect, music, and speech generation as its trigger, `required_mcp: [elevenlabs, finalize]`, `required_env: []`, `unattended_safe: true`
- AC5: the flow names `creative_get_model_schema`, says to set the music model's instrumental option unless the user asked for vocals and supplied lyrics, and says to use only the user's lyrics when vocals are requested
- AC6: the flow names `creative_get_model_guide`, `docs/design/systems/audio.md` as the example design-doc entry, `generations_count: 1`, and `import_audio`, and forbids adding any genre, instrument, mood, or vocal element absent from the request and design doc
- `claude plugin validate .` passes (`plugin.validate`)

### T002: Add the ElevenLabs audio guard hook

**File(s)**: `hooks/generate_audio_guard.py`, `hooks/hooks.json`
**Type**: Create
**Depends**: none
**Acceptance**:
- FR2/AC1: `hooks/hooks.json` keeps the Blender entry unchanged and adds a second PreToolUse command entry with matcher `^mcp__.*[Ee]leven[Ll]abs.*__creative_(generate_in_flow|generate_speech)$`, running `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/generate_audio_guard.py"` with timeout 10
- AC2: audio calls whose `generations_count` is missing or not the integer 1 print the deny payload with the design's `DENY_REASON`
- AC1/AC3/FR3: the first allowed audio call for a session prints the `REMINDER` `additionalContext` with no permission decision; repeat calls print nothing
- AC4/FR4: invalid JSON, non-object input, a missing `tool_input` object, a state-dir error, or an unexpected exception each exit 0 with empty stdout
- AC7/FR7: `creative_generate_in_flow` with a non-audio `node_type` prints nothing and writes no marker
- Markers live under `NMG_GAME_DEV_HOOK_STATE_DIR/generate-audio-reminder` when that variable is set
- `claude plugin validate .` passes (`plugin.validate`)

### T003: Keep the model-asset hook tests correct with two PreToolUse entries

**File(s)**: `tests/unit/test_model_asset_reminder_hook.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- The matcher and command-hook assertions select the Blender entry by its `model_asset_reminder.py` command instead of unpacking a single PreToolUse entry
- A test asserts `hooks/hooks.json` has exactly two PreToolUse entries: the Blender one and the ElevenLabs one
- `uv run pytest tests/unit/test_model_asset_reminder_hook.py -q` passes

### T004: Document the generation rules

**File(s)**: `docs/mcp/elevenlabs.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- FR5: `docs/mcp/elevenlabs.md` has a section that points to `/generate-audio` and states the one-take (`generations_count: 1`, other values denied by the hook), instrumental-by-default, and brief-only prompt rules
- The flow's Generate step points to `/generate-audio`
- `CHANGELOG.md` `[Unreleased]` has a `### Added` bullet describing the skill and hook that ends with `(#242)`

### T005: Unit tests for the hook and the skill content

**File(s)**: `tests/unit/test_generate_audio_guard_hook.py`, `tests/unit/test_generate_audio_skill.py`
**Type**: Create
**Depends**: T001, T002
**Acceptance**:
- AC1: the matcher matches `mcp__elevenlabs__creative_generate_in_flow`, `mcp__elevenlabs__creative_generate_speech`, and `mcp__claude_ai_ElevenLabs__creative_generate_speech`, and does not match `mcp__elevenlabs__creative_generate_image`, `mcp__elevenlabs__creative_list_voices`, or `mcp__blender__execute_blender_code`
- AC2: parametrized deny cases over `sfx`, `music`, `tts` in-flow calls and `creative_generate_speech`, with `generations_count` missing, `0`, `2`, `"1"`, `1.5`, and `true`; each payload has `permissionDecision == "deny"` and a reason containing `generations_count: 1` and `/generate-audio`
- AC1/AC3: the first single-take call returns the reminder naming `/generate-audio` and `nmg-game-dev:generate-audio` with no `permissionDecision`; a repeat call returns ""; a second session gets the reminder
- AC4: invalid JSON, `""`, `[]`, `{}`, and `{"tool_input": "x"}` return "" and create no state dir; an unwritable state dir returns ""
- AC7: an `image` in-flow call with `generations_count: 4` returns "" and creates no marker
- AC5/AC6: the skill test asserts the frontmatter fields from FR1 and that the body contains `creative_get_model_schema`, `instrumental`, `lyrics`, `creative_get_model_guide`, `docs/design/systems/audio.md`, `generations_count: 1`, `import_audio`, and the no-genre/instrument/mood/vocal rule
- `uv run pytest tests/unit -q` passes; `repository.lint`, `repository.format`, and `repository.types` pass

### T006: BDD scenarios for every acceptance criterion

**File(s)**: `tests/bdd/features/generate_audio.feature`, `tests/bdd/test_generate_audio_bdd.py`
**Type**: Create
**Depends**: T001, T002
**Acceptance**:
- The feature file carries SCN001–SCN007 from `specs/242-add-a-generate-audio-skill-that-enforces-one-take-instrumental-brief-faithful-elevenlabs-generation/feature.gherkin`, one per AC1–AC7
- Hook scenarios run `hooks/generate_audio_guard.py` as a real subprocess (`sys.executable`) with `NMG_GAME_DEV_HOOK_STATE_DIR` under `tmp_path`, and assert exit code 0 and stdout
- Skill scenarios read `skills/generate-audio/SKILL.md`
- `uv run pytest tests/bdd/test_generate_audio_bdd.py -q` passes (`repository.tests`)

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #242 | 2026-11-18 | Initial feature tasks |
