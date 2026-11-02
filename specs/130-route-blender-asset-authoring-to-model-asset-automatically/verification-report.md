# Verification Report: Route Blender asset authoring to /model-asset automatically

**Date**: 2026-11-02
**Issue**: #130
**Reviewer**: Claude (nmg-sdlc verify worker, controller run 9825eb77-4b5c-46d5-86aa-baa43d61dfab)
**Scope**: Implementation verification against spec (defect)
**Verification head**: ddc09d78b3c319129be69fd5869b55af87b284f5

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 5 |
| Testability | 5 |
| Error Handling | 5 |
| **Overall** | 5.0 |

### Implementation Status: Pass
**Total Issues**: 0 blocking, 1 low (advisory)

Three changes route Blender asset work to `/model-asset`: the skill description now names its trigger, the onboarding block now routes asset work to the skill, and a new plugin `PreToolUse` hook reminds the agent once per session. Together they meet all five acceptance criteria. Every applicable registered gate passed at the verification head. Coverage is complete (11 declared, 11 recorded), and the runner reports no ceiling.

---

## Issue Scope

- Active issue: #130
- Spec: `specs/130-route-blender-asset-authoring-to-model-asset-automatically`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC5]; FR [FR1–FR5]; tasks [T001–T005]; scenarios [SCN001–SCN005]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":130,"specPath":"specs/130-route-blender-asset-authoring-to-model-asset-automatically","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5"],"tasks":["T001","T002","T003","T004","T005"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 130 --spec specs/130-route-blender-asset-authoring-to-model-asset-automatically --base main --controller-run-id 9825eb77-4b5c-46d5-86aa-baa43d61dfab`
- Artifact: `.nmg-sdlc/verification/130.json`. Identity: head `ddc09d78b3c319129be69fd5869b55af87b284f5`, tree clean, spec hash `sha256:7821d932b3f1084d9a23e5cd746df573e8887540e50aa09ad9060bdba3609515`, steering hash `sha256:119992c8134117285b9116c3a61b6f610bfebaf708cd5e20ad1f72d83c5096a9`
- Coverage: declared 11, recorded 11, complete true. Missing, duplicate, and unknown are all empty
- Runner ceiling: none

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Skill description states its trigger | Pass | `skills/model-asset/SKILL.md:3`: a one-line description that starts "Use whenever you create or change an asset's geometry or materials in Blender" and still contains `freeform` and `Blender MCP`. SCN001 passes |
| AC2 | Consumer agent instructions route Blender asset work | Pass | `src/nmg_game_dev/onboard/instructions.py` `block_text()` adds, inside the markers, "Run `/model-asset` for any asset authoring or editing in Blender … Scene inspection and `/finalize-asset` runs do not need it." SCN002 seeds the 0.21.0 block and asserts that `upsert_block` reports `refreshed` |
| AC3 | Hook reminds once per session on `execute_blender_code` | Pass | `hooks/hooks.json` registers a `PreToolUse` command hook with matcher `^mcp__.*blender.*__execute_blender_code$`. `hooks/model_asset_reminder.py` prints `hookSpecificOutput` with `hookEventName: PreToolUse` and the routing `additionalContext`, with no `permissionDecision` or block decision, and exits 0. Unit tests match the scoped and unscoped names and reject `get_scene_info`, `look`, `execute_blender_code_v2`, and Unreal tools. SCN003 passes. A live run in this verification printed the reminder for session `s-1` and exited 0 |
| AC4 | Silent after first reminder | Pass | An exclusive-create marker (`open("x")`) keyed by the SHA-256 of the session id. In the live run, the repeat call for `s-1` printed nothing and exited 0, and `s-2` received the reminder. SCN004 passes |
| AC5 | Existing behavior preserved; hook fails open | Pass | The full suite passes: 969 passed, 9 skipped. The block still links the asset contract and the design contract. Invalid JSON, a missing or empty `session_id`, and an unwritable state directory (the state dir is a regular file) each exit 0 with no output. SCN005 passes, unit tests cover these cases, and in the live run invalid input exited 0 silently |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Skill description trigger | Complete | `skills/model-asset/SKILL.md` |
| T002 | Onboarding block routing | Complete | `src/nmg_game_dev/onboard/instructions.py`. The module docstring also cites #130 |
| T003 | PreToolUse reminder hook | Complete | `hooks/hooks.json`, `hooks/model_asset_reminder.py`. Honors `NMG_GAME_DEV_HOOK_STATE_DIR`. `plugin.validate` passes |
| T004 | Docs | Complete | `docs/skills/model-asset.md` § "When it runs" and `docs/onboarding/index.md` step 1. The `CHANGELOG.md` `### Fixed` bullet ends `(#130)`. The release bump moved it from `[Unreleased]` to `## [0.21.1]`, and VERSION 0.21.1 is synced across plugin.json, blender_manifest.toml, and the .uplugin |
| T005 | Regression coverage | Complete | `tests/bdd/features/model_asset_routing.feature` (SCN001–SCN005), `tests/bdd/test_model_asset_routing_bdd.py`, `tests/unit/onboard/test_instructions.py`, `tests/unit/test_model_asset_reminder_hook.py` |

---

## Architecture Assessment

| Area | Score (1-5) | Notes |
|------|-------------|-------|
| SOLID Principles | 5 | The hook is a small stdlib script with one job. `main()` is a pure function of stdin text and the state dir, and I/O is confined to `__main__`. The onboarding change only adds text to the existing block |
| Security | 5 | No network and no subprocess. Session ids are hashed before they become file names, so the path cannot be traversed. The hook never denies or blocks a tool call |
| Performance | 5 | One JSON parse and one exclusive file create per `execute_blender_code` call, under a 10 s timeout. The matcher fires only on that tool |
| Testability | 5 | The state directory can be overridden through an env var. Tests load the hook by path for unit checks and run it as a subprocess with `sys.executable` for the BDD scenarios |
| Error Handling | 5 | Fails open on every path: `ValueError` from bad JSON, a non-dict event, a missing session id, and `OSError` from the state dir all return silently, and a top-level `except Exception` exits 0. Exclusive create keeps concurrent first calls from both printing the reminder |

**Average**: 5.0

---

## Test Results

### Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 969 passed, 9 skipped |
| `repository.lint` | Pass | `uv run ruff check .`: All checks passed |
| `repository.format` | Pass | `uv run ruff format --check .`: 309 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: no issues in 197 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 179 passed. Applies because of the `blender_manifest.toml` version bump |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8`. Applies because of the `.uplugin` version bump |
| `gate-mcp-schema` | Not applicable | No `mcp-servers/**` or validator changes |
| `gate-shellcheck` | Not applicable | No `scripts/**.sh` changes |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .` passed with warnings. The warnings (root CLAUDE.md is not loaded as context; LICENSE, icon, and privacy URL are missing for directory submission) predate this change |
| `plugin.session-smoke` | Pass | Plugin loaded with `--plugin-dir` in an ephemeral Herdr project, and `plugin:nmg-game-dev:blender` connected |

**Gate Summary**: 8/8 applicable passed, 0 failed, 0 incomplete (3 not applicable)

### BDD coverage

- Scenarios: SCN001–SCN005 cover 5/5 acceptance criteria
- Step definitions: implemented in `tests/bdd/test_model_asset_routing_bdd.py`
- Execution: Pass

### Exercise testing

Not applicable. This repository is not the nmg-sdlc plugin, and the diff touches no `workflows/` or `agents/` paths. `plugin.validate`, `plugin.session-smoke`, the subprocess BDD scenarios, and the live hook run above cover the shipped hook and skill.

### Smoke

The manifest declares no `repository.nmg-sdlc-smoke` or `project.nmg-sdlc-smoke`. The registered `plugin.session-smoke` passed.

---

## Fixes Applied

| Severity | Category | Location | Issue | Fix | Routing |
|----------|----------|----------|-------|-----|---------|
| — | — | — | None needed | — | — |

## Remaining Issues

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Low | Portability (advisory) | `hooks/hooks.json` | The hook command runs `python3`. A consumer host without `python3` on `PATH` gets a non-blocking hook error instead of the reminder, and the tool call still proceeds | The steering already requires Python 3.11+ on host tooling, and the failure does not block anything. No change is needed for this defect |

## Recommendation

Ready for PR.
