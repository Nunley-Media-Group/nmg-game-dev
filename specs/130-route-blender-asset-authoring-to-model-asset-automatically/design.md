# Root Cause Analysis: Route Blender asset authoring to /model-asset automatically

**Issue**: #130
**Date**: 2026-11-01
**Status**: Approved
**Author**: Rich Nunley

## Root Cause

Nothing routes Blender asset work to `/model-asset`:

- The skill's `description` says what the skill does but names no trigger, so skill selection does not match "make a crate in Blender" or "fix the chair's legs".
- `block_text()` in `src/nmg_game_dev/onboard/instructions.py` points only at the asset and design contracts.
- The plugin ships no `hooks/` directory, so nothing intervenes when Claude calls `execute_blender_code`, and the Blender MCP's own instructions steer Claude to that tool directly.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `skills/model-asset/SKILL.md` | frontmatter `description` | Skill selection text without a trigger |
| `src/nmg_game_dev/onboard/instructions.py` | `block_text()` | Consumer agent instructions omit `/model-asset` |
| `hooks/` (absent) | plugin hooks | No in-session reminder at the tool call |

## Fix Strategy

1. **Description** — replace with: `Use whenever you create or change an asset's geometry or materials in Blender: models it freeform through the Blender MCP with a plan, blockout, spatial inspection, multi-view review, and fix loop`.
2. **Onboarding block** — add one paragraph inside the markers, after the asset-contract sentence:
   `Run \`/model-asset\` for any asset authoring or editing in Blender: creating or changing an asset's geometry or materials. Scene inspection and \`/finalize-asset\` runs do not need it.`
   `upsert_block` already replaces a differing block in place and reports `refreshed`; no logic change.
3. **Plugin hook** — new `hooks/hooks.json`:
   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "^mcp__.*blender.*__execute_blender_code$",
           "hooks": [
             { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/model_asset_reminder.py\"", "timeout": 10 }
           ]
         }
       ]
     }
   }
   ```
   and `hooks/model_asset_reminder.py` (stdlib only, `from __future__ import annotations`, typed):
   - `REMINDER` constant: "nmg-game-dev: to create or change an asset's geometry or materials in Blender, run the /model-asset skill (nmg-game-dev:model-asset) instead of authoring through execute_blender_code directly. Scene inspection and /finalize-asset runs are exempt; continue those as planned."
   - `state_dir()` → `Path(os.environ["NMG_GAME_DEV_HOOK_STATE_DIR"])` when set, else `Path(tempfile.gettempdir()) / "nmg-game-dev-hooks" / "model-asset-reminder"`.
   - `main(stdin_text: str) -> str`: parse JSON; take non-empty string `session_id` (else return `""`); marker = `state_dir() / sha256(session_id).hexdigest()`; `mkdir(parents=True, exist_ok=True)` then `marker.open("x")` — `FileExistsError` → `""`; success → `json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": REMINDER}})`.
   - `__main__`: wraps everything in `try/except Exception` → print nothing; prints the result only when non-empty; always exits 0.
   Exclusive create makes "once per session id" atomic across concurrent calls. Hashing the id keeps the marker name path-safe. No `permissionDecision` is emitted, so the normal permission flow is unchanged.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `skills/model-asset/SKILL.md` | New one-line description | AC1, FR1 |
| `src/nmg_game_dev/onboard/instructions.py` | Routing paragraph in `block_text()`; module docstring cites #130 | AC2, FR2 |
| `hooks/hooks.json` | New PreToolUse registration | AC3, FR3 |
| `hooks/model_asset_reminder.py` | New once-per-session, fail-open reminder | AC3, AC4, AC5, FR3, FR4 |
| `docs/skills/model-asset.md`, `docs/onboarding/index.md`, `CHANGELOG.md` | Describe the routing | FR5 |

## Blast Radius

- Every consumer `CLAUDE.md`/`AGENTS.md` block reports `refreshed` on the next `/onboard-consumer` run (expected drift report).
- The hook runs on every `execute_blender_code` call in any project with the plugin installed, including `/model-asset`'s own calls; after the first call per session it is a file-exists check. It never blocks, so `/finalize-asset` and inspection are unaffected beyond one advisory reminder.
- `plugin.validate` and `plugin.session-smoke` now cover the new `hooks/hooks.json`.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Python stdlib hook run with `python3` | Selected | Matches the repo's primary language; testable with pytest; a missing interpreter is a non-blocking hook error (exit ≠ 2) |
| Bash hook | Rejected | Parsing `session_id` from JSON without `jq` is fragile; `jq` is not a consumer prerequisite |
| Deny `execute_blender_code` outside `/model-asset` | Rejected | Issue Out of Scope; would break inspection and `/finalize-asset` |
| Remind on every call | Rejected | AC4 requires silence after the first reminder |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #130 | 2026-11-01 | Initial defect design |
