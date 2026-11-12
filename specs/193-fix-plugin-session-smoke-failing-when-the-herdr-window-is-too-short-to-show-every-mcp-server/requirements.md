# Defect Report: plugin.session-smoke reports below-the-fold /mcp servers as missing when the Herdr window is short

**Issue**: #193
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/123-register-the-project-verification-gates-and-a-ue-compile-extension-in-steering/

## Reproduction

1. Attach to Herdr with a terminal about 16 rows tall, so a new Herdr tab is about 16 rows tall.
2. Run the registered validation `plugin.session-smoke` (provider `project.plugin-session-smoke`) for a change that touches `.claude-plugin/**`.
3. Claude Code's `/mcp` list shows about six servers followed by `↓ 10 more`; `nmg-game-dev:blender` is not among the visible rows.
4. The validation fails with `plugin MCP servers not all connected: nmg-game-dev:blender missing`, although the server is connected.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | The provider reads every row of the `/mcp` list, whatever the tab height, and passes when every expected server is connected |
| **Actual** | The provider reads only the rows visible in its Herdr tab and reports servers below the `↓ N more` marker as `missing` |

## Acceptance Criteria

### AC1: The smoke sees every server regardless of window height

**Given** a Herdr tab too short to show the whole `/mcp` list, so the list shows a `↓ N more` marker and an expected server is below it
**When** the `project.plugin-session-smoke` provider runs
**Then** it reads every server row in the list and passes when every expected server is connected

### AC2: A genuinely missing or failed server still fails

**Given** an expected server that is absent from the full `/mcp` list, or listed as failed in a row below the fold
**When** the `project.plugin-session-smoke` provider runs
**Then** it returns `failed` and its summary names that server with its status, such as `nmg-game-dev:blender missing` or `nmg-game-dev:blender failed`

### AC3: Evidence holds the full list

**Given** a finished smoke run whose `/mcp` list was paged
**When** its evidence is read
**Then** the recorded `/mcp` artifact contains every server row that was inspected, including rows that were only visible after paging

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | The provider pages through the whole `/mcp` list by sending `up` keys while a `↑ N more` marker is visible and then `down` keys while a `↓ N more` marker is visible, reading the visible rows after each key, and judges servers from the rows combined across those reads | Must |
| FR2 | Pass/fail semantics and the expected-server configuration (`config.expectConnected`) are unchanged: a server is `connected`, `failed`, `pending`, or `missing` by the existing row rules, and the run passes only when every expected server is `connected` | Must |
| FR3 | Unit tests drive the provider with a fake `herdr` that returns a paged `/mcp` screen and cover AC1–AC3 | Must |

## Out of Scope

- Resizing the Herdr client or tab.
- Changing which servers `plugin.session-smoke` expects, or the manifest paths that make it apply.
- The trust-dialog handling and session start-up in the provider.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #193 | 2026-11-11 | Initial defect report |
