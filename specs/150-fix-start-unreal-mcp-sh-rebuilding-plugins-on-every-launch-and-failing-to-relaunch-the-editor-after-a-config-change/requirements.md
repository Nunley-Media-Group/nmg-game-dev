# Defect Report: start-unreal-mcp.sh rebuilds plugins on every launch and fails to relaunch the editor after a config change

**Issue**: #150
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/103-build-missing-project-plugin-binaries-before-start-unreal-mcp-sh-launches-the-editor/

## Reproduction

1. Take a Blueprint-only consumer project on UE 5.8 on macOS whose source-only project plugins (nmg-game-dev, VibeUE) are built, with the editor closed.
2. Modify the project's `Config/DefaultEngine.ini`.
3. Run `scripts/start-unreal-mcp.sh`.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | The script launches the editor. It runs `Build.sh` only when a module binary is missing or older than that module's sources, a build it runs selects one editor target, and a failed build with usable binaries still launches the editor. |
| **Actual** | The script reports every module binary missing (it looks for `UnrealEditor-<Module>.dylib`, but UE 5.8 writes `libUnrealEditor-<Module>.dylib`) and runs `Build.sh UnrealEditor Mac Development -Project=<uproject> -TargetType=Editor -NoEngineChanges`, which names two targets. The build fails with `Action graph is invalid; unable to continue` and `Result: Failed (ActionGraphInvalid)` (exit 9). The script prints `first error: no compiler error found` and exits without launching the editor. |

## Acceptance Criteria

### AC1: A config change no longer triggers a build or blocks the launch

**Given** a project whose plugin editor module binaries (`libUnrealEditor-<Module>.dylib`) are newer than their module sources
**And** the project's `Config/DefaultEngine.ini` is newer than those binaries
**When** `start-unreal-mcp.sh` runs
**Then** `Build.sh` does not run and the editor launches

### AC2: The plugin build selects a single editor target

**Given** a project plugin that needs an editor build, in a Blueprint-only project or in a project with its own `<Project>Editor.Target.cs`
**When** `start-unreal-mcp.sh` runs the build
**Then** `Build.sh` receives `Mac Development -Project=<uproject> -TargetType=Editor -NoEngineChanges` and no named target such as `UnrealEditor`

### AC3: Current UE 5.8 binaries skip the build

**Given** every editor-loaded module of every enabled project source plugin has a `Binaries/Mac/libUnrealEditor-<Module>.dylib` that is not older than that module's sources
**When** `start-unreal-mcp.sh` runs
**Then** it launches the editor without running `Build.sh`

### AC4: A change to one module does not mark the plugin stale forever

**Given** a plugin with two editor-loaded modules, where module A's binary is newer than module A's sources but older than module B's sources, and module B's binary is newer than module B's sources
**When** `start-unreal-mcp.sh` runs
**Then** it does not run `Build.sh` and the editor launches

### AC5: A failed rebuild with usable binaries still launches

**Given** a plugin whose module binary exists but is older than its sources
**And** `Build.sh` fails
**When** `start-unreal-mcp.sh` runs
**Then** it prints a warning to stderr that names the failed build, `/tmp/unreal-mcp-build.log`, and that the editor is starting on the existing plugin binaries
**And** it launches the editor and exits 0

### AC6: A failed build with a missing binary still stops

**Given** a plugin whose module binary is missing
**And** `Build.sh` fails
**When** `start-unreal-mcp.sh` runs
**Then** it exits non-zero without launching the editor and prints `/tmp/unreal-mcp-build.log` to stderr

### AC7: The failure report shows UnrealBuildTool's reason

**Given** `Build.sh` fails and its log has no `error:` line but contains `Result: Failed (ActionGraphInvalid)`
**When** the script reports the failure
**Then** stderr contains `Result: Failed (ActionGraphInvalid)` and does not contain `no compiler error found`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Invoke `Build.sh` with `-TargetType=Editor` as the only target selector, with no positional target name | Must |
| FR2 | Detect editor module binaries as `Binaries/Mac/libUnrealEditor-<Module>.dylib`, accepting a legacy `UnrealEditor-<Module>.dylib` only when the lib-prefixed file is absent | Must |
| FR3 | Judge staleness per module: a module is stale only when a file in its own module directory (the directory holding `<Module>.Build.cs`) is newer than its binary; the `.uplugin` and other modules' sources are not inputs | Must |
| FR4 | When the build fails and every expected module binary of every enabled project source plugin exists, print a warning naming the failed build, the build log path, and that the editor starts on the existing binaries, then launch | Must |
| FR5 | When the build fails and an expected module binary is missing, exit non-zero (Build.sh's status, or 1) without launching and print the build log path | Must |
| FR6 | Report a failure reason from the build log: the first `error:` line, else the first `Result: Failed` line, else the last non-empty line; never print `no compiler error found` | Should |
| FR7 | Cover FR1–FR6 in the launcher's pytest suites with the fake engine, including the UE 5.8 binary name | Must |

## Out of Scope

- Building engine plugins or the engine itself
- Changing the port, launch flags, or project resolution order
- A command-line flag to skip the plugin build
- Windows and Linux launchers

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #150 | 2026-11-11 | Initial defect report |
