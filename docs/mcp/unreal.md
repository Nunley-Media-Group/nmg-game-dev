# Unreal MCP: UE 5.8 with Epic's native server and VibeUE

The agent reaches Unreal through one HTTP endpoint built from two layers:

1. **Epic's Unreal MCP and Editor Tools.** UE 5.8 ships the `ModelContextProtocol` and
   `EditorToolset` plugins. The editor serves streamable HTTP at
   `http://127.0.0.1:<UE_MCP_PORT>/mcp`.
2. **VibeUE.** A third-party plugin that registers its toolsets, including
   `execute_python_code`, on that same endpoint. nmg-game-dev does not author its own UE-side
   bridge, and nothing listens on port 8088 any more.

`.mcp.json` declares the endpoint as a native HTTP server:

```json
"unreal": {
  "type": "http",
  "url": "http://127.0.0.1:${UE_MCP_PORT:-8000}/mcp"
}
```

## Ports and overrides

| Variable | Default | Used by |
|----------|---------|---------|
| `UE_MCP_PORT` | `8000` | `start-unreal-mcp.sh`, `.mcp.json`, `smoke-unreal-mcp.py` |
| `UE_ROOT` | `/Users/Shared/Epic Games/UE_5.8` | `start-unreal-mcp.sh`, `run-ue-tests.sh` |
| `UE_PROJECT` | single `*.uproject` under `$PWD`, else `fixtures/dogfood.uproject` | `start-unreal-mcp.sh` |

`smoke-unreal-mcp.py --url <URL>` overrides the endpoint for a single run. `--fbx <PATH>`
overrides the smoke FBX.

## Setup

1. **Install VibeUE.** `scripts/install-vibeue.sh [plugins_dir]` clones branch `5-8` of VibeUE
   (its UE 5.8 line) at depth 1 into `fixtures/Plugins/VibeUE`, or updates an existing clone to
   origin's `5-8` head. It prints the commit it checked out. It tracks that branch head and never
   pins a tag or commit. Consumer projects get VibeUE from `onboard-consumer` (#7), which tracks
   the same branch.
2. **Start the editor.** `scripts/start-unreal-mcp.sh` launches UE 5.8 with
   `-ModelContextProtocolStartServer -ModelContextProtocolPort=$UE_MCP_PORT`. It is idempotent:
   if the port is already listening it exits 0 without launching a second editor. Before it
   launches, it builds the project's source-only plugins that need it: an enabled plugin under
   `Plugins/` or an `AdditionalPluginDirectories` entry, with `Source/`, whose editor module
   dylib in `Binaries/Mac/` is missing or older than its sources. The build runs the engine's
   `Build.sh` in the foreground and logs to `/tmp/unreal-mcp-build.log`. If it fails, the script
   exits non-zero with the first `error:` line and does not launch the editor. The consumer
   SessionStart hook for this script has a 900-second timeout, so a first build can finish. The
   editor runs detached, and its output goes to `/tmp/unreal-mcp.log`. If UE or the project can't
   be found it exits 1 with a one-line remediation.
3. **Smoke-test the pair.** `scripts/smoke-unreal-mcp.py` (see below).

The dogfood fixture (`fixtures/dogfood.uproject`) enables `ModelContextProtocol`,
`EditorToolset`, `VibeUE`, and `nmg-game-dev`. `fixtures/Config/DefaultEditorPerProjectUserSettings.ini`
sets `bAutoStartServer=True` and `ServerPortNumber=8000`, so an editor opened by hand also serves
the endpoint.

## Smoke test

`scripts/smoke-unreal-mcp.py` is stdlib-only. It runs these steps in order:

1. Initialize an MCP session. It accepts JSON or SSE replies and keeps `Mcp-Session-Id`.
2. Find a tool that runs Python. If `execute_python_code` is not native, it looks for a VibeUE
   toolset through `list_toolsets`, `describe_toolset`, and `call_tool`.
3. Run `unreal.SystemLibrary.get_engine_version()`. The output must contain `5.8`.
4. Import `fixtures/smoke/SM_SmokeCube.fbx` into `/Game/__NmgSmoke` and confirm
   `/Game/__NmgSmoke/SM_SmokeCube` exists.
5. Delete `/Game/__NmgSmoke` and confirm it is gone. This step also runs after a failed step 4.

Calls run one at a time, because the native server runs tools on the game thread.

| Exit | Meaning |
|------|---------|
| `0` | Every check passed |
| `1` | A check failed. stderr shows `FAIL <step>: <detail>` |
| `2` | The endpoint is unreachable. stderr says to run `scripts/start-unreal-mcp.sh` |

## Versions

UE 5.8 is the engine. Epic's MCP plugins ship with it, and VibeUE comes from its `5-8` branch, its UE 5.8 line.
Nothing here is pinned to a version, tag, or commit. The smoke script is what
verifies that the latest versions work together. When it fails after an upgrade, fix the smoke
script or report the regression upstream. Don't pin the old version.
