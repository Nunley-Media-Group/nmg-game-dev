# Tasks: Build missing project plugin binaries before start-unreal-mcp.sh launches the editor

**Issue**: #103
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/1-scaffold-plugin-repo-session-start-hooks/

## Implementation Tasks

### T001: Pre-launch plugin binary check and build

**File(s)**: `scripts/start-unreal-mcp.sh`
**Type**: Modify
**Depends**: none
**Acceptance**:
- Implements the design's steps 1–7 between project resolution and the launch. Port check, editor check, resolution order, and launch flags are unchanged.
- A plugin with `Source/` and a missing or stale editor dylib triggers the logged foreground `Build.sh` run, and the editor launches after it exits 0 (AC1, FR1, FR2).
- Present, current dylibs launch without running `Build.sh` (AC2).
- A failing build or a non-executable `Build.sh` exits non-zero without launching. stderr names `/tmp/unreal-mcp-build.log` and the first `error:` line, or the missing `Build.sh` path and `UE_ROOT` (AC3, AC4, FR3).
- `shellcheck -S style scripts/*.sh` passes.

### T002: Give the start-unreal-mcp hook a 900-second timeout

**File(s)**: `templates/consumer/.claude/settings.json`, `src/nmg_game_dev/onboard/settings.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- The template's `start-unreal-mcp.sh` hook entry carries `"timeout": 900`. The Blender hook is unchanged (AC5, FR4).
- `merge_session_hooks` still appends missing hooks. For an existing hook with the same `command` whose `timeout` is absent or below the template's, it sets the template's value, writes the file, and returns status `refreshed`. Other hooks and keys keep their values and order (AC5).

### T003: Document the pre-launch build

**File(s)**: `docs/mcp/unreal.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- The "Start the editor" step in `docs/mcp/unreal.md` explains that missing or stale project plugin binaries are built first, names `/tmp/unreal-mcp-build.log`, and notes the 900-second hook timeout (FR5).
- `CHANGELOG.md` `[Unreleased]` has an Added bullet for the pre-launch plugin build that ends with `(#103)`.

### T004: Launcher and onboarding tests

**File(s)**: `tests/unit/test_start_unreal_mcp.py`, `tests/bdd/features/start_unreal_plugin_build.feature`, `tests/bdd/test_start_unreal_plugin_build_bdd.py`, `tests/bdd/steps/test_scaffold.py`, `tests/unit/onboard/test_settings.py`
**Type**: Create
**Depends**: T001, T002
**Acceptance**:
- The tests run the script against a temporary project (a `.uproject` plus `Plugins/Fake/Fake.uplugin` with one `Editor` module and a `Source/` file), with a fake `UE_ROOT` holding a fake `UnrealEditor` and a fake `Build.sh` that record their argv and a free port. They prove AC1 (Build.sh argv is `UnrealEditor Mac Development -Project=<uproject> -TargetType=Editor -NoEngineChanges`, it runs before the editor, and the log line names `Fake`), AC2 (a dylib newer than the sources means Build.sh is not run), AC3 (a fake Build.sh that prints `Foo.cpp:3:1: error: boom` and exits 2 yields a non-zero exit, no editor argv, and stderr with the log path and that line), and AC4 (no Build.sh: non-zero exit, stderr naming the path and `UE_ROOT`).
- The existing scaffold launcher scenario in `tests/bdd/steps/test_scaffold.py` still passes. Its `fake_ue_root` also provides a fake `Build.sh` that exits 0.
- `tests/unit/onboard/test_settings.py` covers AC5: the template has the 900 timeout, a missing or lower timeout is raised with status `refreshed`, an equal or higher one gives `unchanged`, and unrelated hooks are untouched.
- `tests/bdd/features/start_unreal_plugin_build.feature` (SCN001–SCN005) is bound in `tests/bdd/test_start_unreal_plugin_build_bdd.py`. `pytest tests/unit tests/bdd` passes.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #103 | 2026-10-31 | Initial feature tasks |
