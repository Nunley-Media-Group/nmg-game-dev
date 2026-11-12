# Tasks: start-unreal-mcp.sh rebuilds plugins on every launch and fails to relaunch the editor after a config change

**Issue**: #150
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/103-build-missing-project-plugin-binaries-before-start-unreal-mcp-sh-launches-the-editor/

## Implementation Tasks

### T001: Correct the plugin build step in the launcher

**File(s)**: `scripts/start-unreal-mcp.sh`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `Build.sh` is invoked as `Mac Development -Project=<uproject> -TargetType=Editor -NoEngineChanges`, with no positional target (AC2, FR1)
- Module binaries are found as `Binaries/Mac/libUnrealEditor-<Module>.dylib`, with `UnrealEditor-<Module>.dylib` accepted only when the lib-prefixed file is absent (AC3, FR2)
- Staleness is judged per module against the directory holding `<Module>.Build.cs` (whole `Source/` when none), and the `.uplugin` is not an input (AC1, AC4, FR3)
- A failed build launches the editor with the warning from design.md when every expected module binary of every enabled source plugin exists (AC5, FR4), and exits non-zero without launching otherwise (AC6, FR5)
- The failure reason line is the first `error:` line, else the first `Result: Failed` line, else the last non-empty log line, and `no compiler error found` is never printed (AC7, FR6)
- `shellcheck -S style scripts/start-unreal-mcp.sh` is clean (`gate-shellcheck`)

### T002: Update the launcher fakes

**File(s)**: `tests/start_unreal_fakes.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `Sandbox.dylib` names `libUnrealEditor-FakeEditor.dylib` and `expected_build_argv` returns `build Mac Development -Project=<uproject> -TargetType=Editor -NoEngineChanges`
- `make_sandbox` can create a stale-but-present binary, a second editor module with its own `Source/<Module>/<Module>.Build.cs`, a project `Config/DefaultEngine.ini` newer than the binaries, and a project `Source/<Project>Editor.Target.cs`

### T003: Add unit regression tests

**File(s)**: `tests/unit/test_start_unreal_mcp.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- One test per AC1–AC7 reproduces the original condition with the fake engine and asserts the AC's observable outcome
- AC2 is asserted for both a Blueprint-only project and a project with `Source/<Project>Editor.Target.cs`
- The existing #103 tests pass with the updated fakes
- `uv run pytest tests/unit tests/bdd -q` passes (`repository.tests`)

### T004: Add BDD scenarios and update the #103 feature

**File(s)**: `tests/bdd/features/start_unreal_plugin_relaunch.feature`, `tests/bdd/test_start_unreal_plugin_relaunch_bdd.py`, `tests/bdd/features/start_unreal_plugin_build.feature`, `tests/bdd/test_start_unreal_plugin_build_bdd.py`
**Type**: Create, Modify
**Depends**: T002
**Acceptance**:
- `start_unreal_plugin_relaunch.feature` carries SCN001–SCN007 from `specs/150-…/feature.gherkin`, each bound to step definitions that run the real launcher against the fakes
- The #103 feature's step texts name `libUnrealEditor-FakeEditor.dylib` and the single-target argv, and its scenarios still pass
- `uv run pytest tests/unit tests/bdd -q`, `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy src tests` pass (`repository.tests`, `repository.lint`, `repository.format`, `repository.types`)

### T005: Update the Unreal MCP setup doc

**File(s)**: `docs/mcp/unreal.md`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- Setup step 2 states that the script checks each editor module's `libUnrealEditor-<Module>.dylib` against that module's sources, runs the single-target editor build, and on a failed build launches on existing binaries with a warning or stops when a binary is missing, printing the failure reason and `/tmp/unreal-mcp-build.log`

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #150 | 2026-11-11 | Initial defect tasks |
