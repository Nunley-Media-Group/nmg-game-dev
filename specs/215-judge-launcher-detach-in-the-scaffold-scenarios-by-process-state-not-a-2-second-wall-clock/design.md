# Root Cause Analysis: The scaffold launcher detach scenarios fail on a loaded host because they time the launcher instead of checking that it detached

**Issue**: #215
**Date**: 2026-11-12
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/1-scaffold-plugin-repo-session-start-hooks/

## Root Cause

`_run_launcher` in `tests/bdd/steps/test_scaffold.py` wraps `subprocess.run(["bash", scripts/<name>])` in `time.monotonic()` and returns `elapsed_seconds`. The shared step `the script returns control to the shell in under two seconds` asserts `elapsed_seconds < 2.0`. That measures how fast the host runs bash, not whether the launcher detached. The fakes (`fake_blender_bin`, and the `fake_ue_root` editor) exit immediately, so the scenarios cannot observe whether the child outlived the launcher, which is the real property of a detached launch.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `tests/bdd/steps/test_scaffold.py` | `LauncherRun`, `_run_launcher`, `script_returns_quickly`, `fake_blender_bin`, `fake_ue_root`, `run_unreal_script` comment | Wall-clock check and fakes that exit at once |
| `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature` | The two detach scenarios (AC3 of #1) | Step text names the two-second bound |

## Fix Strategy

1. **Long-lived fakes (FR2).** A helper `_write_fake_child(path)` writes a bash fake that:
   - appends its argv, one per line, to `$FAKE_CHILD_ARGV_FILE`;
   - writes `$$` to `$FAKE_CHILD_PID_FILE`;
   - then loops `sleep 0.1` until `$FAKE_CHILD_STOP_FILE` exists, `$FAKE_CHILD_LIFETIME` seconds have passed, or 120 s have passed, whichever comes first, and exits 0.

   Both `fake_blender_bin` and the `fake_ue_root` editor use it. The UE argv file path stays what the existing UE assertions read. A fixture `fake_child` provides per-test `argv`, `pid`, and `stop` paths under `tmp_path`. On teardown it creates the stop file and sends `SIGTERM` to any recorded PID that is still alive, so no fake outlives the test.
2. **Structural check (FR1).**
   - `LauncherRun` drops `elapsed_seconds`. `_run_launcher(script, env_overrides, timeout=30)` accepts a script name under `scripts/` or an absolute `Path`. It returns `LauncherRun(result, timed_out)`, catching `subprocess.TimeoutExpired` as `timed_out=True` with `result=None` instead of raising.
   - `assert_detached(run, pid_file)` fails with `launcher did not return within <timeout> s while its child was running` when `timed_out` is true. It fails with `launcher exited <code>: <stderr>` when the exit code is not 0. Otherwise it waits up to 10 s for `pid_file` to hold a PID, then fails with `launcher exited before its child was still running (PID <pid> is gone)` unless `os.kill(pid, 0)` succeeds.
   - The step text `the script returns control to the shell in under two seconds` becomes `the script exits 0 while the process it started is still running`, bound to `assert_detached` with the run's PID file. Both detach scenarios use it, and the UE scenario keeps its argv assertions.
3. **Blocking and slow launchers (FR3, AC2, AC3).** New scenarios in the same feature run synthetic launchers that `_run_launcher` accepts by path, all against the long-lived fake child:
   - **AC2, waits for its child:** a launcher that runs `"$FAKE_CHILD" &` then `wait`. The child is given `FAKE_CHILD_LIFETIME=1`, so the launcher exits 0 after the child exits. `assert_detached` must raise its "child is gone" `AssertionError`, and the scenario asserts that it did.
   - **AC2, hangs:** the same blocking launcher with no lifetime limit, run with a 3 s bound. `assert_detached` must raise its timeout `AssertionError`.
   - **AC3, slow but detached:** a launcher that runs `sleep 2.5`, then starts the child with `nohup "$FAKE_CHILD" >/dev/null 2>&1 &`, `disown`, and `exit 0`. `assert_detached` passes, although the run took more than 2 s.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `tests/bdd/steps/test_scaffold.py` | Long-lived fakes with PID/argv/stop files and teardown; `_run_launcher` without wall-clock timing; `assert_detached`; new step and scenario bindings | AC1–AC3, FR1–FR3 |
| `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature` | Detach step text replaced; scenarios for a launcher that waits on its child, one that hangs, and one that is slow but detached | AC1–AC3 |

## Blast Radius

Only the scaffold BDD scenarios change. The idempotency scenario keeps using `_run_launcher` (with its 5 s bound) and reads only `result`. The launcher scripts and every gate other than `repository.*` are untouched.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Check that the script exited 0 while the child it started is alive | Selected | It is the property detach guarantees and is independent of host load |
| Raise the wall-clock bound | Rejected | Still fails under heavier load, and a blocking launcher with a fast child would pass |
| Measure only CPU time of the launcher | Rejected | Does not detect a launcher that waits on its child |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #215 | 2026-11-12 | Initial defect design |
