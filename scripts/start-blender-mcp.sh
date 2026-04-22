#!/usr/bin/env bash
# start-blender-mcp.sh — Idempotent Blender MCP launcher.
#
# Ships as a consumer deliverable; invoked manually in this repo (nmg-game-dev)
# for smoke-testing, and as a SessionStart hook in consumer game projects.
#
# Design: design.md § Artifact specifications #3
# Invariants: steering/tech.md § Session-start contract invariants 1-6
set -euo pipefail

readonly PORT="${BLENDER_MCP_PORT:-9876}"
readonly LOG="/tmp/blender-mcp.log"

if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "start-blender-mcp: port ${PORT} already LISTEN — skipping launch" >&2
  exit 0
fi

# Resolution order: BLENDER_BIN → BLENDER_APP/Contents/MacOS/Blender → default /Applications.
resolve_blender() {
  if [[ -n "${BLENDER_BIN:-}" && -x "${BLENDER_BIN}" ]]; then
    echo "${BLENDER_BIN}"
    return
  fi
  local app="${BLENDER_APP:-/Applications/Blender.app}"
  local bin="${app}/Contents/MacOS/Blender"
  if [[ -x "${bin}" ]]; then
    echo "${bin}"
    return
  fi
  echo "start-blender-mcp: Blender not found. Set BLENDER_BIN or BLENDER_APP (tried: ${bin})" >&2
  exit 1
}

BLENDER="$(resolve_blender)"
readonly BLENDER

# bpy.ops.blender_mcp.start_server() is a placeholder — the Blender MCP add-on's
# concrete operator name lands with issue #2; see design.md § Open Questions.
BOOTSTRAP_PY="$(cat <<'PYEOF'
import bpy
import addon_utils
import os
import sys

override = os.environ.get("BLENDER_MCP_ADDON_OVERRIDE", "")
candidates = [c for c in override.split(",") if c]
candidates += [
    "bl_ext.user_default.blender_mcp",
    "bl_ext.user_default.blender-mcp",
    "blender_mcp",
    "blender-mcp",
]

enabled = None
for name in candidates:
    try:
        addon_utils.enable(name, default_set=True, persistent=True)
        enabled = name
        break
    except Exception:
        continue

if not enabled:
    sys.stderr.write(f"blender_mcp: no addon found among {candidates}\n")
    sys.exit(1)


def _start() -> None:
    try:
        bpy.ops.blender_mcp.start_server()  # type: ignore[attr-defined]
    except Exception as exc:
        sys.stderr.write(f"blender_mcp: failed to start server: {exc}\n")


bpy.app.timers.register(_start, first_interval=1.0)
PYEOF
)"
readonly BOOTSTRAP_PY

BLENDER_MCP_ADDON_OVERRIDE="${BLENDER_MCP_ADDON:-}" \
  nohup "${BLENDER}" --python-expr "${BOOTSTRAP_PY}" >"${LOG}" 2>&1 &
disown
echo "start-blender-mcp: launched Blender (port ${PORT}, log ${LOG}, pid $!)"
exit 0
