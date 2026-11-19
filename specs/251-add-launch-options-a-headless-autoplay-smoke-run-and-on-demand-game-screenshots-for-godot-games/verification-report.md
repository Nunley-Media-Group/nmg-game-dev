# Verification Report: Launch options, headless autoplay smoke run, and on-demand game screenshots

**Date**: 2026-11-19
**Issue**: #251
**Reviewer**: Claude (nmg-sdlc verify worker, gate phase)
**Scope**: Implementation verification against spec
**Verification head**: cc35bc7c851bc30d777c8e235e04f1be2724ccc9

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 5 |
| Testability | 4 |
| Error Handling | 5 |
| **Overall** | 4.8 |

### Implementation Status: Pass
**Total Issues**: 0 above info (2 info notes)

The review of this source (reviewed head `4cf18007cb906aa97906c4253c9f3f0699f20e17`, full mode, result passed) found no finding above `info`. The branch was then integrated with `main` and its version prepared (0.30.0). The pre-merge gate ran once at the verification head through `sdlc-verify-steering.mjs`: all 11 registered validations are applicable, required, and passed; coverage is complete (declared 11, recorded 11, no missing, duplicate, or unknown); no ceiling.

---

## Issue Scope

- Active issue: #251
- Spec: `specs/251-add-launch-options-a-headless-autoplay-smoke-run-and-on-demand-game-screenshots-for-godot-games`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1-AC8]; FR [FR1-FR8]; tasks [T001-T009]; scenarios [SCN001-SCN008]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":251,"specPath":"specs/251-add-launch-options-a-headless-autoplay-smoke-run-and-on-demand-game-screenshots-for-godot-games","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008","T009"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/251.json` (schemaVersion 1), tier `pre-merge`, base `main`
- Identity: head `cc35bc7c851bc30d777c8e235e04f1be2724ccc9`, tree clean, steering `sha256:06873b51...`, spec `sha256:e8432e83...`
- Ceiling: none
- Coverage: declared 11, recorded 11, complete true

---

## Acceptance Criteria Verification

| AC | Description | Status | Exercised | Evidence |
|----|-------------|--------|-----------|----------|
| AC1 | Launch options read the same on desktop and web | Pass | real entry point | `nmg_launch.gd` configure/get_option/has_option; `test_nmg_launch.gd` cmdline, web hash, flag, default, hash-wins tests pass in real Godot (gate-godot-headless: 28 passed). JavaScriptBridge read itself needs a web export. |
| AC2 | The smoke run passes a clean game | Pass | mocked | `smoke.py`, `godot/__main__.py smoke`; `_autoplay_when_scene_ready` waits for the main scene. BDD SCN002 uses FakeGodotRunner; the review ran the real CLI against Godot 4.7.2 ("smoke passed (120 frames)"). |
| AC3 | The smoke run fails on runtime errors | Pass | mocked | `smoke.py` check_smoke: smoke.timeout / smoke.runtime_error with first 20 error lines; `test_smoke.py`, BDD SCN003; real probe printed the SCRIPT ERROR line and exit 1. |
| AC4 | `/ship` gates on the smoke run | Pass | mocked | `ship/runner.py` `_run_smoke` after project tests, before mobile budgets; `ship.smoke_failed`; `tests/unit/ship/test_runner.py`, BDD SCN004; gate-ship-smoke dry run passed. |
| AC5 | A screenshot is saved on demand | Pass | mocked | `shot.py` take_shot (windowed), `__main__.py shot`, `mcp_tools.game_screenshot`, `nmg_launch.gd _take_shot`; `test_shot.py`, `test_cli.py`, `test_finalize_mcp_tools.py`, BDD SCN005. The windowed save needs a display. |
| AC6 | A failed screenshot is reported | Pass | mocked | `shot.no_image` with output tail, `godot.not_found`, structured MCP error; `test_shot.py`, BDD SCN006. |
| AC7 | Test runs use their own save folder | Pass | real entry point | `nmg_launch.gd save_dir`; save-dir tests pass in real Godot. |
| AC8 | Onboarding registers the NmgLaunch autoload | Pass | real entry point | `onboard/godot.py` LAUNCH_AUTOLOAD_RES in render and DRIFT_CHECKED; `tests/unit/onboard/test_runner.py` AC8 tests and BDD SCN008 against temp projects. |

Criteria whose tests mock the path under test: **AC2, AC3, AC4, AC5, AC6** (the Godot process is faked by FakeGodotRunner or a patched `subprocess.run`, by design; the review's real-Godot smoke probes cover AC2 and AC3).

Functional requirements FR1-FR8: all pass (see `.nmg-sdlc/verification/251-review.md`). Design paths DP1-DP10 and consumers C1-C6: all pass.

---

## Task Completion

| Task | Description | Status |
|------|-------------|--------|
| T001 | Add the NmgLaunch autoload to the add-on | Complete |
| T002 | Test NmgLaunch in the headless add-on runner | Complete |
| T003 | Add the smoke and shot commands to the Godot boundary | Complete |
| T004 | Add the game_screenshot finalize MCP tool | Complete |
| T005 | Gate /ship on the smoke run | Complete |
| T006 | Register the NmgLaunch autoload during onboarding | Complete |
| T007 | Python unit tests for smoke, shot, the MCP tool, the ship gate, and onboarding | Complete |
| T008 | BDD scenarios for launch options, smoke, shot, ship, and onboarding | Complete |
| T009 | Document launch options, the smoke run, and screenshots | Complete |

---

## Architecture Assessment

| Area | Score (1-5) | Notes |
|------|-------------|-------|
| SOLID Principles | 5 | Godot work stays inside `src/nmg_game_dev/godot/` (smoke.py, shot.py, project.py); the finalize MCP tool wraps it without logic; ship calls it as one gate step. |
| Security | 5 | No credentials; launch options are parsed as key/value strings; shot paths validated (`shot.invalid_path`, `invalid_after` incl. NaN). |
| Performance | 5 | No per-frame hook beyond a bounded (600-frame) one-shot autoplay wait; smoke and shot runs are timeout-bounded. |
| Testability | 4 | Real-Godot add-on tests for parsing, autoplay, save dir; Python layers tested with fakes; windowed shot and web hash read not exercisable headless. |
| Error Handling | 5 | Structured errors with remediation for timeout, runtime error, no_image, invalid_after, invalid_path, not_found, project_missing, ship.smoke_failed. |

Layer separation follows `steering/snippets/project-structure.md`: no live editor bridge, Godot runs only through the boundary; the add-on owns runtime behavior only.

---

## Test Coverage

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1-AC8 | Yes (SCN001-SCN008) | Yes | Yes |

- `repository.tests`: 2057 passed, 19 skipped
- `gate-godot-headless`: add-on runner 28 passed, 0 failed; import and probes passed
- `gate-blender-headless`: 428 passed, 4 skipped
- `repository.types`: no issues in 290 source files

---

## Steering Doc Verification Gates

| Gate | Tier | Selection | Status | Evidence |
|------|------|-----------|--------|----------|
| repository.tests | null | null | Pass | command exited 0; 2057 passed, 19 skipped |
| repository.lint | null | null | Pass | command exited 0 |
| repository.format | null | null | Pass | command exited 0 |
| repository.types | null | null | Pass | command exited 0; mypy no issues |
| gate-blender-headless | null | null | Pass | command exited 0; 428 passed |
| gate-godot-headless | null | null | Pass | import, add-on tests (28 passed), and probes passed |
| gate-mcp-schema | null | null | Pass | command exited 0 |
| gate-shellcheck | null | null | Pass | command exited 0 |
| gate-ship-smoke | null | null | Pass | command exited 0 (dry-run /ship all of the fixture) |
| plugin.validate | null | null | Pass | command exited 0 |
| plugin.session-smoke | null | null | Pass | plugin loaded via --plugin-dir; nmg-game-dev:blender connected |

**Gate Summary**: 11/11 passed, 0 failed, 0 incomplete. The project declares no tiers, so every required validation ran.

---

## Fixes Applied

None in the gate phase (review findings from the earlier review cycle were repaired in implement before this source was reviewed and passed).

## Remaining Issues

No critical, high, medium, or low issues. Info notes:

- **F1** (info, test-quality): AC2-AC6 tests mock the Godot process by design; the windowed `_take_shot` save and the web JavaScriptBridge hash read are not exercised (need a display / web export).
- **F2** (info, acceptance): the doc comment at `nmg_launch.gd:13` is 158 characters, past the GDScript 100-column guideline; cosmetic.

---

## Recommendation

**Ready for PR / merge.** The review passed with info notes only, and every registered pre-merge validation passed at the exact verification head with complete coverage.
