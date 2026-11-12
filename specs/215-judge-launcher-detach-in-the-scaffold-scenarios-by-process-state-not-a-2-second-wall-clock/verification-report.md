# Verification Report: Judge launcher detach in the scaffold scenarios by process state, not a 2-second wall clock

**Date**: 2026-11-12
**Issue**: #215
**Reviewer**: Claude (architecture-reviewer, nmg-sdlc verify worker)
**Scope**: Implementation verification against spec

**Verification head**: 9552bd37ded6ac8bb84bf0326aab8abfc08a5459

---

## Executive Summary

The fix replaces the `< 2.0 s` wall-clock assertion in the scaffold launcher scenarios with a structural detach check: the launcher must exit 0 while the long-lived fake child it started is still alive. The fakes now record their argv and PID and stay alive until a stop file appears; a fixture stops them at teardown. Three new scenarios show that a launcher that waits for its child fails the check, a launcher that hangs fails it, and a slow launcher that detaches passes it. This is a re-verification after deliver's base reconciliation merged `origin/main` (1293c00, bringing in #217, #218 and #219) into the branch as 9552bd3. The merge touched none of #215's files beyond the auto-merged `CHANGELOG.md`, so the diagnosis is a stale gate identity, not a defect; the repair is a fresh run of the full registered gate at the new head. Every applicable registered gate passed again at 9552bd37ded6ac8bb84bf0326aab8abfc08a5459, and coverage is complete.

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
**Total Issues**: 3 (all Low, not blocking)

---

## Issue Scope

- Active issue: #215
- Spec: `specs/215-judge-launcher-detach-in-the-scaffold-scenarios-by-process-state-not-a-2-second-wall-clock`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3]; FR [FR1, FR2, FR3]; tasks [T001, T002, T003]; scenarios [SCN001, SCN002, SCN003]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":215,"specPath":"specs/215-judge-launcher-detach-in-the-scaffold-scenarios-by-process-state-not-a-2-second-wall-clock","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3"],"functionalRequirements":["FR1","FR2","FR3"],"tasks":["T001","T002","T003"],"scenarios":["SCN001","SCN002","SCN003"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 215 --spec specs/215-… --base main --controller-run-id dbcc29f2-4c09-480d-9d69-e0106d371257`
- Artifact: `.nmg-sdlc/verification/215.json`, `ok: true`, `ceiling: null`
- Identity: head `9552bd37ded6ac8bb84bf0326aab8abfc08a5459`, tree clean, steering `sha256:6db9aabc…d4`, spec `sha256:510c90d8…be`
- Coverage: declared 11, recorded 11, complete `true`; missing / duplicate / unknown all empty
- Base ref: `main`. The local `main` ref (41c5b31) is behind `origin/main` (1293c00, the merge base of this branch) and is checked out in another worktree, so this run compares against more paths than the branch changes against `origin/main`. Because of that, more gates applied (Blender headless, UE compile, MCP schema, shellcheck, plugin validation, session smoke), and every one of them passed. The verdict does not change.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Detach is judged structurally: pass only if the script exited 0 while the fake child is alive, and the argv still matches | Pass | `tests/bdd/steps/test_scaffold.py` `assert_detached` (timeout → non-zero exit → PID recorded and `os.kill(pid, 0)` alive); `blender_detached`, `script_exits_while_child_runs`, `ue_editor_detached` call it; UE argv still asserts `-ModelContextProtocolStartServer` and `-ModelContextProtocolPort=18088`, and Blender argv now asserts `--python-expr` + `start_server`. `test_blender_launcher_detaches`, `test_unreal_launcher_detaches` PASSED |
| AC2 | A blocking launcher still fails | Pass | `blocking_launcher` (`"$FAKE_CHILD_BIN" &` + `wait`); `detach_fails_child_gone` expects `PID \d+ is gone` with a 1 s child lifetime; `detach_fails_launcher_hung` expects `did not return within 3 s` with a 3 s bound. `test_blocking_launcher_fails_when_child_exits`, `test_blocking_launcher_fails_when_it_hangs` PASSED |
| AC3 | Host load does not fail the scenarios | Pass | `slow_launcher` sleeps 2.5 s, then runs `nohup … & disown; exit 0`; `detach_passes_child_running` passes `assert_detached`; `slow_launcher_finished_delay` checks a marker the launcher touches after its 2.5 s sleep. No wall-clock threshold remains in `test_scaffold.py`. `test_slow_launcher_passes_when_detached` PASSED |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `LauncherRun` has no `elapsed_seconds`; `_run_launcher(script, env, timeout=30)` takes a name or a `Path` and reports `TimeoutExpired` as `timed_out=True` |
| FR2 | Pass | `_FAKE_CHILD_BODY` writes argv and `$$`, then loops until the stop file appears, `FAKE_CHILD_LIFETIME` elapses, or 120 s pass; the `fake_child` fixture touches the stop file and sends SIGTERM to a recorded live PID |
| FR3 | Pass | The two AC2 scenarios assert that `assert_detached` raises for a blocking launcher |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Long-lived fake children that record their PID and are stopped afterwards | Complete | `fake_child` fixture is shared by `fake_blender_bin` and `fake_ue_root` |
| T002 | Replace the wall-clock assertion with a structural detach check | Complete | Step text replaced in both detach scenarios; idempotency keeps `timeout=5` and still passes |
| T003 | Scenarios for blocking, hanging, and slow-but-detached launchers | Complete | Three scenarios added; the "more than 2 s" check uses a marker written after the 2.5 s sleep rather than a timer (see Remaining Issues) |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Each helper does one thing: run (`_run_launcher`), write fakes (`_write_fake_child`, `_write_launcher`), read/wait for the PID, check liveness, judge detach |
| Open/Closed | 5 | `_run_launcher` accepts any launcher path, so synthetic launchers reuse it without changing it |
| Liskov Substitution | 5 | The fake Blender and fake UE editor use one fake body with the same env contract |
| Interface Segregation | 5 | `FakeChild.env(lifetime)` exposes only the variables the fake reads |
| Dependency Inversion | 5 | Paths and lifetime are passed through environment variables; nothing is hard-coded to a host |

### Layer Separation

The change stays in the BDD test layer (`tests/bdd/`). The launcher scripts are unchanged, which matches the spec's Out of Scope.

### Dependency Flow

The steps depend on fixtures and module helpers only. The only new imports are standard library ones (`contextlib`, `signal`, `collections.abc.Iterator`).

---

## Security Assessment

- [x] Authentication: N/A (test code)
- [x] Authorization: N/A
- [x] Input validation: `_read_pid` accepts only all-digit content
- [x] Injection prevention: `subprocess.run` uses an argv list (`["bash", path]`) with no shell string; launcher bodies are fixed literals
- [x] Data protection: no secrets; all files live under `tmp_path`

---

## Performance Assessment

- [x] Async patterns: state-based polling (`_wait_for_pid`, 50 ms steps, 10 s cap) instead of fixed sleeps
- [x] Caching: N/A
- [x] Resource management: no fake outlives its test; the stop file plus SIGTERM at teardown, and a 120 s self-limit as a backstop; no leftover `fake-child` processes after the run
- [x] Query optimization: N/A

The 7 launcher scenarios run in 8.26 s, most of it the deliberate 2.5 s and 3 s cases.

---

## Testability and Error Handling

- Failure messages name the cause: `did not return within <timeout> s`, `launcher exited <code>: <stderr>`, `no PID recorded in <file>`, `PID <pid> is gone`.
- A timeout is returned as data (`timed_out=True`), not raised, so the detach check can judge it. The idempotency step and the remediation step guard against `result is None`.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 (SCN001) | Yes: start-blender-mcp.sh / start-unreal-mcp.sh detach scenarios | Yes | Yes |
| AC2 (SCN002) | Yes: "waits for its child" + "does not return" | Yes | Yes |
| AC3 (SCN003) | Yes: "slow launcher that detaches" | Yes | Yes |

### Coverage Summary

- Feature file: `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature`. 2 scenarios changed, 3 added.
- Step definitions: implemented in `tests/bdd/steps/test_scaffold.py`
- Targeted run: `uv run pytest tests/bdd/steps/test_scaffold.py -v -k "detach or launcher or idempotent"`: 7 passed
- Full suite: `repository.tests` (`uv run pytest tests/unit tests/bdd -q`) passed at 9552bd3, including the tests merged in from #217, #218 and #219
- No `fake-child` process remained after the gate run

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. The change touches no nmg-sdlc workflow, agent, or skill file; it changes only BDD test code. |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | command exited 0 |
| repository.lint | Pass | command exited 0 |
| repository.format | Pass | command exited 0 |
| repository.types | Pass | command exited 0 |
| gate-blender-headless | Pass | command exited 0 |
| gate-ue-compile | Pass | DogfoodEditor compiled (`project.ue-compile` passed at 9552bd3) |
| gate-mcp-schema | Pass | command exited 0 |
| gate-shellcheck | Pass | command exited 0 |
| gate-ship-smoke | Not applicable | no matching changed paths (recorded as skipped, not applicable) |
| plugin.validate | Pass | command exited 0 |
| plugin.session-smoke | Pass | plugin loaded via --plugin-dir; nmg-game-dev:blender connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable). The manifest does not declare `repository.nmg-sdlc-smoke`.

---

## Fixes Applied

None. No finding needed a code change.

## Remaining Issues

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `tests/bdd/steps/test_scaffold.py` `slow_launcher_finished_delay` |
| **Issue** | T003 asks the AC3 scenario to assert that the run took more than 2 s. The step instead checks for a marker the launcher touches after `sleep 2.5`, which proves the delay ran before the detach without timing it. |
| **Impact** | None. This is equivalent evidence and does not depend on wall-clock time, which is the point of the fix. |
| **Reason Not Fixed** | Intentional and consistent with FR1. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `tests/bdd/steps/test_scaffold.py` `_pid_alive` |
| **Issue** | The "child is gone" check uses `os.kill(pid, 0)`. If the OS reused the dead fake's PID within milliseconds, the check could report it alive. |
| **Impact** | Very unlikely, and it could only cause a false failure of the negative AC2 scenario, never a false pass of AC1. |
| **Reason Not Fixed** | The risk is negligible and the spec's design specifies this check. |

---

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Versioning |
| **Location** | `CHANGELOG.md` |
| **Issue** | After the base merge, `VERSION` and the manifests carry main's 0.24.0, while the #215 entry still sits under its earlier `## [0.23.1]` heading above main's `## [0.24.0]`. |
| **Impact** | None on the ACs. Deliver re-runs prepare-version, which owns the version bump and the CHANGELOG heading. |
| **Reason Not Fixed** | Outside the verify publication scope (only this report is writable); version files belong to deliver. |

## Positive Observations

- The check now tests the property that detach actually guarantees, so host load can no longer fail it.
- Fake processes are reliably cleaned up through the stop file, SIGTERM, and a 120 s self-limit.
- The negative scenarios prove that the check still catches a launcher that waits for its child or never returns.

---

## Recommendations Summary

### Before PR (Must)
- [x] None

### Short Term (Should)
- [ ] None

### Long Term (Could)
- [ ] Keep the local `main` ref in step with `origin/main` so the gate's changed-path set matches the PR diff.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `tests/bdd/steps/test_scaffold.py` | 2 (Low) | Fake children, detach check, new steps |
| `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature` | 0 | Step text replaced; 3 scenarios added |
| `CHANGELOG.md`, `VERSION`, plugin manifests | 1 (Low) | #215 entry sits under a `[0.23.1]` heading while `VERSION` is main's 0.24.0 after the merge |

---

## Recommendation

**Ready for PR**

All three ACs, three FRs and three tasks are met. Every applicable registered gate passed with complete coverage at head 9552bd37ded6ac8bb84bf0326aab8abfc08a5459, after the base reconciliation merge.
