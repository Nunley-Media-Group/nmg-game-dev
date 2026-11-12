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
#
# Isolation (#189): each run gets a fresh mktemp -d directory exported as BLENDER_USER_SCRIPTS,
# which overrides any inherited value. _runner.py links the add-on only inside that directory, so
# the user's Blender scripts directory and other checkouts' runs are never touched. The directory
# is removed on exit, pass or fail. Blender's exit status is passed through unchanged.
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

user_scripts="$(mktemp -d "${TMPDIR:-/tmp}/nmg-blender-user-scripts.XXXXXX")"
# Blender only adds a scripts addons directory to sys.path when it exists at startup, so create it
# before launch (#189). _runner.py still refreshes the script paths after linking.
mkdir -p "${user_scripts}/addons"
# rm -rf removes the add-on symlink itself and never follows it into the checkout.
trap 'rm -rf "${user_scripts}"' EXIT

status=0
BLENDER_USER_SCRIPTS="${user_scripts}" "${BLENDER}" --background --python-exit-code 1 \
  --python tests/blender/_runner.py -- "${target}" || status=$?
exit "${status}"
