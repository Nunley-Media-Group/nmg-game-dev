# Verification Report: plugin.session-smoke reads the whole /mcp list at any window height

**Date**: 2026-11-11
**Issue**: #193
**Reviewer**: Claude (nmg-sdlc verify worker, architecture-reviewer inline)
**Scope**: Implementation verification against spec
**Verification head**: f39f09a0808d43a46ba91d5aa2833242479314eb

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4.4 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.6 |

### Implementation Status: Pass
**Total Issues**: 3 (all Low, none blocking)

All three acceptance criteria, three functional requirements, two tasks and three scenarios are implemented and covered by `tests/unit/test_plugin_session_smoke.py` (10 tests, driven through `node` against a fake `herdr`). The registered gate ran at the verification head with complete coverage (11 declared, 11 recorded, ceiling null): 10 applicable validations passed and `gate-ship-smoke` was correctly not applicable. The real `plugin.session-smoke` ran in a narrow Herdr pane, paged the `/mcp` list, opened the truncated `plugin:nmg-…` rows' detail views, and reported `nmg-game-dev:blender connected`. That is the exact failure this issue describes.

---

## Issue Scope

- Active issue: #193
- Spec: `specs/193-fix-plugin-session-smoke-failing-when-the-herdr-window-is-too-short-to-show-every-mcp-server`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3]; FR [FR1, FR2, FR3]; tasks [T001, T002]; scenarios [SCN001, SCN002, SCN003]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":193,"specPath":"specs/193-fix-plugin-session-smoke-failing-when-the-herdr-window-is-too-short-to-show-every-mcp-server","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3"],"functionalRequirements":["FR1","FR2","FR3"],"tasks":["T001","T002"],"scenarios":["SCN001","SCN002","SCN003"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/193.json`, generated 2026-11-12T02:12:45Z by `sdlc-verify-steering.mjs` for controller run `7034c3d5-701e-45e0-805e-ab16dcb8a610`.
- Identity: head `f39f09a0808d43a46ba91d5aa2833242479314eb` (clean tree); steering hash `sha256:795f9897…c0e4`; spec hash `sha256:dc0ff3b7…b548`.
- Coverage: declared 11, recorded 11, complete `true`; no missing, duplicate or unknown results.
- Ceiling: `null`.
- This worker re-checked the artifact against the live checkout with the finalizer's own `matchesRegisteredResults`: steering hash, spec hash, changed paths, per-validation config hashes, run id and head all match. The gate was not re-run because nothing changed since it finished.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | The smoke sees every server regardless of window height | Pass | `steering/extensions/plugin-session-smoke.mjs` `pageMcpList()` presses `up` while `↑ N more` shows and then `down` while `↓ N more` shows, reading after each key. `inspectTruncatedRows()` and `detailRow()` open a truncated `plugin:nmg-…` row with `enter`, read the full name and status from its detail view, and return with `esc`. Tests: `test_a_connected_server_below_the_fold_is_found`, `test_a_connected_server_above_a_bottom_scrolled_window_is_found`, `test_a_connected_server_with_a_truncated_name_is_found_in_its_detail_view`. Real smoke: `passed`, "plugin loaded via --plugin-dir; nmg-game-dev:blender connected" |
| AC2 | A genuinely missing or failed server still fails | Pass | `serverStatus(row)` returns `missing` with no row, `failed` on `SERVER_FAILED`, and `connected` on `SERVER_CONNECTED`, else `pending`. The summary names `nmg-game-dev:<server> <status>`. Tests: `test_a_server_missing_from_the_full_list_fails_and_is_named`, `test_a_failed_server_below_the_fold_fails_and_is_named`, `test_a_failed_server_with_a_truncated_name_fails_and_is_named`, `test_a_missing_server_among_truncated_names_is_walked_once` |
| AC3 | Evidence holds the full list | Pass | `record()` adds every non-blank line of every read, including detail rows, to an insertion-ordered `Set`. The `artifact` evidence is `bounded([...lines].join("\n"))`. Tests: `test_the_mcp_artifact_holds_every_row_read_after_paging` (all 16 rows), `test_refused_keys_are_recorded_as_paging_stopped_early`. Real smoke artifact contains rows read after `↓`/`↑` paging and the `Plugin:nmg-game-dev:texture-gen … Status: ✔ connected` detail row |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `pageMcpList()` uses `MORE_ABOVE`/`MORE_BELOW`, at most `MAX_SCROLL_KEYS = 200` presses per direction per pass, and runs once per `/mcp` poll. Servers are judged from `latest`, which keeps the most recent row across all reads |
| FR2 | Pass | The `SERVER_FAILED` / `SERVER_CONNECTED` rules and `config.expectConnected` are unchanged, and the run passes only when every expected server is `connected`. `steering/manifest.json` is not in the diff. `test_a_window_tall_enough_for_the_whole_list_sends_no_keys` passes |
| FR3 | Pass | `tests/unit/test_plugin_session_smoke.py` puts a fake `herdr` first on `PATH`. The fake renders a 16-row list at a configurable height and width, scrolls with the selection, draws the detail view and logs the keys it receives. No Claude Code, Blender or Unreal process starts |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Page through the whole /mcp list and judge servers from every row read | Complete | `createSmoke({ pollMs, keySettleMs, mcpPolls })` is exported. The frozen `extension`, its id and its provider id are unchanged, and the module imports only `node:` built-ins. f39f09a adds the truncated-row detail walk (see Remaining Issues, item 1) |
| T002 | Cover paging, failure naming, and evidence with a fake herdr | Complete | 10 tests. The 6 required by T002 plus 4 for truncated names and refused keys. All pass (`uv run pytest tests/unit/test_plugin_session_smoke.py -q`: 10 passed in 35.96s) and under `repository.tests` |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Paging (`pageMcpList`), row classification (`serverStatus`), truncation detection (`truncatedPluginRow`), detail parsing (`detailRow`) and the walk (`inspectTruncatedRows`) are separate functions. `smoke()` is still long because it owns session start-up, polling and evidence |
| Open/Closed | 4 | The marker and status rules are module constants. The provider contract with the nmg-sdlc loader is unchanged |
| Liskov Substitution | 5 | `createSmoke()` with default timings is the registered provider, with the same request and result shape |
| Interface Segregation | 5 | The helpers take only `press`, `onRead`, `signal` and `done` callbacks |
| Dependency Inversion | 4 | Timings are injected through `createSmoke`. `herdr` is reached through `PATH`, which the tests replace. The process runner is not injectable, but the `PATH` seam is enough |

### Layer Separation

The change is confined to the steering extension, a verification-gate provider. No shipped plugin, skill, MCP server or editor code changes.

### Dependency Flow

The module still imports only Node built-ins, so the nmg-sdlc steering loader can load it from its staged copy.

---

## Security Assessment

- [x] Authentication: not applicable
- [x] Authorization: not applicable. The session runs in an ephemeral `mkdtemp` project that is removed in `finally`
- [x] Input validation: screen text is only pattern-matched and never executed
- [x] Injection prevention: `spawn` is called with `shell: false` and argument arrays, so pane ids and keys are never interpolated into a shell
- [x] Data protection: evidence is bounded at 8000/4000 characters. It records `/mcp` rows, which contain server names and tool counts, not secrets

## Performance Assessment

- [x] Async patterns: every key press is awaited and followed by a settle wait (250 ms in production)
- [x] Resource management: presses are capped at 200 per direction per pass and the walk at `2 * serverCount` steps. The walk runs again only when the set of truncated rows changes and a server is still unresolved
- [x] Bounded runtime: polling is still capped at `MCP_POLLS = 60`. A paged pass adds roughly (rows − visible) × 250 ms per poll
- [ ] Minor: when no `N servers` line is read, `serverCount` defaults to `MAX_SCROLL_KEYS` (200), which raises the walk's upper bound to 400 steps. The walk still stops when every expected server is settled or the list wraps (Low)

## Testability Assessment

Excellent. The `createSmoke` factory and a stateful fake `herdr` cover each acceptance criterion and the refused-key path without real terminals or editors.

## Error Handling Assessment

- A refused `send-keys` ends the pass early and is recorded in the evidence as "paging stopped early", so rows that were never reached are explained.
- A detail view that cannot be parsed (`detailRow` returns null) ends the walk without a false positive. The server stays `missing` or `pending` and fails truthfully.
- Cancellation is still checked in every poll, and the tab and project are cleaned up in `finally`.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes: pytest tests in `tests/unit/test_plugin_session_smoke.py` | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |

### Coverage Summary

- Feature files: 3 scenarios in `feature.gherkin`, which names `tests/unit/test_plugin_session_smoke.py` as its implementation file
- Unit tests: 10 for this provider, all passing. The full `repository.tests` suite passed at the verification head
- Real smoke: `plugin.session-smoke` passed at the verification head through Herdr and a throwaway Claude Code session

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | No nmg-sdlc skill, workflow or agent changed. This repo's plugin surface is covered by the registered `plugin.validate` and `plugin.session-smoke`, and both passed |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q` exited 0 |
| `repository.lint` | Pass | `uv run ruff check .` exited 0 |
| `repository.format` | Pass | `uv run ruff format --check .` exited 0 |
| `repository.types` | Pass | `uv run mypy src tests` exited 0 |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh` exited 0 |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8` |
| `gate-mcp-schema` | Pass | `validate-mcp-tools.py` exited 0 |
| `gate-shellcheck` | Pass | exited 0 |
| `gate-ship-smoke` | Not applicable | No ship paths changed (recorded `skipped`, `applicable: false`) |
| `plugin.validate` | Pass | `claude plugin validate .` exited 0 |
| `plugin.session-smoke` | Pass | "plugin loaded via --plugin-dir; nmg-game-dev:blender connected"; ephemeral project and Herdr tab closed |

The applicability check ran against the stale local `main` ref, so it saw 198 changed paths and turned on gates that this issue's diff alone would not have needed. They all passed.

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None needed during verification | — | — |

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Low Priority

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Low | Spec drift | `specs/193-…/design.md` | f39f09a opens truncated rows with `enter`/`esc`. That goes beyond the design's "Navigation keys only move the list selection; nothing is activated". The real smoke run showed this is needed: a narrow pane truncates names to `plugin:nmg-…`. `enter` is pressed only on a list row and `esc` closes the detail view, so no server action is taken. T001's "no More marker → no keys" holds for the paging pass, but the detail walk can still press keys when names are truncated and an expected server is unresolved | Spec files are read-only in verify. Record the detail-view walk in the design's change history next time the spec is amended |
| Low | Robustness | `steering/extensions/plugin-session-smoke.mjs` `inspectTruncatedRows` | Assumes `esc` from a detail view selects the first list row. If Claude Code changes that, the walk can lose its place. It would then end at its step cap and report `missing` or `pending`, which fails safely rather than passing falsely | It matches current Claude Code behaviour and the real smoke confirmed it |
| Low | Performance | `steering/extensions/plugin-session-smoke.mjs` `serverCount` default | Without an `N servers` line, the walk's bound is 400 steps | It is bounded and stops early once every server is settled |

## Recommendation

Ready for PR.
