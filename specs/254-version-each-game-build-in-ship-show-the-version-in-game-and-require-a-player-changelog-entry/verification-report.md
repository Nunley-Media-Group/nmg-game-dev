# Verification Report: Version each game build in /ship, show the version in game, and require a player changelog entry

**Date**: 2026-11-19
**Issue**: #254
**Reviewer**: Claude (nmg-sdlc verify, gate phase)
**Scope**: Implementation verification against spec
**Verification head**: 9022cd4c4d95ae9dd060241c5122f2641b64b066

---

## Executive Summary

The review passed (full mode, reviewed head `008794222a7a5cc757410aafd1f96671468b11d8`) with no finding above `info`. That head has since been merged with `origin/main` (#291, #292) and the version prepared (`VERSION` 0.34.0, commit `9022cd4`). The pre-merge gate ran once against this head through `sdlc-verify-steering.mjs`. Coverage is complete (11 declared, 11 recorded). All 9 applicable required validations passed. The 2 validations whose paths the change does not touch were skipped as not applicable. The deterministic ceiling is none.

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 5 |
| Testability | 4 |
| Error Handling | 4 |
| **Overall** | 4.7 |

### Implementation Status: Pass
**Total Issues**: 4 (all `info`; none blocking)

---

## Issue Scope

- Active issue: #254
- Spec: `specs/254-version-each-game-build-in-ship-show-the-version-in-game-and-require-a-player-changelog-entry`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1-AC6]; FR [FR1-FR6]; tasks [T001-T007]; scenarios [SCN001-SCN006]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":254,"specPath":"specs/254-version-each-game-build-in-ship-show-the-version-in-game-and-require-a-player-changelog-entry","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6"],"tasks":["T001","T002","T003","T004","T005","T006","T007"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact

- Artifact: `.nmg-sdlc/verification/254.json`
- Identity: head `9022cd4c4d95ae9dd060241c5122f2641b64b066`, tree clean, steering `sha256:655dd303…37ee3`, spec `sha256:34cd5ca7…3e3093`
- Coverage: declared 11, recorded 11, complete true; missing, duplicate and unknown are all empty
- Ceiling: none

---

## Acceptance Criteria Verification

The evidence below comes from the review record `.nmg-sdlc/verification/254-review.json`. Every criterion's tests drive the real entry point. No criterion's tests mock the path under test.

| AC | Description | Status | Exercised | Evidence |
|----|-------------|--------|-----------|----------|
| AC1 | `/ship` sets the version | Pass | real entry point | `src/nmg_game_dev/ship/version.py` plan/write_version; `runner.py` `_apply_version` runs after every gate and before export; `tests/unit/ship/test_runner.py::test_bump_minor_writes_the_version_to_the_project_and_every_preset` |
| AC2 | The version must increase | Pass | real entry point | `version.py` resolve_version raises `version_invalid`, `version_not_increased` and `version_missing` before any Godot command; `test_a_refused_version_stops_before_any_godot_command_or_write` |
| AC3 | A changelog entry is required | Pass | real entry point | `src/nmg_game_dev/ship/changelog.py` section match; `ship.changelog_missing` before any Godot or security command; `test_a_missing_changelog_section_stops_before_any_godot_or_tool` |
| AC4 | Release notes carry the version, changes, and gate results | Pass | real entry point | `release_notes.py` heading, Changes, Gates and Artifacts sections; `test_release_notes_carry_the_version_changes_and_gate_results`; BDD SCN004 |
| AC5 | The game shows its version | Pass | real entry point | `nmg_build.gd`, `nmg_version_label.gd`; `tests/test_nmg_build.gd` passes in headless Godot (`gate-godot-headless` passed) |
| AC6 | Dry run changes nothing | Pass | real entry point | `_apply_version` dry-run branch; `test_a_dry_run_records_the_version_and_changelog_lines_in_each_dry_run_file`; BDD SCN006; `gate-ship-smoke` passed |

FR1-FR6 and design paths DP1-DP8 all passed review. The review found 8 consumers (CN1-CN8), all of which pass.

---

## Task Completion

| Task | Description | Status |
|------|-------------|--------|
| T001 | Resolve and write the build version | Complete |
| T002 | Find the changelog section | Complete |
| T003 | Wire versioning, the changelog gate, and gate results into /ship | Complete |
| T004 | Add NmgBuild and NmgVersionLabel to the add-on | Complete |
| T005 | Python tests for versioning, the changelog gate, release notes, and dry run | Complete |
| T006 | BDD scenarios | Complete |
| T007 | Document the release flow | Complete |

---

## Architecture Assessment

| Area | Score (1-5) | Notes |
|------|-------------|-------|
| SOLID | 5 | The new version, changelog and release-notes modules each own one concern, and the runner composes them |
| Security | 5 | No credentials are touched. Version and changelog gates run before signing and before any security tool |
| Performance | 5 | The change adds only small file reads and writes; the runtime add-on adds one ProjectSettings read in `_ready` and no per-frame hook |
| Testability | 4 | Unit, runner and BDD tests drive the real flow with a fake Godot. The add-on tests run in real headless Godot. Info F3: those tests are not listed in `required_tests` |
| Error Handling | 4 | Structured `ship.*` codes with remediation. Each file is written atomically (temp file, then `os.replace`), with the presets before the project. Info F1 and F2 cover message wording and a crash between the two writes |

Layer separation follows `project-structure.md`: the skill calls `python -m nmg_game_dev.ship`, ship logic stays in `src/nmg_game_dev/ship/`, and the runtime classes live in the Godot add-on.

---

## Test Results (pre-merge tier)

The project declares no tiers. Every result records `tier: null` and `selection: null`.

| Gate | Status | Tier | Selection | Evidence |
|------|--------|------|-----------|----------|
| repository.tests | Pass | null | null | `uv run pytest tests/unit tests/bdd -q` exited 0 |
| repository.lint | Pass | null | null | `uv run ruff check .` exited 0 |
| repository.format | Pass | null | null | `uv run ruff format --check .` exited 0 |
| repository.types | Pass | null | null | `uv run mypy src tests` exited 0 |
| gate-blender-headless | Pass | null | null | `scripts/run-blender-tests.sh` exited 0 |
| gate-godot-headless | Pass | null | null | `scripts/run-godot-tests.sh` exited 0 |
| gate-mcp-schema | Not applicable | null | null | The change touches no `mcp-servers/**` path |
| gate-shellcheck | Not applicable | null | null | The change touches no `scripts/**.sh` path |
| gate-ship-smoke | Pass | null | null | `scripts/ship-smoke.sh` exited 0 (dry-run `/ship all` on the fixture, which now has version 1.0.0 and a `## 1.0.0` changelog section) |
| plugin.validate | Pass | null | null | `claude plugin validate .` exited 0 |
| plugin.session-smoke | Pass | null | null | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 9/9 applicable passed, 0 failed, 0 incomplete (2 not applicable)

### Smoke lifecycle evidence

The project registers no `repository.nmg-sdlc-smoke` validation. The registered plugin session smoke (`plugin.session-smoke`) passed against this head.

---

## Fixes Applied

None in this phase. The gate phase makes no source changes. An earlier review cycle repaired F1 (the remediation for an equal version), and this review confirmed the repair.

## Remaining Issues

These are `info` notes only, and none blocks merge:

- **F1** (info, Error Handling, `src/nmg_game_dev/ship/version.py`): when the requested version equals the current one, the remediation assumes an interrupted earlier ship. If that version already shipped, it could steer toward re-shipping the same version.
- **F2** (info, Error Handling, `src/nmg_game_dev/ship/version.py`): if the process crashes between the preset write and the project write, a rerun with the same `--bump` increments the Android version code a second time. This is harmless because codes only need to increase.
- **F3** (info, Testing, `scripts/run-godot-tests.sh`): the `test_nmg_build.gd` tests still run and gate, but they are not in `required_tests`, so the gate would not notice if they were deleted.
- **F4** (info, Docs, `docs/skills/ship.md`): the dry-run paragraph suggests the changelog line is recorded only with a flag, but it is recorded without one too.

---

## Recommendation

**Ready for PR.** Coverage is complete, every applicable required validation passed at head `9022cd4c4d95ae9dd060241c5122f2641b64b066`, and only `info` notes remain.
