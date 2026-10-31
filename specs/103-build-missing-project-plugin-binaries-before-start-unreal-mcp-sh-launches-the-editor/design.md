# Design: Build missing project plugin binaries before start-unreal-mcp.sh launches the editor

**Issue**: #103
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/1-scaffold-plugin-repo-session-start-hooks/

## Overview

`scripts/start-unreal-mcp.sh` gains a pre-launch step between project resolution and the `nohup` launch. It lists the project's source plugins and checks each one's editor dylibs. When any are missing or stale, it runs the engine's `Build.sh` editor build synchronously and either continues to the existing launch or exits non-zero with the build log path and first error. The SessionStart hook gets a 900-second timeout in the consumer template and in the onboarding merge, so a first build can finish inside the hook.

## Architecture

Order inside the script (port check, editor check, and project resolution are unchanged and stay first):

1. `plugin_dirs`: each `*/` under `<project dir>/Plugins/` and under each `AdditionalPluginDirectories` entry (resolved relative to the `.uproject`'s directory, read with `plutil -extract AdditionalPluginDirectories json -o - <uproject>`), that contains exactly one `*.uplugin` and a `Source/` directory.
2. Skip a plugin that the `.uproject` lists with `"Enabled": false`.
3. `editor_modules <uplugin>`: read `Modules` with `plutil`. Keep each module whose `Type` is one of `Runtime`, `RuntimeNoCommandlet`, `RuntimeAndProgram`, `Editor`, `EditorNoCommandlet`, `EditorAndProgram`, `Developer`, `DeveloperTool`, or `UncookedOnly`, and whose `PlatformAllowList` is absent or contains `Mac`, and whose `PlatformDenyList` does not contain `Mac`.
4. A plugin **needs a build** when any kept module lacks `<plugin>/Binaries/Mac/UnrealEditor-<Module>.dylib`, or when `find <plugin>/Source <plugin>/*.uplugin -newer <oldest dylib>` prints anything.
5. When no plugin needs a build, go straight to the launch.
6. Otherwise, require `BUILD_SH="${UE_ROOT}/Engine/Build/BatchFiles/Mac/Build.sh"` to be executable (AC4). Log `start-unreal-mcp: building project plugins (<names>) — log /tmp/unreal-mcp-build.log` to stderr. Run `"${BUILD_SH}" UnrealEditor Mac Development -Project="${PROJECT}" -TargetType=Editor -NoEngineChanges >"${BUILD_LOG}" 2>&1`.
7. On a non-zero exit, print `start-unreal-mcp: plugin build failed (exit N) — see /tmp/unreal-mcp-build.log` and `start-unreal-mcp: first error: <line>` (the first `grep -m1 'error:'` line, or `no compiler error found`) to stderr, and exit with Build.sh's status, or 1 if that status is 0.
8. Launch exactly as today.

A `.uplugin` that `plutil` cannot parse counts as needing a build, so UBT reports the real problem. `BUILD_LOG` is `readonly`, next to the existing `LOG`.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `scripts/start-unreal-mcp.sh` | env `UE_ROOT`, `UE_PROJECT`, `UE_MCP_PORT` (unchanged) | exit 0 after launch; non-zero on build failure or missing `Build.sh`; build log `/tmp/unreal-mcp-build.log` | Builds stale or missing project plugin binaries before launch |
| `templates/consumer/.claude/settings.json` | — | `start-unreal-mcp.sh` hook entry has `"timeout": 900` | Hook may run a first build |
| `nmg_game_dev.onboard.settings.merge_session_hooks` | template + settings | `StepResult` `installed`, `refreshed` (a timeout raised on an existing hook), or `unchanged` | Adds missing hooks as today; for a hook with the same `command`, sets `timeout` to the template's value when it is absent or lower |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Foreground build with a 900 s hook timeout | Selected | Reports the failure where the session sees it (AC3); skipped when binaries are current |
| Detached build-then-launch | Rejected | The session never sees a build failure |
| Always run Build.sh | Rejected | A no-op UBT run still adds tens of seconds to every session start |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #103 | 2026-10-31 | Initial feature design |
