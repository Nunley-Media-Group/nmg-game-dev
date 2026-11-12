# Tasks: plugin.session-smoke reports below-the-fold /mcp servers as missing when the Herdr window is short

**Issue**: #193
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/123-register-the-project-verification-gates-and-a-ue-compile-extension-in-steering/

## Implementation Tasks

### T001: Page through the whole /mcp list and judge servers from every row read

**File(s)**: `steering/extensions/plugin-session-smoke.mjs`
**Type**: Modify
**Depends**: none
**Acceptance**:
- Each `/mcp` poll reads the visible screen, sends `herdr pane send-keys <pane> up` and re-reads while a `↑ N more` marker is visible, then sends `down` and re-reads while a `↓ N more` marker is visible, with at most 200 presses per direction per pass (FR1).
- A server's status comes from the most recent row read that contains `nmg-game-dev` and the server name, classified by the existing failed/connected rules, or `missing` when no read showed it; the run passes only when every `config.expectConnected` server is `connected` (AC1, AC2, FR2).
- The `/mcp` artifact evidence holds the distinct lines from every read in first-seen order (AC3).
- The module exports `createSmoke({ pollMs, keySettleMs, mcpPolls })` returning the provider; the frozen `extension` export, its id `project.plugin-session-smoke`, and its provider id are unchanged, and the module still imports only Node built-ins.
- With no `More` marker on screen, a pass sends no keys.

### T002: Cover paging, failure naming, and evidence with a fake herdr

**File(s)**: `tests/unit/test_plugin_session_smoke.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- A fake `herdr` executable placed first on `PATH` answers `tab create`, `tab list`, `pane list`, `agent start`, `agent prompt`, `pane read`, `pane send-keys`, and `tab close`; it renders a `/mcp` list of 16 rows in a window of configurable height with `↑ N more` / `↓ N more` markers, moves its selection on `up`/`down` keys and scrolls to keep the selection visible, and logs the keys it received. The tests start no Claude Code, Blender, or Unreal process.
- Each test runs the provider through `node` using `createSmoke` with near-zero poll and settle times and a small poll count, and reads the provider result as JSON.
- AC1: with a 6-row window and `plugin:nmg-game-dev:blender` connected at row 13, the result is `passed`, the summary contains `nmg-game-dev:blender connected`, and the fake logged `down` keys.
- AC1: with the window initially scrolled to the bottom and the blender row at row 2, the result is `passed` and the fake logged `up` keys.
- AC2: with no blender row in the list, the result is `failed` and the summary contains `nmg-game-dev:blender missing`.
- AC2: with the blender row below the fold marked `✘ failed`, the result is `failed` and the summary contains `nmg-game-dev:blender failed`.
- AC3: after a paged run, the `artifact` evidence entry contains every one of the 16 row strings.
- FR2: with a window tall enough for the whole list, the result is `passed` and the fake logged no keys.
- Passes under `repository.tests` (`uv run pytest tests/unit tests/bdd -q`), and the module passes `repository.lint`, `repository.format`, and `repository.types`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #193 | 2026-11-11 | Initial defect tasks |
