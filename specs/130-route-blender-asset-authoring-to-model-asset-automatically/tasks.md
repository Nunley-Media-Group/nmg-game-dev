# Tasks: Route Blender asset authoring to /model-asset automatically

**Issue**: #130
**Date**: 2026-11-01
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: State the /model-asset trigger in the skill description

**File(s)**: `skills/model-asset/SKILL.md`
**Type**: Modify
**Depends**: none
**Acceptance**:
- AC1: frontmatter `description` is one line, says the skill is used whenever creating or changing an asset's geometry or materials in Blender, and contains `freeform` and `Blender MCP`
- `test_frontmatter_declares_the_ac1_contract` still passes

### T002: Route Blender asset work in the onboarding block

**File(s)**: `src/nmg_game_dev/onboard/instructions.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- AC2: `block_text()` contains a paragraph instructing the agent to run `/model-asset` for any asset authoring or editing in Blender and exempting scene inspection and `/finalize-asset`, inside the markers
- AC5: the asset-contract and design-contract links remain

### T003: Ship the once-per-session PreToolUse reminder hook

**File(s)**: `hooks/hooks.json`, `hooks/model_asset_reminder.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- AC3: `hooks/hooks.json` registers a `PreToolUse` command hook whose matcher matches `mcp__blender__execute_blender_code` and `mcp__plugin_nmg-game-dev_blender__execute_blender_code` and does not match other Blender MCP tools such as `mcp__blender__get_scene_info`; the first call for a session id prints `hookSpecificOutput` with `hookEventName: PreToolUse` and the routing `additionalContext`, with no `permissionDecision` or block decision, and exits 0
- AC4: a repeat call for the same session id exits 0 with empty stdout; a new session id gets the reminder
- AC5: invalid JSON, a missing or empty `session_id`, or an unwritable state directory each exit 0 with empty stdout
- The state directory honors `NMG_GAME_DEV_HOOK_STATE_DIR`
- `claude plugin validate .` passes (`plugin.validate`)

### T004: Document the routing

**File(s)**: `docs/skills/model-asset.md`, `docs/onboarding/index.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T001, T002, T003
**Acceptance**:
- FR5: `docs/skills/model-asset.md` has a section saying the skill runs for any request to create or change an asset's geometry or materials in Blender, that the onboarding block and a once-per-session plugin hook route to it, and that inspection and `/finalize-asset` are exempt
- `docs/onboarding/index.md` says the installed `CLAUDE.md` block routes Blender asset work to `/model-asset`
- `CHANGELOG.md` `[Unreleased]` has a `### Fixed` bullet describing the routing that ends with `(#130)`

### T005: Add regression coverage for the routing

**File(s)**: `tests/bdd/features/model_asset_routing.feature`, `tests/bdd/test_model_asset_routing_bdd.py`, `tests/unit/onboard/test_instructions.py`, `tests/unit/test_model_asset_reminder_hook.py`
**Type**: Create | Modify
**Depends**: T001, T002, T003
**Acceptance**:
- `tests/bdd/features/model_asset_routing.feature` carries SCN001–SCN005 from this spec's Gherkin, bound in `tests/bdd/test_model_asset_routing_bdd.py`
- SCN001 (AC1) reads the skill frontmatter; SCN002 (AC2) seeds `CLAUDE.md` with the 0.21.0 block text and asserts `upsert_block` reports `refreshed` and the new text names `/model-asset`; SCN003–SCN005 (AC3–AC5) run `hooks/model_asset_reminder.py` with `sys.executable` as a subprocess, with `NMG_GAME_DEV_HOOK_STATE_DIR` under `tmp_path`, and assert exit code and stdout
- Unit tests cover the matcher regex against the plugin-scoped and unscoped tool names and a non-matching Blender tool, and the unwritable-state-dir case (state dir pointing at an existing regular file)
- The tests fail against the 0.21.0 description, block, and missing hook, and pass after T001–T003
- `uv run pytest tests/unit tests/bdd -q` (`repository.tests`), `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src tests` pass

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #130 | 2026-11-01 | Initial defect tasks |
