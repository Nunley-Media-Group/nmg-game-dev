# Requirements: Build missing project plugin binaries before start-unreal-mcp.sh launches the editor

**Issue**: #103
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/1-scaffold-plugin-repo-session-start-hooks/

## User Story

**As a** developer of a Blueprint-only consumer project
**I want** `start-unreal-mcp.sh` to compile the project's source-only plugins before it launches the editor
**So that** the Unreal MCP endpoint comes up instead of the editor exiting at startup

## Background

Onboarding installs `Plugins/nmg-game-dev/` and VibeUE as source only, and `Plugins/*/Binaries/` is gitignored. On a fresh checkout the editor finds missing modules. The script passes `-unattended`, which suppresses the rebuild prompt, so the editor logs `Plugin 'nmg-game-dev' failed to load because module 'NmgGameDevRuntime' could not be found` and exits. Finalize then fails with `mcp.unreal.unreachable`, which hides the cause. `scripts/start-unreal-mcp.sh` today resolves the `.uproject`, checks the port, and launches `UnrealEditor` in the background without looking at plugin binaries.

## Acceptance Criteria

### AC1: Missing binaries are built before launch

**Given** a project with an enabled plugin under `Plugins/` (or under a directory in the `.uproject`'s `AdditionalPluginDirectories`) that has `Source/` but lacks `Binaries/Mac/UnrealEditor-<Module>.dylib` for one of its editor-loaded modules
**When** `start-unreal-mcp.sh` runs
**Then** it logs `start-unreal-mcp: building project plugins (<plugin names>)`, runs `"$UE_ROOT/Engine/Build/BatchFiles/Mac/Build.sh" UnrealEditor Mac Development -Project=<uproject> -TargetType=Editor -NoEngineChanges` in the foreground, and launches the editor after it exits 0

### AC2: Present binaries skip the build

**Given** every enabled project plugin with `Source/` has an editor dylib for each editor-loaded module, and no file under its `Source/` or its `.uplugin` is newer than the oldest of those dylibs
**When** `start-unreal-mcp.sh` runs
**Then** it launches the editor without running `Build.sh`

### AC3: Build failure is reported

**Given** the plugin build exits non-zero
**When** `start-unreal-mcp.sh` runs
**Then** it exits non-zero without launching the editor, and stderr names the build log `/tmp/unreal-mcp-build.log` and the first line of that log matching `error:` (or `no compiler error found` when none matches)

### AC4: Missing build tool is reported

**Given** a build is needed and `"$UE_ROOT/Engine/Build/BatchFiles/Mac/Build.sh"` is not executable
**When** `start-unreal-mcp.sh` runs
**Then** it exits non-zero without launching the editor, and stderr names the missing path and `UE_ROOT`

### AC5: The SessionStart hook allows the build to finish

**Given** the consumer template `templates/consumer/.claude/settings.json`, or a consumer `.claude/settings.json` whose `start-unreal-mcp.sh` hook has no `timeout` or a lower one
**When** `/onboard-consumer` merges the SessionStart hooks
**Then** the `start-unreal-mcp.sh` hook has `"timeout": 900`, a raised timeout is reported as `refreshed`, and other hooks and keys keep their values

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Detect enabled project plugins (`Plugins/*` plus `AdditionalPluginDirectories`) with `Source/` whose editor-loaded modules lack an up-to-date `Binaries/Mac/UnrealEditor-<Module>.dylib` | Must |
| FR2 | Run the engine `Build.sh` editor build for the project in the foreground, logging to `/tmp/unreal-mcp-build.log`, when any plugin needs a build | Must |
| FR3 | On a build failure or missing `Build.sh`, exit non-zero without launching, printing the log path and the first compiler error | Must |
| FR4 | The consumer hook template and the onboarding merge give the `start-unreal-mcp.sh` hook a 900-second timeout | Must |
| FR5 | `docs/mcp/unreal.md` describes the pre-launch build, its log, and the hook timeout | Should |

## Out of Scope

- Building engine plugins or the engine itself
- Changing the port, launch flags, or `.uproject` resolution order
- Non-macOS hosts

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #103 | 2026-10-31 | Initial feature spec |
