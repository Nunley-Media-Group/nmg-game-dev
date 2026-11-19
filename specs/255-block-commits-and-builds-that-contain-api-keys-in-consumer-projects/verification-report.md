# Verification Report: Block commits and builds that contain API keys in consumer projects

**Date**: 2026-11-19
**Issue**: #255
**Reviewer**: Claude (nmg-sdlc verify worker, gate phase)
**Scope**: Pre-merge gate against the Approved spec; review passed earlier for this source
**Verification head**: 3eaee1256339c84c405066e0bafbe17227e049e2

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 5 |
| **Overall** | 4.8 |

### Implementation Status: Pass
**Total Issues**: 0 blocking/major/minor; 2 info notes (F3, F4)

The review checklist (`.nmg-sdlc/verification/255-review.json`) passed with no finding above `info`. The steering gate runner ran every registered pre-merge validation at the verification head: coverage is complete (11 declared, 11 recorded), every applicable required validation passed, and no ceiling applies.

---

## Issue Scope

- Active issue: #255
- Spec: `specs/255-block-commits-and-builds-that-contain-api-keys-in-consumer-projects`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5]; FR [FR1, FR2, FR3, FR4, FR5, FR6]; tasks [T001, T002, T003, T004, T005, T006]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":255,"specPath":"specs/255-block-commits-and-builds-that-contain-api-keys-in-consumer-projects","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6"],"tasks":["T001","T002","T003","T004","T005","T006"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/255.json` (tier `pre-merge`; this project declares no validation tiers, so every result records `tier: null`, `selection: null`)
- Identity: head `3eaee1256339c84c405066e0bafbe17227e049e2`, tree clean
- Coverage: declared 11, recorded 11, complete; no missing, duplicate or unknown results
- Ceiling: none

---

## Acceptance Criteria Verification

From the passed review record. No criterion's tests mock the path under test.

| AC | Description | Status | Exercised | Evidence |
|----|-------------|--------|-----------|----------|
| AC1 | A commit that stages a key is blocked | Pass | real entry point | `src/nmg_game_dev/secrets/scan.py` `staged_files` reads stage-0 blobs (`:0:<path>`); `tests/unit/secrets/test_scan.py` drives a real git index and `main --staged` (exit 1) |
| AC2 | A clean commit proceeds | Pass | real entry point | Clean staged set exits 0, including `<digit>:<rest>` paths (`test_scan.py`) |
| AC3 | Reviewed false positives are allowed via `.nmg/secret-scan-allow` | Pass | real entry point | `load_allow` / `Allow.permits` (`sha256:` and `<path>:<pattern>`); unit, ship and BDD tests |
| AC4 | `/ship` refuses to build when a key is found | Pass | real entry point | `src/nmg_game_dev/ship/runner.py` `_scan_secrets` runs before version, changelog, signing, presets and every Godot command; `tests/unit/ship/test_runner.py` |
| AC5 | Onboarding installs the scanner and pre-commit hook | Pass | real entry point | `src/nmg_game_dev/onboard/secrets_hook.py`; `tests/unit/onboard/test_secrets_hook.py` install, conflict, not-a-repo states |

## Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `python -m nmg_game_dev.secrets scan --staged/--tracked/--root`; stdlib-only scanner |
| FR2 | Pass | `ensure_secret_scanner` syncs `scan.py` to `scripts/nmg_secret_scan.py`; hook resolved via `git rev-parse --git-path hooks` |
| FR3 | Pass | Secret scan is the first ship gate line (`secrets: no matches`) |
| FR4 | Pass | `Match.value` is `repr=False`; reports and `ShipError` carry masked values only |
| FR5 | Pass | Per-pattern, masking, fingerprint, allow, binary and LFS-pointer skips, hook states and ship gate tests; BDD `tests/bdd/features/secret_scan.feature` SCN001-SCN005 |
| FR6 | Pass | `docs/onboarding/index.md`, `docs/skills/ship.md`, `skills/ship/SKILL.md`, `skills/onboard-consumer/SKILL.md` |

## Task Completion

| Task | Status |
|------|--------|
| T001-T006 | Complete (verified by review rows AC1-AC5, FR1-FR6, DP1-DP12, C1-C7) |

---

## Architecture Assessment

| Area | Score (1-5) | Notes |
|------|-------------|-------|
| SOLID Principles | 5 | Scanner is a single stdlib module reused by CLI, hook copy and ship gate; onboarding step isolated in `secrets_hook.py` |
| Security | 5 | Raw secret values never printed; masked rendering; allow-list by fingerprint or path:pattern |
| Performance | 4 | Binary/LFS skip by probe; walk skips `.venv`, `node_modules` |
| Testability | 5 | Real git repos in tests; CLI `main` driven directly |
| Error Handling | 5 | `GitError` -> exit 2 / `ship.secret_scan_failed`; structured onboarding `conflict`/`skipped` statuses with remediation |

Layer separation follows steering: skills call `python -m nmg_game_dev.*`; ship runner owns the gate; onboarding owns installation.

---

## Test Results (Steering Doc Verification Gates)

| Gate | Tier | Selection | Status | Evidence |
|------|------|-----------|--------|----------|
| repository.tests | null | null | Pass | `uv run pytest tests/unit tests/bdd -q` exited 0 |
| repository.lint | null | null | Pass | `uv run ruff check .` exited 0 |
| repository.format | null | null | Pass | `uv run ruff format --check .` exited 0 |
| repository.types | null | null | Pass | `uv run mypy src tests` exited 0 |
| gate-blender-headless | null | null | Pass | `scripts/run-blender-tests.sh` exited 0 |
| gate-godot-headless | null | null | Pass | `scripts/run-godot-tests.sh` exited 0 |
| gate-mcp-schema | null | null | Not applicable | No `mcp-servers/**` change |
| gate-shellcheck | null | null | Not applicable | No `scripts/**.sh` change |
| gate-ship-smoke | null | null | Pass | `scripts/ship-smoke.sh` exited 0 |
| plugin.validate | null | null | Pass | `claude plugin validate .` exited 0 |
| plugin.session-smoke | null | null | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 9/9 applicable gates passed, 0 failed, 0 incomplete (2 not applicable)

Real smoke lifecycle: `plugin.session-smoke` (extension `project.plugin-session-smoke`) passed against this checkout. No `repository.nmg-sdlc-smoke` validation is declared in this project.

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| major | Correctness | `src/nmg_game_dev/secrets/scan.py` | F1 (earlier review): staged blob spec `:<path>` misread `<digit>:<rest>` paths | Explicit stage-0 `:0:<path>` plus regression test | direct (implement stage) |
| minor | Docs | `docs/skills/ship.md` | F2 (earlier review): documented gate order did not match `run_ship` | Reordered to match | direct (implement stage) |

## Remaining Issues

None blocking. Info notes carried from the review:

- **F3** (info): The non-git walk also skips `.env*`, `.claude/settings.local.json`, `.venv/`, `node_modules/`, and onboarding skips the hook when the target is a subfolder of a larger repository. Both are safer than the spec wording and documented.
- **F4** (info): In a git work tree `/ship` scans tracked files only, as AC4 specifies; an untracked, unignored file under `game/` holding a key would still be exported. Candidate follow-up.

---

## Recommendation

**Ready for PR**

Review passed with no finding above info, and every applicable registered pre-merge validation passed at the verification head with complete coverage.
