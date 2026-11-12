# Root Cause Analysis: The launcher detach scenarios no longer enforce the two-second return bound

**Issue**: #226
**Date**: 2026-11-12
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/215-judge-launcher-detach-in-the-scaffold-scenarios-by-process-state-not-a-2-second-wall-clock/

## Root Cause

#215 removed `elapsed_seconds` from `LauncherRun` in `tests/bdd/steps/test_scaffold.py`, along with the step `the script returns control to the shell in under two seconds` that asserted `elapsed_seconds < 2.0`. Now `assert_detached(run, pid_file)` checks only three things: the run did not time out (30 s default), the exit code is 0, and the recorded child PID is alive. It also added `slow_launcher` and `detach_passes_child_running`, which assert that a launcher sleeping 2.5 s passes. That assertion makes a slow return a passing result. Nothing in the suite measures how long a launcher takes to return control to the shell.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `tests/bdd/steps/test_scaffold.py` | `LauncherRun`, `_run_launcher` | No elapsed time is recorded |
| `tests/bdd/steps/test_scaffold.py` | `assert_detached` | No time bound |
| `tests/bdd/steps/test_scaffold.py` | `test_slow_launcher_passes_when_detached`, `detach_passes_child_running` | Assert that a 2.5 s launcher passes |
| `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature` | The two detach scenarios and "A slow launcher that detaches still passes the detach check (AC3)" | The step text omits the bound, and the slow scenario expects a pass |

## Fix Strategy

1. **Record elapsed time.** Add `elapsed_seconds: float` back to `LauncherRun`. `_run_launcher` measures `time.monotonic()` around `subprocess.run`. A timed-out run records the bound it hit. `result`, `timed_out`, and `timeout` keep their current meaning.
2. **Bound the detach check.** Add a module constant `DETACH_RETURN_LIMIT_SECONDS = 2.0`. `assert_detached(run, pid_file)` keeps its current checks in their current order: timeout, non-zero exit, no recorded PID, dead PID. Then it adds a final check that fails with `launcher took {elapsed:.2f} s to return (limit 2.0 s)` when `run.elapsed_seconds >= DETACH_RETURN_LIMIT_SECONDS`. The time check runs last so that:
   - a blocking launcher still fails with the same "PID … is gone" or "did not return within 3 s" message (AC3);
   - the slow launcher's failure names the time bound only after its child was confirmed alive (AC2).
3. **Restore the step.** Add the step `the script returns control to the shell in under two seconds`, bound to a function that calls `assert_detached` on the run, to both detach scenarios. It sits directly after `the script exits 0 while the process it started is still running`. The child-alive step stays (AC1, FR1).
4. **Invert the slow scenario.** Replace "A slow launcher that detaches still passes the detach check (AC3)" with "A slow launcher fails the detach check (AC2)". It keeps the `Given` (the `slow_launcher` fixture with its marker) and the `When`. Its `Then` becomes `the detach check fails because the launcher took longer than two seconds`, which asserts `pytest.raises(AssertionError, match=r"took \d+\.\d+ s to return \(limit 2\.0 s\)")`. It keeps `And the launcher finished its 2.5 second delay before detaching`. The `@scenario` binding is renamed `test_slow_launcher_fails_detach_check`, and `detach_passes_child_running` is removed (AC2, FR2).
5. The `fake_child` fixture, `_FAKE_CHILD_BODY`, `_wait_for_pid`, `_pid_alive`, and the teardown that writes the stop file and sends SIGTERM do not change (FR3).

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `tests/bdd/steps/test_scaffold.py` | `elapsed_seconds` on `LauncherRun`; timing in `_run_launcher`; `DETACH_RETURN_LIMIT_SECONDS`; final elapsed check in `assert_detached`; new under-two-seconds step; slow-launcher scenario binding and `Then` step inverted | AC1, AC2, FR1, FR2 |
| `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature` | Under-two-seconds step added to both detach scenarios; slow-launcher scenario renamed and its outcome inverted | AC1, AC2 |

## Blast Radius

Only the scaffold BDD scenarios change:
- The idempotency scenario still calls `_run_launcher` with a 5 s bound and reads only `result`.
- The two blocking-launcher scenarios keep their match patterns, because the time check runs after the checks they trigger.
- The launcher scripts and every other test module stay untouched.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Time bound and child-alive check together in `assert_detached` | Selected | Every caller enforces both properties the issue requires |
| A separate time-only step, leaving `assert_detached` structural | Rejected | Callers of `assert_detached` could pass a slow launcher, which is the regression this issue reverses |
| A bound looser than 2.0 s | Rejected | The issue fixes the bound at two seconds |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #226 | 2026-11-12 | Initial defect design |
