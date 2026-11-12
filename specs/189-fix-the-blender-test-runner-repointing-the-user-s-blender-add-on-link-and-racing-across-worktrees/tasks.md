# Tasks: The Blender test runner repoints the user's Blender add-on link and races across worktrees

**Issue**: #189
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/95-fix-the-always-green-blender-gate-re-import-entry-lookup-notarization-secret-exposure-and-stale-lockfiles/

## Implementation Tasks

### T001: Give each gate run its own temporary user scripts location

**File(s)**: `scripts/run-blender-tests.sh`
**Type**: Modify
**Depends**: none
**Acceptance**:
- The script creates a fresh directory with `mktemp -d` for each run and runs Blender with `BLENDER_USER_SCRIPTS` set to it, overriding any inherited `BLENDER_USER_SCRIPTS` (FR1, AC1, AC2).
- The directory is removed when the script exits after a passing or a failing Blender run, without following the add-on symlink inside it (FR1, AC3).
- The script exits with Blender's exit status, and the Blender argv is unchanged (`--background --python-exit-code 1 --python tests/blender/_runner.py -- <target>`).
- `gate-shellcheck` passes on the script.

### T002: Make the runner link the add-on only inside the per-run location

**File(s)**: `tests/blender/_runner.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `_install_addon_link()` creates the `nmg_game_dev_blender_addon` symlink only under `<BLENDER_USER_SCRIPTS>/addons`, pointing at this checkout's `plugins/nmg-game-dev-blender-addon` (FR2, AC2).
- When `BLENDER_USER_SCRIPTS` is unset or empty, or `bpy.utils.user_resource("SCRIPTS", path="addons")` resolves outside it, the runner raises `RuntimeError` naming `scripts/run-blender-tests.sh` and creates no directory or link (FR2, AC1).
- `user_resource` is no longer called with `create=True`.

### T003: Cover the gate script's per-run isolation and cleanup

**File(s)**: `tests/unit/test_run_blender_tests.py`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- A `BLENDER_BIN` shim test (no Blender) sets the caller's `BLENDER_USER_SCRIPTS` to a `tmp_path` directory standing in for the user's scripts directory and asserts the shim saw a different, existing directory, and that the stand-in directory's contents are unchanged after the run (AC1, FR1).
- A shim test starts two gate runs concurrently and asserts each saw its own distinct `BLENDER_USER_SCRIPTS` directory (AC2).
- Shim tests with a passing (exit 0) and a failing (exit 3) shim assert the recorded directory no longer exists after the gate returns and the gate exits 0 and 3 respectively (AC3).
- A `needs_blender` test runs the real headless gate on a `tmp_path` suite that asserts `bpy.utils.user_resource("SCRIPTS")` resolves to `BLENDER_USER_SCRIPTS`, that `<BLENDER_USER_SCRIPTS>/addons/nmg_game_dev_blender_addon` resolves to this checkout's `plugins/nmg-game-dev-blender-addon`, and that the enabled add-on module's `__file__` is inside that checkout directory (AC1, AC2, FR3).
- The existing argv and exit-code tests in the file still pass.
- `repository.tests` passes (`uv run pytest tests/unit tests/bdd -q`).

### T004: Cover the runner guard with a fake bpy

**File(s)**: `tests/unit/test_blender_runner_isolation.py`
**Type**: Create
**Depends**: T002
**Acceptance**:
- Loads `tests/blender/_runner.py` by file path and injects a fake `bpy` module whose `utils.user_resource` returns a chosen `addons` path.
- With `BLENDER_USER_SCRIPTS` set to a `tmp_path` directory and `user_resource` resolving inside it, `_install_addon_link()` creates a symlink under that directory that resolves to `plugins/nmg-game-dev-blender-addon` (FR2, FR3, AC2).
- With `BLENDER_USER_SCRIPTS` unset, and separately with `user_resource` resolving to a `tmp_path` directory outside `BLENDER_USER_SCRIPTS`, `_install_addon_link()` raises `RuntimeError` and the outside directory gains no entry (FR2, AC1).
- `repository.tests`, `repository.lint`, `repository.format`, and `repository.types` pass.

### T005: Confirm the existing Blender suite passes through the isolated gate

**File(s)**: `tests/blender/`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- `gate-blender-headless` (`scripts/run-blender-tests.sh`, headless `blender --background`) passes on the full `tests/blender` suite with the isolated user scripts location (AC4); any test that relied on the user's real scripts directory is corrected to use the per-run location.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #189 | 2026-11-11 | Initial defect tasks |
