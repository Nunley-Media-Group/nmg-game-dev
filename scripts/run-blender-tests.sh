#!/usr/bin/env bash
# run-blender-tests.sh — Headless Blender test driver.
#
# Backs gate-blender-headless (steering/tech.md § Verification Gates).
# Invoked by $nmg-sdlc:verify-code when a diff touches plugins/nmg-game-dev-blender-addon/**
# or tests/blender/**.
#
# Blender resolution order mirrors scripts/start-blender-mcp.sh lines 19-33:
#   1. BLENDER_BIN  — explicit executable override
#   2. BLENDER_APP/Contents/MacOS/Blender  — app bundle override (default /Applications/Blender.app)
#   3. /Applications/Blender.app/Contents/MacOS/Blender  — documented default
#
# Usage (from repo root):
#   scripts/run-blender-tests.sh [target]
#
# target is the optional pytest path (default tests/blender). Blender exits with the pytest
# result: --python-exit-code 1 turns an unhandled exception in the runner into exit 1, and
# _runner.py exits with pytest's exact code, so a failing or erroring test fails the gate.
set -euo pipefail

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
  echo "run-blender-tests: Blender not found. Set BLENDER_BIN or BLENDER_APP (tried: ${bin})" >&2
  exit 1
}

BLENDER="$(resolve_blender)"
readonly BLENDER

target="${1:-tests/blender}"
exec "${BLENDER}" --background --python-exit-code 1 --python tests/blender/_runner.py -- "${target}"
