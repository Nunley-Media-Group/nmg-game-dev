# Root Cause Analysis: plugin.session-smoke reports below-the-fold /mcp servers as missing when the Herdr window is short

**Issue**: #193
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/123-register-the-project-verification-gates-and-a-ue-compile-extension-in-steering/

## Root Cause

`smoke()` in `steering/extensions/plugin-session-smoke.mjs` sends `/mcp` and then polls `herdr pane read <pane> --source visible --format text`. That source returns only the rows that fit the pane, and a new Herdr tab takes the size of the Herdr client window. Claude Code renders `/mcp` as a scrolling selection list: when it does not fit, it shows a window of rows with `↓ N more` below (and `↑ N more` above once scrolled). `serverStatus()` searches only that one visible screen, so any expected server outside the window is classified `missing`, and the run fails even though the server is connected.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `steering/extensions/plugin-session-smoke.mjs` | `smoke()` `/mcp` polling loop | Reads one visible screen per poll and judges servers from it |
| `steering/extensions/plugin-session-smoke.mjs` | `serverStatus()` | Classifies a server from the single visible screen |
| `steering/extensions/plugin-session-smoke.mjs` | `/mcp` artifact evidence | Records only the last visible screen |

## Fix Strategy

Page through the list on every poll and judge from every row read.

1. Add constants `MORE_ABOVE = /↑\s*\d+\s+more/`, `MORE_BELOW = /↓\s*\d+\s+more/`, `MAX_SCROLL_KEYS = 200` (per direction per pass), and `KEY_SETTLE_MS = 250`.
2. Each `/mcp` poll runs one list pass: read the visible screen; while `MORE_ABOVE` matches and fewer than `MAX_SCROLL_KEYS` presses were sent, `herdr pane send-keys <pane> up`, wait the key settle time, and read again; then do the same with `MORE_BELOW` and `down`. Herdr already accepts `up`/`down` key names (the trust dialog sends `down`). Navigation keys only move the list selection; nothing is activated.
3. Every read is recorded: its lines are appended to an ordered list of distinct lines (first-seen order), and for each expected server, the most recent line that contains both `nmg-game-dev` and the server name (the existing row rule) is kept as that server's latest row.
4. A server's status comes from its latest row with the existing `SERVER_FAILED` / `SERVER_CONNECTED` rules (`failed`, `connected`, otherwise `pending`), or `missing` when no read has shown a row for it. `serverStatus(screen, server)` becomes a row classifier over that latest row. The poll loop still stops early once every expected server is `connected` or `failed`, and the run still passes only when all are `connected`.
5. The `/mcp` artifact evidence records the distinct lines from every read (bounded as before), so it holds every row inspected, not just the final screen.
6. Testability seam: the module exports `createSmoke({ pollMs = POLL_MS, keySettleMs = KEY_SETTLE_MS, mcpPolls = MCP_POLLS } = {})`, which returns the provider function; `extension.providers["project.plugin-session-smoke"]` is `createSmoke()`. The frozen `extension` export, its id, provider id, and the Node-built-ins-only imports are unchanged, so the nmg-sdlc steering loader (which reads only the `extension` export) is unaffected.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `steering/extensions/plugin-session-smoke.mjs` | Add paging pass, latest-row-per-server tracking, distinct-line artifact, and the `createSmoke` factory | AC1, AC2, AC3, FR1, FR2 |
| `tests/unit/test_plugin_session_smoke.py` | New pytest module driving the provider through `node` with a fake `herdr` on `PATH` | FR3; proves AC1–AC3 |

## Blast Radius

Only the `plugin.session-smoke` validation calls this provider. The manifest record (`steering/manifest.json`, `config.expectConnected: ["blender"]`, `when` paths) is unchanged. On a tall tab with no `More` markers the pass reads one screen and sends no keys, so behaviour there is the same as before. The tests never start Claude Code, Blender, or Unreal: the fake `herdr` answers every `herdr` subcommand the provider calls.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Page with `up`/`down` keys until no `More` marker remains | Selected | Works at any tab height with the existing `--source visible` read; matches how the list scrolls |
| Read `--source recent` (scrollback) instead | Rejected | The `/mcp` list is a redrawn TUI selection list, so off-screen rows never reach scrollback |
| Resize the Herdr tab before reading | Rejected | New tabs inherit the client size and the provider cannot rely on resizing the user's client |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #193 | 2026-11-11 | Initial defect design |
