# Verification Report: Scan untracked exportable files in the /ship secret gate

**Date**: 2026-11-19
**Issue**: #296
**Reviewer**: nmg-sdlc verify (gate phase)
**Scope**: Implementation verification against spec
**Verification head**: c2bfe7c203736e89ce50e2fc56773d03eec08734

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
**Total Issues**: 0

The review (head 54ff5e9, scoped after a repair of findings F1 and F2) passed with no findings. The gate ran once at the merge-queue head c2bfe7c, which adds only the version bump and changelog entry. Every registered pre-merge validation that applies passed, and coverage is complete (11 declared, 11 recorded).

Deterministic steering artifact: `.nmg-sdlc/verification/296.json`. Ceiling: none. Coverage: declared 11, recorded 11, complete true.

---

## Issue Scope

- Active issue: #296
- Spec: `specs/296-scan-untracked-exportable-files-in-the-ship-secret-gate-and-align-255-ac4`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3]; FR [FR1, FR2, FR3, FR4, FR5]; tasks [T001, T002, T003, T004, T005]; scenarios [SCN001, SCN002, SCN003]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":296,"specPath":"specs/296-scan-untracked-exportable-files-in-the-ship-secret-gate-and-align-255-ac4","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5"],"tasks":["T001","T002","T003","T004","T005"],"scenarios":["SCN001","SCN002","SCN003"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Acceptance Criteria Verification

| AC | Description | Status | Exercised | Evidence |
|----|-------------|--------|-----------|----------|
| AC1 | Untracked files that would be exported are scanned | Pass | real entry point | `src/nmg_game_dev/secrets/scan.py` `shippable_files` adds `git ls-files -z --others --exclude-standard -- game/`; `src/nmg_game_dev/ship/runner.py` runs `_scan_secrets` before any Godot call and in dry run. `tests/unit/ship/test_runner.py` (dry run and real ship, masked line, no Godot call), BDD SCN001 |
| AC2 | Ignored and non-exported untracked files are not scanned | Pass | real entry point | `--exclude-standard` skips ignored files, the `game/` pathspec excludes files outside the project, and `game/.godot/` is dropped. `tests/unit/secrets/test_scan.py` ignored/outside/.godot tests, BDD SCN002 outline |
| AC3 | Outside git, local secret stores are skipped and every other file is scanned | Pass | real entry point | Non-work-tree branch returns the unchanged #255 walk. `test_outside_git_*` runner tests, BDD SCN003 outline |

No criterion's tests mock the path under test.

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | Same patterns, `.env` rule, masking and `.nmg/secret-scan-allow` handling for untracked `game/` files; allow-file test for untracked matches in `test_scan.py` |
| FR2 | Pass | Symlinks and non-regular paths skipped; `.godot` filter; tests pass |
| FR3 | Pass | Non-git path unchanged; `test_outside_a_work_tree_the_ship_scan_walks_as_before` |
| FR4 | Pass | Standard-library only; `--staged` / `--tracked` CLI untouched |
| FR5 | Pass | `docs/skills/ship.md`, `docs/onboarding/index.md` and `skills/ship/SKILL.md` describe the untracked scan and non-git exclusions |

---

## Task Completion

| Task | Description | Status |
|------|-------------|--------|
| T001 | Add the ship file source to the scanner | Complete |
| T002 | Point the /ship gate at the new scan | Complete |
| T003 | Unit tests for the scanner and the ship gate | Complete |
| T004 | BDD scenarios for the untracked and non-git gate | Complete |
| T005 | Update the ship and onboarding docs | Complete |

---

## Architecture Assessment

| Area | Score (1-5) | Notes |
|------|-------------|-------|
| SOLID Principles | 5 | File-source selection (`shippable_files`) stays separate from scanning; runner only swaps the entry it calls |
| Security | 5 | Widens the secret gate to untracked exportable files; matches stay masked; no new dependencies |
| Performance | 5 | One extra `git ls-files` call per ship |
| Testability | 5 | Tests drive real git repos and the real `/ship` runner entry point |
| Error Handling | 5 | Git failures in either listing raise `GitError`, surfaced as structured `ship.secret_scan_failed` with remediation (DP2) |

Design paths: DP1 (non-work-tree walk) pass; DP2 (git failure inside a work tree) pass. Consumers CON1-CON4 (runner, scanner CLI and onboarding copy, docs, ship SKILL.md) consistent.

---

## Test Results

| Validation | Tier | Selection | Status | Evidence |
|------------|------|-----------|--------|----------|
| repository.tests | none | none | Pass | `uv run pytest tests/unit tests/bdd -q`: 2550 passed, 24 skipped |
| repository.lint | none | none | Pass | `uv run ruff check .` exited 0 |
| repository.format | none | none | Pass | `uv run ruff format --check .` exited 0 |
| repository.types | none | none | Pass | `uv run mypy src tests` exited 0 |
| gate-blender-headless | none | none | Pass | `scripts/run-blender-tests.sh` exited 0 |
| gate-godot-headless | none | none | Pass | `scripts/run-godot-tests.sh` exited 0 |
| gate-mcp-schema | none | none | Not applicable | No `mcp-servers/**` change |
| gate-shellcheck | none | none | Not applicable | No `scripts/**.sh` change |
| gate-ship-smoke | none | none | Pass | `scripts/ship-smoke.sh` exited 0 |
| plugin.validate | none | none | Pass | `claude plugin validate .` exited 0 |
| plugin.session-smoke | none | none | Pass | Plugin loaded via `--plugin-dir`; nmg-game-dev:blender connected |

**Gate Summary**: 9/9 applicable passed, 0 failed, 0 incomplete; 2 not applicable.

Real smoke lifecycle: `plugin.session-smoke` (extension `project.plugin-session-smoke`) ran in an ephemeral project and passed. No `repository.nmg-sdlc-smoke` is registered.

---

## Fixes Applied

| Severity | Category | Location | Issue | Fix | Routing |
|----------|----------|----------|-------|-----|---------|
| minor | Docs | `skills/ship/SKILL.md`, `docs/onboarding/index.md` | F1: consumer-facing text still described a tracked-only scan | Repaired in implement (54ff5e9) | direct |
| minor | Testability | `tests/unit/secrets/test_scan.py` | F2: no test that the allow file covers untracked `game/` matches | Test added in implement (54ff5e9) | direct |

## Remaining Issues

None.

## Recommendation

Ready for PR.
