# Verification Report: Restore the two-second return bound in the launcher detach scenarios

**Date**: 2026-11-12
**Issue**: #226
**Reviewer**: Claude (nmg-sdlc architecture-reviewer)
**Scope**: Implementation verification against spec

**Verification head**: 62e8d077d83fcfc69bc770734c435e9fa1ca9d60

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

The detach check in `tests/bdd/steps/test_scaffold.py` again requires a launcher to return in under 2.0 s. `LauncherRun.elapsed_seconds` is measured with `time.monotonic()` around the launcher run, including runs that time out. `assert_detached` keeps its timeout, exit-code, and child-PID checks in the same order, then rejects a run when `elapsed_seconds >= DETACH_RETURN_LIMIT_SECONDS` (2.0). The scenario that let a 2.5 s launcher pass is now one that requires it to fail. All 11 registered validations are recorded at the verification head. The 8 that apply passed; the other 3 don't apply to this change.

---

## Issue Scope

- Active issue: #226
- Spec: `specs/226-restore-the-two-second-return-bound-in-the-launcher-detach-scenarios`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3]; FR [FR1, FR2, FR3]; tasks [T001, T002]; scenarios [SCN001, SCN002, SCN003]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":226,"specPath":"specs/226-restore-the-two-second-return-bound-in-the-launcher-detach-scenarios","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3"],"functionalRequirements":["FR1","FR2","FR3"],"tasks":["T001","T002"],"scenarios":["SCN001","SCN002","SCN003"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact

- Runner: `sdlc-verify-steering.mjs --base main` → `.nmg-sdlc/verification/226.json`
- Identity: head `62e8d077d83fcfc69bc770734c435e9fa1ca9d60`, tree `clean`, spec hash `sha256:09be35e1…`, steering hash `sha256:6db9aabc…`
- Ceiling: none
- Coverage: declared 11, recorded 11, complete `true`, no missing, duplicate, or unknown results

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | The Blender and Unreal launcher detach scenarios pass only when the script exits 0 in under 2 s with the fake child alive | Pass | `tests/bdd/steps/test_scaffold.py:162-166` (elapsed check in `assert_detached`); the step "the script returns control to the shell in under two seconds" is added to both detach scenarios (`tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature:44,53`); `test_blender_launcher_detaches` (0.35 s) and `test_unreal_launcher_detaches` (0.36 s) pass |
| AC2 | A 2.5 s synthetic launcher fails the detach check although its child is alive | Pass | Scenario "A slow launcher fails the detach check (AC2)" (feature:67-71); `detach_fails_launcher_too_slow` asserts `AssertionError` matching `took \d+\.\d+ s to return \(limit 2\.0 s\)`; the marker step proves the 2.5 s delay ran; `test_slow_launcher_fails_detach_check` passes (2.77 s) |
| AC3 | Blocking launchers still fail (the child is gone, or the launcher does not return) | Pass | Scenarios at feature:57-65 are unchanged; their steps still match `PID \d+ is gone` (steps:542) and `did not return within 3 s` (steps:548); `test_blocking_launcher_fails_when_child_exits` and `test_blocking_launcher_fails_when_it_hangs` pass |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `DETACH_RETURN_LIMIT_SECONDS = 2.0`; `elapsed_seconds` is measured on both the success and timeout paths of `_run_launcher`; both detach scenarios carry the new step |
| FR2 | Pass | The old scenario and `detach_passes_child_running` are removed; `test_slow_launcher_fails_detach_check` binds the replacement scenario |
| FR3 | Pass | `git diff main...HEAD` doesn't touch `_FAKE_CHILD_BODY`, the `fake_child` fixture, or its teardown |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Restore the two-second bound in the detach check | Complete | The checks run in the specified order; the failure message format matches the spec |
| T002 | Prove slow and blocking launchers fail the detach check | Complete | `uv run pytest tests/bdd -q -k "launcher or detach"`: 7 passed |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | `_run_launcher` measures; `assert_detached` judges |
| Open/Closed | 5 | The limit is a named module constant |
| Liskov Substitution | 5 | N/A (no inheritance) |
| Interface Segregation | 5 | `LauncherRun` gains one field |
| Dependency Inversion | 5 | Test-only change; no production dependencies |

### Layer Separation

The change is limited to the BDD test harness. `scripts/start-blender-mcp.sh` and `scripts/start-unreal-mcp.sh` are unchanged, as the spec's Out of Scope requires.

### Dependency Flow

There are no new imports beyond the existing `time` module.

---

## Security Assessment

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: N/A (test harness only)
- [x] Injection prevention: subprocess runs use argv lists, not a shell string
- [x] Data protection: no secrets touched

---

## Performance Assessment

- [x] Async patterns: N/A
- [x] Caching: N/A
- [x] Resource management: the fake-child teardown is unchanged, so no processes leak
- [x] Query optimization: N/A
- Test runtime is unchanged. The slow-launcher scenario still takes about 2.8 s, and the real launchers return in about 0.35 s, well inside the 2.0 s bound.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes | Yes | Yes |
| AC2 | Yes | Yes | Yes |
| AC3 | Yes | Yes | Yes |

### Coverage Summary

- Launcher scenarios: 7 selected, 7 passed (`uv run pytest tests/bdd -q -k "launcher or detach"`)
- Full suite: `repository.tests` (`uv run pytest tests/unit tests/bdd -q`) passed at the verification head
- Step definitions: Implemented

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. The change touches no nmg-sdlc `workflows/` or `agents/` paths, and no shipped skill, agent, or plugin manifest behavior. `plugin.validate` and `plugin.session-smoke` passed because the version bump touched `.claude-plugin/plugin.json`. |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | command exited 0 |
| `repository.lint` | Pass | command exited 0 |
| `repository.format` | Pass | command exited 0 |
| `repository.types` | Pass | command exited 0 |
| `gate-blender-headless` | Pass | command exited 0 |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against UE 5.8 |
| `gate-mcp-schema` | Not applicable | no matching changed paths |
| `gate-shellcheck` | Not applicable | no matching changed paths |
| `gate-ship-smoke` | Not applicable | no matching changed paths |
| `plugin.validate` | Pass | command exited 0 |
| `plugin.session-smoke` | Pass | plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 8/8 applicable gates passed, 0 failed, 0 incomplete (3 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None required | — | — |

## Remaining Issues

None.

### Low Priority (observation, no action)

The new step "the script returns control to the shell in under two seconds" calls the full `assert_detached`, so it repeats the exit and child-alive checks of the step before it. That matches the spec, which says each step must pass on its own, and it costs nothing.

---

## Positive Observations

- `elapsed_seconds` is recorded on the timeout path too, so `LauncherRun` is always fully populated.
- The failure message carries the measured time and the limit, which makes triage copy-paste.
- The bound check runs after the PID check, so the blocking-launcher scenarios keep their original failure reasons.

---

## Recommendations Summary

### Before PR (Must)
- None

### Short Term (Should)
- None

### Long Term (Could)
- None

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `tests/bdd/steps/test_scaffold.py` | 0 | elapsed timing, bound check, step bindings |
| `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature` | 0 | new step on both detach scenarios; scenario replaced |
| `CHANGELOG.md`, `VERSION`, manifests | 0 | 0.25.2 patch bump, consistent across all mapped files |

---

## Recommendation

**Ready for PR**

All three acceptance criteria and all three functional requirements are implemented and pass their tests. Every applicable registered gate passed at head `62e8d077d83fcfc69bc770734c435e9fa1ca9d60`.
