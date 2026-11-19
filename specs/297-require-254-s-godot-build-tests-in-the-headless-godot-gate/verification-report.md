# Verification Report: Require #254's Godot build tests in the headless Godot gate

**Date**: 2026-11-19
**Issue**: #297
**Reviewer**: Claude (nmg-sdlc verify, gate phase)
**Scope**: Implementation verification against spec
**Verification head**: f66a38e359e46f29e6b2bdf4e0ca8088dd2daa99

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
**Total Issues**: 1 (info only)

`scripts/run-godot-tests.sh` now requires the six `test_nmg_build.gd` tests, a guard test fails when a `func test_*` in that file is not listed, and the fake `godot` exercises the exit-5 path for a missing build test. Every pre-merge validation the manifest registers for this change passed at the verification head.

---

## Issue Scope

- Active issue: #297
- Spec: `specs/297-require-254-s-godot-build-tests-in-the-headless-godot-gate`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2]; FR [FR1, FR2, FR3]; tasks [T001, T002, T003]; scenarios [SCN001, SCN002]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":297,"specPath":"specs/297-require-254-s-godot-build-tests-in-the-headless-godot-gate","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2"],"functionalRequirements":["FR1","FR2","FR3"],"tasks":["T001","T002","T003"],"scenarios":["SCN001","SCN002"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

## Deterministic Steering Artifact

- Artifact: `.nmg-sdlc/verification/297.json` (tier `pre-merge`; no tiers declared, so every applicable required validation ran)
- Ceiling: none
- Coverage: declared 11, recorded 11, complete; no missing, duplicate or unknown results

---

## Acceptance Criteria Verification

| AC | Description | Status | Exercised | Evidence |
|----|-------------|--------|-----------|----------|
| AC1 | `required_tests` lists every `test_nmg_build.gd` test | Pass | real entry point | `scripts/run-godot-tests.sh:75-80` lists the six `test_nmg_build.gd::test_version_*` entries, matching the six `func test_*` in `test_nmg_build.gd`; `test_required_tests_list_every_build_test` and BDD SCN001 parse both real files; `gate-godot-headless` passed with the real Godot add-on run |
| AC2 | A missing required test fails the gate with exit 5 | Pass | mocked | The real script runs under a fake `godot` in `tests_missing_build` mode; `test_a_missing_build_test_exits_5_and_names_it`, the parametrized `test_addon_test_failure_exits_5` case and BDD SCN002 assert exit 5 and the named test in stderr. The Godot engine is faked; the gate's own headless Godot run covers the real engine |

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `scripts/run-godot-tests.sh:20-22` header names the NmgBuild version tests; `required_tests` holds the six entries; shellcheck clean |
| FR2 | Pass | `tests/unit/test_run_godot_tests.py::test_required_tests_list_every_build_test` and BDD SCN001 |
| FR3 | Pass | Fake `godot` in `tests/unit/test_run_godot_tests.py` prints the six build PASS lines; `tests_missing_build` mode omits one |

Criteria whose tests mock the path under test: **AC2** (fake `godot` on `PATH`).

---

## Task Completion

| Task | Description | Status |
|------|-------------|--------|
| T001 | Require the build tests in the gate | Complete |
| T002 | Teach the fake godot the build tests and add the guards | Complete |
| T003 | BDD scenarios for the required build tests | Complete |

---

## Architecture Assessment

| Area | Score (1-5) | Notes |
|------|-------------|-------|
| SOLID | 5 | Data-only change to an existing list; guard tests parse the real files |
| Security | 5 | No new inputs, credentials or network use |
| Performance | 5 | Six extra `grep -qxF` checks over an in-memory log |
| Testability | 5 | Guard fails on rename or deletion; exit-5 path exercised end to end through the script |
| Error Handling | 5 | Unchanged exit-5 path, now covering the build tests |

### Findings

- **F1** (info): the `gate-godot-headless` row in `steering/snippets/project-tech.md` says `run_tests.gd` runs "(requiring the variant-routing tests to pass)". That already understated the required set before #297 and now also leaves out the NmgBuild tests. It predates this change and the spec doesn't cover it.

---

## Test Results (Steering Verification Gates)

| Validation | Tier | Selection | Status | Evidence |
|------------|------|-----------|--------|----------|
| repository.tests | — | — | Pass | `uv run pytest tests/unit tests/bdd -q` exited 0 |
| repository.lint | — | — | Pass | `uv run ruff check .` exited 0 |
| repository.format | — | — | Pass | `uv run ruff format --check .` exited 0 |
| repository.types | — | — | Pass | `uv run mypy src tests` exited 0 |
| gate-blender-headless | — | — | Pass | `scripts/run-blender-tests.sh` exited 0 (applies through the version bump of `blender_manifest.toml`) |
| gate-godot-headless | — | — | Pass | `scripts/run-godot-tests.sh` exited 0 against real headless Godot |
| gate-mcp-schema | — | — | Not applicable | No `mcp-servers/**` change |
| gate-shellcheck | — | — | Pass | `shellcheck -S style` exited 0 |
| gate-ship-smoke | — | — | Not applicable | No ship or `tests/godot/**` change |
| plugin.validate | — | — | Pass | `claude plugin validate .` exited 0 |
| plugin.session-smoke | — | — | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 9/9 applicable passed, 0 failed, 0 incomplete; 2 not applicable.

No `nmg-sdlc-smoke` validation is registered in this project.

---

## Fixes Applied

None. This is the gate phase, and the review passed with no finding above `info`.

## Remaining Issues

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| info | Documentation | `steering/snippets/project-tech.md` | Gate row understates `run_tests.gd`'s required set | Predates this change and isn't in the spec's scope |

## Recommendation

Ready for PR.
