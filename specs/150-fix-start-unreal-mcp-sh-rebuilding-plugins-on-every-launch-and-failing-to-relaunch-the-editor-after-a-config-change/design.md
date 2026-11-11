# Root Cause Analysis: start-unreal-mcp.sh rebuilds plugins on every launch and fails to relaunch the editor after a config change

**Issue**: #150
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/103-build-missing-project-plugin-binaries-before-start-unreal-mcp-sh-launches-the-editor/

## Root Cause

Four defects in the plugin build step of `scripts/start-unreal-mcp.sh` combine:

1. **Two targets.** The build runs `Build.sh UnrealEditor Mac Development -Project=<uproject> -TargetType=Editor -NoEngineChanges`. UnrealBuildTool plans the named `UnrealEditor` target and the project's editor target selected by `-TargetType=Editor`. Both compile the project plugins into the same `Plugins/*/Intermediate/Build/Mac/arm64/UnrealEditor/Development/` directory, so when UBT regenerates its makefiles (for example after `Config/DefaultEngine.ini` changes) it fails with `Unable to merge actions ... PrerequisiteItems are different` and `Action graph is invalid`.
2. **Wrong binary name.** `plugin_needs_build` checks `Binaries/Mac/UnrealEditor-<Module>.dylib`. UE 5.8 on macOS writes `libUnrealEditor-<Module>.dylib`, so every module reads as missing and the build runs on every launch, which is what exposes defect 1.
3. **Plugin-wide staleness.** It compares everything under the plugin's `Source/` plus the `.uplugin` against the oldest module binary. UBT relinks only modules whose inputs changed, so after a change to one module another module's binary stays older than the plugin's newest source, and the plugin is stale on every launch.
4. **All-or-nothing failure and a blind report.** Any build failure exits without launching, even when every binary exists. The report greps for `error:`; a UBT planning failure has none, so it prints `no compiler error found`.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `scripts/start-unreal-mcp.sh` | `plugin_needs_build` | Binary name and staleness test (defects 2, 3) |
| `scripts/start-unreal-mcp.sh` | build block after `build_names` | Build argv, failure handling and report (defects 1, 4) |
| `tests/start_unreal_fakes.py` | `Sandbox.dylib`, `make_sandbox`, `expected_build_argv` | Fakes encode the old binary name and argv |
| `docs/mcp/unreal.md` | Setup step 2 | Describes the old build and failure behavior |

## Fix Strategy

In `scripts/start-unreal-mcp.sh`:

1. Add `module_binary <plugin_dir> <module>`: prints `<plugin_dir>/Binaries/Mac/libUnrealEditor-<module>.dylib` when it exists, else `<plugin_dir>/Binaries/Mac/UnrealEditor-<module>.dylib` when it exists, else nothing.
2. Add `module_source_dir <plugin_dir> <module>`: prints the directory of the first `<module>.Build.cs` found under `<plugin_dir>/Source`, or `<plugin_dir>/Source` when none is found.
3. Rewrite `plugin_needs_build`: an unparseable `.uplugin` still needs a build; for each module from `editor_modules`, a missing binary needs a build; otherwise the module is stale when `find <module_source_dir> -newer <binary> -print -quit` prints anything. The `.uplugin` is not an input.
4. Add `plugin_binaries_present <plugin_dir> <uplugin>`: returns 0 when `plutil` parses the `.uplugin` and every module from `editor_modules` has a `module_binary`.
5. Keep the list of enabled source plugins from `project_source_plugins` in an array so the post-failure check reuses it.
6. Build with `"${BUILD_SH}" Mac Development -Project="${PROJECT}" -TargetType=Editor -NoEngineChanges`.
7. Add `build_failure_reason`: the first `grep -m1 'error:'` line, else the first line containing `Result: Failed`, else the last non-empty line of `BUILD_LOG`, else `build log is empty`.
8. On a non-zero build: when `plugin_binaries_present` holds for every enabled source plugin, print `start-unreal-mcp: warning: plugin build failed (exit N) — see /tmp/unreal-mcp-build.log; starting the editor on the existing plugin binaries` and `start-unreal-mcp: failure reason: <reason>`, then fall through to the launch. Otherwise print `start-unreal-mcp: plugin build failed (exit N) — see /tmp/unreal-mcp-build.log` and `start-unreal-mcp: failure reason: <reason>`, and exit with Build.sh's status (1 if that is 0).

The port check, editor check, project resolution, `editor_modules`, `plugin_disabled`, `project_source_plugins` and the launch flags are unchanged.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `scripts/start-unreal-mcp.sh` | Steps 1–8 above | AC1–AC7, FR1–FR6 |
| `tests/start_unreal_fakes.py` | Binary name `libUnrealEditor-`; argv without `UnrealEditor`; sandbox options for a stale binary, a second module, module `Build.cs` files, a project `Config/DefaultEngine.ini` and a project `Source/<Project>Editor.Target.cs` | FR7 |
| `tests/unit/test_start_unreal_mcp.py` | Unit tests for AC1–AC7 | FR7 |
| `tests/bdd/features/start_unreal_plugin_build.feature`, `tests/bdd/test_start_unreal_plugin_build_bdd.py` | #103 step texts updated to the `libUnrealEditor-` name and the single-target argv | FR1, FR2 |
| `tests/bdd/features/start_unreal_plugin_relaunch.feature`, `tests/bdd/test_start_unreal_plugin_relaunch_bdd.py` | Scenarios SCN001–SCN007 for AC1–AC7 | FR7 |
| `docs/mcp/unreal.md` | Setup step 2 describes per-module staleness, the UE 5.8 binary name, and launching on existing binaries after a failed build | Docs match behavior |

## Blast Radius

Only the launcher's pre-launch build step changes. Consumers get the script through `/onboard-consumer`; the SessionStart hook, its 900-second timeout and `merge_session_hooks` are unchanged. A project whose binaries are current now launches without invoking UBT. A failed build no longer blocks the launch when every binary exists, so the editor may start on binaries older than their sources; the warning names the build log.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Select the target with `-TargetType=Editor` only | Selected | One target for Blueprint-only and code projects alike, with no target-name discovery |
| Name the project's editor target (`<Project>Editor`) and drop `-TargetType` | Rejected | A Blueprint-only project has no `.Target.cs` to read the name from |
| Keep `UnrealEditor` and drop `-TargetType=Editor` | Rejected | Builds project plugins against the engine target, not the project's editor target that the editor loads |
| Keep the `.uplugin` as a staleness input | Rejected | A `.uplugin` version bump does not relink, so the plugin would stay stale forever |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #150 | 2026-11-11 | Initial defect design |
