# Design: Add a generate-audio skill that enforces one-take, instrumental, brief-faithful ElevenLabs generation

**Issue**: #242
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/130-route-blender-asset-authoring-to-model-asset-automatically/

## Overview

Three additions. The skill `skills/generate-audio/SKILL.md` carries the generation rules. The stdlib hook `hooks/generate_audio_guard.py` enforces the one-take rule and points the agent to the skill once per session. `docs/mcp/elevenlabs.md` documents both. The hook follows `hooks/model_asset_reminder.py` closely: stdlib only, `main(stdin_text) -> str` for unit tests, a `__main__` wrapper that prints and always exits 0.

## Architecture

```text
hooks/hooks.json PreToolUse
├── matcher ^mcp__.*blender.*__execute_blender_code$  → model_asset_reminder.py   (unchanged)
└── matcher ^mcp__.*[Ee]leven[Ll]abs.*__creative_(generate_in_flow|generate_speech)$
                                                       → generate_audio_guard.py  (new)
```

`generate_audio_guard.main(stdin_text)`:

1. Parse JSON. If it isn't a dict, or `tool_input` isn't a dict, return "" (fail open).
2. Classify the call. If `tool_name` ends with `__creative_generate_speech`, it is audio. If it ends with `__creative_generate_in_flow`, it is audio only when `tool_input["node_type"]` is in `{"sfx", "music", "tts"}`. Anything else returns "".
3. Take rule: `count = tool_input.get("generations_count")`. The call is single-take only when `type(count) is int and count == 1`, so `True`, `1.0`, and `"1"` fail. Otherwise return the deny payload.
4. Reminder: require a non-empty string `session_id`, otherwise return "". Create the marker `state_dir() / sha256(session_id)` with `open("x")`. `FileExistsError` and other `OSError`/`ValueError` return "". On success, return the reminder payload.
5. The `__main__` block wraps everything in `try/except Exception` and always calls `sys.exit(0)`.

`state_dir()` returns `Path(os.environ[NMG_GAME_DEV_HOOK_STATE_DIR]) / "generate-audio-reminder"` when the variable is set, otherwise `Path(tempfile.gettempdir()) / "nmg-game-dev-hooks" / "generate-audio-reminder"`.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `hooks/generate_audio_guard.py` (stdin → stdout) | PreToolUse event JSON: `session_id`, `tool_name`, `tool_input` | Deny: `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": DENY_REASON}}` | Audio call with `generations_count` ≠ integer 1 |
| same | same | Reminder: `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": REMINDER}}` | First allowed audio call per session |
| same | same | empty stdout, exit 0 | Repeat session, non-audio call, unreadable input, or any error |
| `hooks/hooks.json` | — | Second `PreToolUse` entry: `{"matcher": "^mcp__.*[Ee]leven[Ll]abs.*__creative_(generate_in_flow\|generate_speech)$", "hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/generate_audio_guard.py\"", "timeout": 10}]}` | Existing Blender entry unchanged |
| `skills/generate-audio/SKILL.md` | — | Frontmatter `name`, one-line `description`, `required_mcp: [elevenlabs, finalize]`, `required_env: []`, `unattended_safe: true` | Skill picker entry `nmg-game-dev:generate-audio` |

`DENY_REASON`: "nmg-game-dev: game audio is generated one take at a time. Set generations_count: 1 on this call and follow the /generate-audio skill (nmg-game-dev:generate-audio)."

`REMINDER`: "nmg-game-dev: run ElevenLabs sound-effect, music, and speech generation through the /generate-audio skill (nmg-game-dev:generate-audio): one take (generations_count: 1), instrumental music unless the user asked for vocals and gave lyrics, and a prompt built only from the user's request and the design docs. Import the saved file with import_audio."

## Skill flow (SKILL.md body)

1. **Read the brief.** Read the user's request and the matching entry in the project's design docs (for example `docs/design/systems/audio.md`). That entry and the request are the only prompt sources.
2. **Read the model.** Call `creative_get_model_guide` for the model you will use, and `creative_get_model_schema` for its parameters.
3. **Write the prompt.** Build it only from the request and the design-doc entry, following the model guide's format. Add no genre, instrument, mood, or vocal element that neither source names.
4. **Music: instrumental by default.** Set the instrumental option that the music model's schema names, unless the user explicitly asked for vocals and supplied lyrics. When vocals are requested, use only the user's lyrics, unchanged.
5. **One take.** Pass `generations_count: 1` on every generation call. Never generate several takes to choose from. The hook denies any other value.
6. **Generate and wait.** Poll `creative_get_flow_run_status` until the run completes.
7. **Download and import.** Save the output locally and call `import_audio` with a PascalCase name, `kind` `sfx` or `music`, and `loop` when the brief asks for it.

It also has a failure-modes section ("call denied for generations_count → set it to 1 and retry once"; "no design-doc entry → use the request alone and add nothing") and a test-fixtures line that points at the unit and BDD tests.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Extend `model_asset_reminder.py` to also handle ElevenLabs | Rejected | Mixing a never-block reminder with a deny path in one script muddies #130's fail-open guarantee and its tests |
| Separate state-dir env var for the new hook | Rejected | Reusing `NMG_GAME_DEV_HOOK_STATE_DIR` with a `generate-audio-reminder` subdirectory keeps one override for tests and cannot collide with the model-asset markers |
| Treat a missing `generations_count` as allowed (MCP default) | Rejected | The MCP default is several takes. The issue requires the deny |
| Remind on image/video `creative_generate_in_flow` calls | Rejected | The skill covers audio only |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #242 | 2026-11-18 | Initial feature design |
