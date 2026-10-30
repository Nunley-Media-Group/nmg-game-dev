# Blender MCP: latest mcp-for-blender

The Blender MCP server is `mcp-for-blender`, published from `ahujasid/blender-mcp`. It ships
with a matching Blender add-on. nmg-game-dev runs the latest release of both, with no version
pin. Blender itself is 5.2 LTS.

`.mcp.json` declares the server:

```json
"blender": {
  "command": "uvx",
  "args": ["mcp-for-blender@latest"],
  "env": { "BLENDER_MCP_DISABLE_TELEMETRY": "1" }
}
```

## Ports and overrides

| Variable | Default | Used by |
|----------|---------|---------|
| `BLENDER_MCP_PORT` | `9876` | `start-blender-mcp.sh`: the port it checks for an already-running server |
| `BLENDER_APP` | `/Applications/Blender.app` | `start-blender-mcp.sh` |
| `BLENDER_BIN` | unset | `start-blender-mcp.sh`. Wins over `BLENDER_APP` when it is executable |
| `BLENDER_MCP_ADDON` | unset | `start-blender-mcp.sh`. Add-on module name tried before the defaults |
| `BLENDER_USER_ADDONS` | unset | `install-blender-mcp-addon.sh`, passed through to the install command |

## Setup

1. **Install the add-on.** `scripts/install-blender-mcp-addon.sh` runs
   `uvx mcp-for-blender@latest install-addon`. It exits 2 with a remediation if `uvx` is missing
   or the install fails. Install `uv` first.
2. **Start Blender.** `scripts/start-blender-mcp.sh` launches Blender in the background with the
   add-on enabled and its server started. It is idempotent: if `BLENDER_MCP_PORT` is already
   listening it exits 0 without launching a second Blender. Its output goes
   to `/tmp/blender-mcp.log`. The add-on is enabled from the first candidate that is installed,
   in this order: the `BLENDER_MCP_ADDON` override, `blender_mcp`,
   `bl_ext.user_default.blender_mcp`, `blender-mcp-addon`, `bl_ext.user_default.blender-mcp`,
   `blender-mcp`.
3. **Smoke-test the server.** `scripts/smoke-blender-mcp.py` (see below).

## Smoke test

`scripts/smoke-blender-mcp.py` reads `mcpServers.blender` from `.mcp.json` and starts it over
stdio. Then it runs:

1. `initialize`, then `notifications/initialized`.
2. `tools/list`, which must offer `execute_blender_code`.
3. `execute_blender_code` with `import bpy` and `print(bpy.app.version_string)`. A non-error reply
   that contains a version string passes.

Each reply has 120 seconds (`--timeout` overrides this). The server process is stopped on exit.

| Exit | Meaning |
|------|---------|
| `0` | Every check passed |
| `1` | A check failed. stderr shows `FAIL <step>: <detail>` |
| `2` | Blender or the add-on is not reachable. stderr names `scripts/install-blender-mcp-addon.sh` and `scripts/start-blender-mcp.sh` |

## Versions

Blender 5.2 LTS, the `mcp-for-blender` server, and its add-on all track their latest releases.
None is pinned, and there is no `--with` or `mcp<2` constraint. The smoke script verifies that
the latest versions work together. If the smoke script fails after an upgrade, fix the script or
report the regression upstream. Don't pin the old version.
