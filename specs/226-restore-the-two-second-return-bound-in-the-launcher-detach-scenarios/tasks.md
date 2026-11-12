# Tasks: The launcher detach scenarios no longer enforce the two-second return bound

**Issue**: #226
**Date**: 2026-11-12
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/215-judge-launcher-detach-in-the-scaffold-scenarios-by-process-state-not-a-2-second-wall-clock/

## Implementation Tasks

### T001: Restore the two-second bound in the detach check

**File(s)**: `tests/bdd/steps/test_scaffold.py`, `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `LauncherRun` has `elapsed_seconds: float`, which `_run_launcher` measures with `time.monotonic()` around the launcher run, including runs that time out (FR1).
- `assert_detached` keeps its timeout, exit-code, and child-PID checks in their current order, then fails with `launcher took <x.xx> s to return (limit 2.0 s)` when `elapsed_seconds >= 2.0`. The limit is the module constant `DETACH_RETURN_LIMIT_SECONDS = 2.0` (AC1, FR1).
- Both detach scenarios, "Launcher scripts detach Blender and UE when invoked manually (AC3)" and "start-unreal-mcp.sh detaches the UE Editor on the expected port (AC3)", contain `And the script returns control to the shell in under two seconds` in addition to `And the script exits 0 while the process it started is still running`. Each step passes for `scripts/start-blender-mcp.sh` and `scripts/start-unreal-mcp.sh` run against the fake child (AC1, FR1).
- `_FAKE_CHILD_BODY`, the `fake_child` fixture, and its teardown are unchanged (FR3).

### T002: Prove slow and blocking launchers fail the detach check

**File(s)**: `tests/bdd/steps/test_scaffold.py`, `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- AC2, FR2: the scenario "A slow launcher that detaches still passes the detach check (AC3)" no longer exists. The scenario "A slow launcher fails the detach check (AC2)" runs the 2.5 s synthetic launcher against a fake child that keeps running. It asserts that `assert_detached` raises `AssertionError` matching `took \d+\.\d+ s to return \(limit 2\.0 s\)`, and that the slow-launcher marker file exists. The binding is `test_slow_launcher_fails_detach_check`, and `detach_passes_child_running` is removed.
- AC3: the scenarios "A launcher that waits for its child fails the detach check (AC2)" and "A launcher that does not return fails the detach check (AC2)" pass unchanged. They still match `PID \d+ is gone` and `did not return within 3 s`.
- Evidence: `uv run pytest tests/bdd -q -k "launcher"` passes. `repository.tests` (`uv run pytest tests/unit tests/bdd -q`), `repository.lint`, `repository.format`, and `repository.types` pass.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #226 | 2026-11-12 | Initial defect tasks |
