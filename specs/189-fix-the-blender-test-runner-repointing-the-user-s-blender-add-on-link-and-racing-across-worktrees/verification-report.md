# Verification Report: The Blender test runner repoints the user's Blender add-on link and races across worktrees

**Date**: 2026-11-11
**Issue**: #189
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Implementation verification against the approved defect spec
**Verification head**: 1418c1be42110d767090213b4b0f6dd4c72fdb55

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 5 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.8 |

### Implementation Status: Pass
**Total Issues**: 2 (both Low, non-blocking)

`scripts/run-blender-tests.sh` now gives every run a fresh `mktemp -d` directory, exports it as `BLENDER_USER_SCRIPTS` (overriding any inherited value), removes it on exit through an `EXIT` trap, and passes Blender's exit status through. `tests/blender/_runner.py` links the add-on only inside that directory and raises `RuntimeError` before any write when the variable is unset or Blender's addons path resolves outside it. All four ACs, three FRs, five tasks and four scenarios are met. All 10 applicable registered gates passed at the verification head.

---

## Issue Scope

- Active issue: #189
- Spec: `specs/189-fix-the-blender-test-runner-repointing-the-user-s-blender-add-on-link-and-racing-across-worktrees`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4]; FR [FR1, FR2, FR3]; tasks [T001, T002, T003, T004, T005]; scenarios [SCN001, SCN002, SCN003, SCN004]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":189,"specPath":"specs/189-fix-the-blender-test-runner-repointing-the-user-s-blender-add-on-link-and-racing-across-worktrees","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4"],"functionalRequirements":["FR1","FR2","FR3"],"tasks":["T001","T002","T003","T004","T005"],"scenarios":["SCN001","SCN002","SCN003","SCN004"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 189 --base main --controller-run-id fdbe8a3d-d203-4fb3-84eb-34a2ba2d064b`
- Artifact: `.nmg-sdlc/verification/189.json`. Identity: head `1418c1be42110d767090213b4b0f6dd4c72fdb55`, steering `sha256:119992c8…`, spec `sha256:7cdb160b…`
- Ceiling: none (`ok: true`)
- Coverage: declared 11, recorded 11, complete `true`, with no missing, duplicate or unknown ids

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Test runs do not touch the user's Blender scripts directory | Pass | `scripts/run-blender-tests.sh` runs Blender with `BLENDER_USER_SCRIPTS="${user_scripts}"`, a per-run `mktemp -d` directory. `tests/blender/_runner.py` `_isolated_addons_dir()` refuses an unset variable or an addons path outside it. `test_gate_runs_blender_with_a_per_run_user_scripts_directory_not_the_callers` shows that the caller's stand-in scripts tree is byte-identical after a run. The `test_blender_runner_isolation.py` refusal tests show nothing is written outside. In a live check, the user's real `~/Library/Application Support/Blender/*/scripts/addons/nmg_game_dev_blender_addon` links were unchanged across a real headless gate run |
| AC2 | Each run uses its own add-on location | Pass | `test_concurrent_gate_runs_each_use_their_own_user_scripts_directory`: two overlapping runs (rendezvous-confirmed `overlapped`) saw distinct directories. `test_a_real_gate_run_loads_the_add_on_from_its_own_location_and_checkout` (real Blender 5.2, run here with `BLENDER_APP`): `user_resource("SCRIPTS")` resolves to the run directory, the link resolves to this checkout's `plugins/nmg-game-dev-blender-addon`, and the enabled module's `__file__` is inside this checkout |
| AC3 | The isolated location is cleaned up | Pass | `trap 'rm -rf "${user_scripts}"' EXIT`. `test_gate_removes_its_user_scripts_directory_and_exits_with_blenders_status[0/3]`: the directory existed while Blender ran and is gone afterwards, for both passing and failing runs. After the real-Blender runs, no `nmg-blender-user-scripts.*` directories remained under `$TMPDIR` |
| AC4 | Existing Blender tests still pass | Pass | `gate-blender-headless` passed: `209 passed, 4 skipped` through the isolated gate |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | Per-run `mktemp -d`, `BLENDER_USER_SCRIPTS` override, EXIT-trap removal, `status=0 … || status=$?; exit "${status}"`. The Blender argv is unchanged, and the existing argv tests still pass |
| FR2 | Pass | `_isolated_addons_dir()` checks the variable, then checks `addons_dir.is_relative_to(root)` on resolved paths before `mkdir`. `user_resource` is called without `create=True`, which a fake-`bpy` test asserts |
| FR3 | Pass | The fake-`bpy` guard tests and the real headless-Blender test both show the link resolves under the per-run location |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Per-run temporary user scripts location | Complete | It also pre-creates `addons/` before launch so Blender adds it to `sys.path` at startup. `gate-shellcheck` passed |
| T002 | Runner links only inside the per-run location | Complete | `_isolated_addons_dir()` and `_install_addon_link()`. `main()` also calls `bpy.utils.refresh_script_paths()` after linking |
| T003 | Gate-script isolation and cleanup tests | Complete | Shim tests for the caller directory, concurrency, and pass/fail cleanup, plus the real-Blender isolation test |
| T004 | Fake-bpy runner guard tests | Complete | `tests/unit/test_blender_runner_isolation.py`: 4 tests |
| T005 | Existing Blender suite passes through the isolated gate | Complete | `gate-blender-headless`: 209 passed, 4 skipped. No `tests/blender` test changes were needed |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | The shell script owns lifecycle (create, export, cleanup, exit status). `_isolated_addons_dir()` owns the guard. `_install_addon_link()` keeps its idempotent link logic |
| Open/Closed | 5 | The Blender argv and the runner's pytest flow are unchanged. Isolation is layered on |
| Liskov Substitution | 5 | N/A (no type hierarchy). The fake `bpy` honours the real `user_resource` signature |
| Interface Segregation | 5 | The runner depends only on `bpy.utils.user_resource` and `refresh_script_paths` |
| Dependency Inversion | 5 | The runner reads its location from the environment contract the gate sets, not from a hard-coded path |

### Layer Separation

The change stays inside test tooling (`scripts/` gate backer and the `tests/blender` runner). No shipped add-on, pipeline or plugin code is touched.

### Dependency Flow

The gate script sets the contract (`BLENDER_USER_SCRIPTS`), and the runner enforces it. Running the runner directly fails closed with an actionable message that names `scripts/run-blender-tests.sh`.

---

## Security Assessment

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: the addons path is resolved (`Path.resolve()`) on both sides before `is_relative_to`, so symlinked or `..` paths cannot escape. A sibling-prefix directory (`run-scripts-sibling`) is rejected, which a test covers
- [x] Injection prevention: all shell expansions are quoted, and `mktemp -d` gives an unpredictable, private (0700) directory
- [x] Data protection: `rm -rf` on the temp directory removes the add-on symlink without following it, so the checkout's add-on source is never deleted. The user's real scripts directory is no longer written at all

## Performance Assessment

- [x] Async patterns: N/A
- [x] Caching: N/A
- [x] Resource management: one small temp directory per run, removed on exit, with no leak seen after real runs
- [x] Query optimization: N/A. Gate runtime is unchanged (headless suite 197.6 s)

## Testability

Strong. The shim `BLENDER_BIN` tests cover the shell lifecycle without Blender, including a rendezvous that proves the two runs actually overlap. The fake-`bpy` tests cover the guard. A `needs_blender` test proves the real Blender 5.2 behaviour end to end.

## Error Handling

Both refusal paths raise `RuntimeError` with remediation, and nothing is written first. The exit status is preserved for pass, fail and error. Two Low findings are listed under Remaining Issues.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps / Test | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | SCN001 | `test_gate_runs_blender_with_a_per_run_user_scripts_directory_not_the_callers`; `test_the_runner_refuses_*` | Yes |
| AC2 | SCN002 | `test_concurrent_gate_runs_each_use_their_own_user_scripts_directory`; `test_a_real_gate_run_loads_the_add_on_from_its_own_location_and_checkout` | Yes |
| AC3 | SCN003 | `test_gate_removes_its_user_scripts_directory_and_exits_with_blenders_status[0,3]` | Yes |
| AC4 | SCN004 | `gate-blender-headless` (full `tests/blender` suite) | Yes |

### Coverage Summary

- Feature file: `feature.gherkin` with 4 scenarios, mapped to pytest tests and the gate as declared in its header
- Targeted run, with real Blender via `BLENDER_APP`: `uv run pytest tests/unit/test_run_blender_tests.py tests/unit/test_blender_runner_isolation.py -v` gave 14 passed, 0 skipped
- `repository.tests`: 1062 passed, 10 skipped
- `gate-blender-headless`: 209 passed, 4 skipped

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. No nmg-sdlc plugin `workflows/` or `agents/` paths changed. `plugin.validate` and `plugin.session-smoke` still ran and passed as registered gates |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `1062 passed, 10 skipped` in 101.86 s |
| `repository.lint` | Pass | `uv run ruff check .` exited 0 |
| `repository.format` | Pass | `uv run ruff format --check .` exited 0 |
| `repository.types` | Pass | `uv run mypy src tests` exited 0 |
| `gate-blender-headless` | Pass | `209 passed, 4 skipped` in 197.61 s through the isolated gate |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against `/Users/Shared/Epic Games/UE_5.8` |
| `gate-mcp-schema` | Pass | Exited 0 |
| `gate-shellcheck` | Pass | Exited 0, including `scripts/run-blender-tests.sh` |
| `gate-ship-smoke` | Not applicable | No ship paths in scope |
| `plugin.validate` | Pass | `claude plugin validate .` exited 0 |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | No fixes were needed | — | — |

## Remaining Issues

### Critical Issues
None.

### High Priority
None.

### Medium Priority
None.

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling / Documentation |
| **Location** | `tests/blender/_runner.py` `main()` comment before `bpy.utils.refresh_script_paths()` |
| **Issue** | The comment says the per-run directory "is created after startup", but `scripts/run-blender-tests.sh` now pre-creates `${user_scripts}/addons` before launch. The refresh is still correct as a safeguard (for example, when `BLENDER_USER_SCRIPTS` is set by hand to a directory without `addons/`) |
| **Impact** | Slightly misleading comment only. Behaviour is correct |
| **Reason Not Fixed** | The verify publication scope allows only `verification-report.md`. This is cosmetic and does not justify a source change |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Resource management |
| **Location** | `scripts/run-blender-tests.sh` EXIT trap |
| **Issue** | A `SIGKILL` of the gate shell skips the EXIT trap and leaves one empty-ish temp directory under `$TMPDIR` |
| **Impact** | Negligible. The directory is private, holds only a symlink, and the OS temp cleaner removes it. It is never shared with another run |
| **Reason Not Fixed** | This is inherent to signal semantics and outside the spec |

---

## Positive Observations

- Fail-closed guard: the runner can no longer write to the user's real Blender scripts directory, even when run by hand.
- `rm -rf` does not follow the add-on symlink, and the design calls this out explicitly.
- The concurrency test proves the two runs actually overlap (rendezvous), not just that they ran one after the other.
- The real-Blender test checks Blender 5.2's actual `BLENDER_USER_SCRIPTS` resolution and the module's import origin, not just the link target.

---

## Recommendations Summary

### Before PR (Must)
- None

### Short Term (Should)
- None

### Long Term (Could)
- [ ] Reword the `_runner.py` refresh comment to "may not exist at startup"

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `scripts/run-blender-tests.sh` | 1 (Low) | Per-run isolation, cleanup, status pass-through |
| `tests/blender/_runner.py` | 1 (Low) | Guard and isolated link; comment wording |
| `tests/unit/test_run_blender_tests.py` | 0 | Shim, concurrency, cleanup and real-Blender tests |
| `tests/unit/test_blender_runner_isolation.py` | 0 | Fake-bpy guard tests |
| `CHANGELOG.md`, `VERSION`, plugin manifests | 0 | 0.21.4 version preparation |

---

## Recommendation

**Ready for PR**

Every AC, FR, task and scenario is met with direct evidence, including a real headless Blender 5.2 run. All applicable registered gates passed at `1418c1be42110d767090213b4b0f6dd4c72fdb55`. The two Low findings are non-blocking.
