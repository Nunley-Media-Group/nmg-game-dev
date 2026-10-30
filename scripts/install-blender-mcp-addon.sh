#!/usr/bin/env bash
# install-blender-mcp-addon.sh — Install the Blender add-on bundled with the latest mcp-for-blender.
#
# Runs `uvx mcp-for-blender@latest install-addon`, which copies the add-on that matches the
# latest server into Blender's add-on directory. BLENDER_USER_ADDONS is inherited from the
# environment and forwarded unchanged. Nothing is pinned: scripts/smoke-blender-mcp.py verifies
# the latest release end to end.
#
# Exit: 0 installed; 2 when uvx is missing or the install command fails.
set -euo pipefail

if ! command -v uvx >/dev/null 2>&1; then
  echo "install-blender-mcp-addon: uvx not found on PATH. Install uv (https://docs.astral.sh/uv/) and re-run." >&2
  exit 2
fi

if ! uvx mcp-for-blender@latest install-addon; then
  echo "install-blender-mcp-addon: 'uvx mcp-for-blender@latest install-addon' failed. Check network access and BLENDER_USER_ADDONS." >&2
  exit 2
fi
