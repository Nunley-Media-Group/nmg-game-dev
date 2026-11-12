# Tasks: The scaffold launcher detach scenarios fail on a loaded host because they time the launcher instead of checking that it detached

**Issue**: #215
**Date**: 2026-11-12
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/1-scaffold-plugin-repo-session-start-hooks/

## Implementation Tasks

### T001: Long-lived fake children that record their PID and are stopped afterwards

**File(s)**: `tests/bdd/steps/test_scaffold.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- The fake Blender and fake UE editor record their argv and their own PID to files given by environment variables. Each then keeps running until a stop file appears, an optional `FAKE_CHILD_LIFETIME` elapses, or 120 s pass, whichever comes first (FR2).
- A fixture creates the stop file and terminates any recorded PID that is still alive when the test ends, so no fake process outlives the test (FR2).
- The UE scenario's argv assertions (`-ModelContextProtocolStartServer`, `-ModelContextProtocolPort=18088`) still read the editor's recorded argv (AC1).

### T002: Replace the wall-clock assertion with a structural detach check

**File(s)**: `tests/bdd/steps/test_scaffold.py`, `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `LauncherRun` no longer has `elapsed_seconds`, and nothing in `test_scaffold.py` compares a launcher's run time with a threshold (AC3, FR1).
- `_run_launcher` takes a script name under `scripts/` or an absolute path, defaults to a 30 s bound, and reports a timeout as `timed_out=True` instead of raising (FR1).
- `assert_detached(run, pid_file)` passes only when the run did not time out, exited 0, and the PID the fake child recorded (waited for up to 10 s) is alive. Each failure message names the cause: timeout, non-zero exit with stderr, or the dead child PID (AC1, FR1).
- In both detach scenarios, the step `the script returns control to the shell in under two seconds` is replaced by `the script exits 0 while the process it started is still running`, bound to `assert_detached` (AC1).
- The idempotency scenario still passes with its 5 s bound.

### T003: Scenarios for blocking, hanging, and slow-but-detached launchers

**File(s)**: `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature`, `tests/bdd/steps/test_scaffold.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- AC2, FR3: a synthetic launcher in `tmp_path` that starts the fake child with `&` and then `wait`s, run with a child lifetime of 1 s, exits 0 after the child exits. `assert_detached` raises `AssertionError` naming the dead child PID, and the scenario asserts that it raised.
- AC2, FR3: the same launcher, with no lifetime limit and a 3 s bound, times out. `assert_detached` raises `AssertionError` naming the timeout, and the scenario asserts that it raised.
- AC3: a synthetic launcher that sleeps 2.5 s, then starts the fake child with `nohup … &` and `disown`, and exits 0, passes `assert_detached`. The scenario also asserts the run took more than 2 s, which shows that the old bound would have failed it.
- Every fake child started by these scenarios is stopped at teardown. No real Blender or Unreal process starts. Passes under `repository.tests` (`uv run pytest tests/unit tests/bdd -q`), and the changed files pass `repository.lint`, `repository.format`, and `repository.types`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #215 | 2026-11-12 | Initial defect tasks |
