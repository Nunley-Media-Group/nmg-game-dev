# Design: Upgrade toolchain to UE 5.8 with native MCP plus VibeUE, and Blender 5.2 MCP

**Issue**: #68
**Date**: 2026-10-30
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs/

## Overview

Point the repo at UE 5.8 and its native MCP server, run the latest Blender MCP (`mcp-for-blender`) with its bundled add-on, and stop pinning third-party tools. Two install scripts fetch the latest VibeUE and Blender add-on. Two stdlib-only smoke scripts prove the latest versions work end to end. Guard tests lock the endpoint, the 5.8 references, and the latest-version policy.

## Architecture

```
Claude Code ── .mcp.json ──┬─ blender: uvx mcp-for-blender@latest (stdio) ─► socket 9876 ─► Blender + blender_mcp add-on
                           └─ unreal:  type http ─► 127.0.0.1:${UE_MCP_PORT:-8000}/mcp ─► UE 5.8 Unreal MCP (+ EditorToolset) + VibeUE toolsets

scripts/start-unreal-mcp.sh   → UnrealEditor <uproject> -ModelContextProtocolStartServer -ModelContextProtocolPort=$PORT -log
scripts/install-vibeue.sh     → git clone --depth 1 <VibeUE> fixtures/Plugins/VibeUE   (or git pull --ff-only)
scripts/install-blender-mcp-addon.sh → uvx mcp-for-blender@latest install-addon
scripts/smoke-unreal-mcp.py   → JSON-RPC over streamable HTTP
scripts/smoke-blender-mcp.py  → JSON-RPC over stdio to the .mcp.json blender command
```

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `scripts/start-unreal-mcp.sh` | env `UE_ROOT` (default `/Users/Shared/Epic Games/UE_5.8`), `UE_MCP_PORT` (default 8000), `UE_PROJECT` | exit 0 (launched or already listening) / 1 (editor or project missing) | AC1, AC2 |
| `scripts/run-ue-tests.sh` | env `UE_ROOT` (default `/Users/Shared/Epic Games/UE_5.8`) | unchanged | AC1; messages say 5.8 |
| `scripts/install-vibeue.sh [plugins_dir]` | default `<repo>/fixtures/Plugins` | exit 0 with the checked-out commit printed / 2 when `git` is missing or the clone fails | AC2, AC6 |
| `scripts/install-blender-mcp-addon.sh` | env `BLENDER_USER_ADDONS` passed through | exit 0 / 2 when `uvx` is missing or install fails | AC5, AC6 |
| `scripts/smoke-unreal-mcp.py [--url URL] [--fbx PATH]` | default URL `http://127.0.0.1:${UE_MCP_PORT:-8000}/mcp`, default FBX `fixtures/smoke/SM_SmokeCube.fbx` | exit 0 / 1 (`FAIL <step>: <detail>`) / 2 (`UNREACHABLE: ... run scripts/start-unreal-mcp.sh`) | AC4 |
| `scripts/smoke-blender-mcp.py [--mcp-json PATH]` | default repo `.mcp.json` | exit 0 / 1 / 2 (remediation names `scripts/install-blender-mcp-addon.sh` and `scripts/start-blender-mcp.sh`) | AC5 |

### Unreal smoke steps

1. POST `initialize` (protocol `2025-06-18`, `Accept: application/json, text/event-stream`). Parse a JSON or SSE `data:` response and keep `Mcp-Session-Id`. Send `notifications/initialized`. A connection error exits 2.
2. `tools/list`. When `execute_python_code` is not native, call `list_toolsets` and `describe_toolset` (via `tools/call`) and find a toolset whose name or description contains `VibeUE` and that provides `execute_python_code`. Native tools are called directly; toolset tools go through `call_tool` with the toolset and tool names as `describe_toolset` reports them.
3. `execute_python_code` with `import unreal; print(unreal.SystemLibrary.get_engine_version())`. The output must contain `5.8`.
4. `execute_python_code` that builds an `unreal.AssetImportTask` for the FBX (`destination_path="/Game/__NmgSmoke"`, `automated=True`, `save=False`, `replace_existing=True`), runs `AssetToolsHelpers.get_asset_tools().import_asset_tasks`, and prints whether `EditorAssetLibrary.does_asset_exist("/Game/__NmgSmoke/SM_SmokeCube")` is true.
5. `execute_python_code` that runs `EditorAssetLibrary.delete_directory("/Game/__NmgSmoke")` and prints whether `does_directory_exist` is false. Step 5 also runs in a `finally` after any failure in step 4.

Calls are strictly sequential (the native server runs tools serially on the game thread).

### Blender smoke steps

Read `mcpServers.blender` from `.mcp.json`, start `command`/`args` with its `env` merged, and speak newline-delimited JSON-RPC on stdin/stdout: `initialize`, `notifications/initialized`, `tools/list` (must include `execute_blender_code`), then `tools/call execute_blender_code` with `import bpy\nprint(bpy.app.version_string)`. A non-error result containing a version string passes. A result whose text reports that it couldn't connect to Blender exits 2. Each read has a 120 s timeout; the child is terminated on exit.

## Data / Storage Changes

`.mcp.json`:

```json
{
  "mcpServers": {
    "blender": {
      "command": "uvx",
      "args": ["mcp-for-blender@latest"],
      "env": { "BLENDER_MCP_DISABLE_TELEMETRY": "1" },
      "description": "Blender MCP — ahujasid/blender-mcp, published as mcp-for-blender; always the latest release"
    },
    "unreal": {
      "type": "http",
      "url": "http://127.0.0.1:${UE_MCP_PORT:-8000}/mcp",
      "description": "Unreal MCP — Epic's native UE 5.8 server with VibeUE's toolsets registered on it"
    },
    "meshy": "(unchanged)"
  }
}
```

`fixtures/dogfood.uproject`: `EngineAssociation` `5.8`. `Plugins`: `ModelContextProtocol`, `EditorToolset`, `VibeUE`, and `nmg-game-dev`, all enabled. `AdditionalPluginDirectories` stays `["../plugins"]`.

`fixtures/Config/DefaultEditorPerProjectUserSettings.ini`:

```ini
[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]
bAutoStartServer=True
ServerPortNumber=8000
```

`.gitignore`: remove `fixtures/Config/` and `fixtures/Source/`, and add `fixtures/Plugins/`. Track the existing `fixtures/Source/{Dogfood.Target.cs,DogfoodEditor.Target.cs,Dogfood/Dogfood.Build.cs,Dogfood/Dogfood.h,Dogfood/Dogfood.cpp}` and `fixtures/Config/{DefaultEngine.ini,DefaultInput.ini}`, with any 5.7-specific build settings moved to the 5.8 equivalents.

`fixtures/smoke/SM_SmokeCube.fbx`: a 1 m cube named `SM_SmokeCube`, exported from headless Blender with contract §7 FBX settings.

`start-blender-mcp.sh` candidate order: `BLENDER_MCP_ADDON` override, then `blender_mcp`, `bl_ext.user_default.blender_mcp`, `blender-mcp-addon`, `bl_ext.user_default.blender-mcp`, `blender-mcp`.

Guard constants in `tests/_scaffold_contract.py`: drop `FLOATING_VERSION_REFS`; add `UNREAL_MCP_URL = "http://127.0.0.1:${UE_MCP_PORT:-8000}/mcp"`, `BLENDER_MCP_PACKAGE = "mcp-for-blender@latest"`, and `UE_VERSION = "5.8"`.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Native `type: http` entry in `.mcp.json` | Selected | Claude Code speaks streamable HTTP directly; drops the Node.js `mcp-remote` hop |
| Launch flags plus project INI for auto-start | Selected | Flags make the start script work for any project; the INI covers editors opened by hand |
| `mcp-for-blender@latest` instead of the `blender-mcp` shim | Selected | Canonical package name; bundles the matching add-on and `install-addon` |
| Pin VibeUE / Blender MCP versions | Rejected | Interview decision: third-party tools track latest, verified by smoke scripts |
| Smoke scripts using the `mcp` Python SDK | Rejected | Stdlib JSON-RPC keeps the scripts dependency-free and unit-testable against a stub server |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #68 | 2026-10-30 | Initial feature design |
