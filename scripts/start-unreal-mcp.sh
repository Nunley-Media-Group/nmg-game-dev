#!/usr/bin/env bash
# start-unreal-mcp.sh — Idempotent Unreal Engine Editor MCP launcher.
#
# Ships as a consumer deliverable; invoked manually in this repo (nmg-game-dev)
# for smoke-testing (opens fixtures/dogfood.uproject by default), and as a
# SessionStart hook in consumer game projects (opens the consumer's .uproject).
#
# Design: design.md § Artifact specifications #4
# Invariants: steering/tech.md § Session-start contract invariants 1-6
set -euo pipefail

readonly PORT="${UE_MCP_PORT:-8088}"
readonly LOG="/tmp/unreal-mcp.log"
readonly UE_ROOT="${UE_ROOT:-/Users/Shared/Epic Games/UE_5.7}"
readonly UE_EDITOR="${UE_ROOT}/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"

if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "start-unreal-mcp: port ${PORT} already LISTEN — skipping launch" >&2
  exit 0
fi

if [[ ! -x "${UE_EDITOR}" ]]; then
  echo "start-unreal-mcp: UnrealEditor not found at ${UE_EDITOR} — set UE_ROOT" >&2
  exit 1
fi

# Resolution order: UE_PROJECT → single *.uproject in $PWD → $PWD/fixtures/dogfood.uproject.
resolve_uproject() {
  if [[ -n "${UE_PROJECT:-}" ]]; then
    echo "${UE_PROJECT}"
    return
  fi
  local found
  mapfile -t found < <(find "${PWD}" -maxdepth 2 -name "*.uproject" 2>/dev/null)
  if (( ${#found[@]} == 1 )); then
    echo "${found[0]}"
    return
  fi
  if [[ -f "${PWD}/fixtures/dogfood.uproject" ]]; then
    echo "${PWD}/fixtures/dogfood.uproject"
    return
  fi
  echo "start-unreal-mcp: no .uproject resolved — set UE_PROJECT, or run from a consumer project containing exactly one .uproject file" >&2
  exit 1
}

PROJECT="$(resolve_uproject)"
readonly PROJECT

# Port binding is the UE plugin's responsibility (issue #3) — this script only launches UE.
nohup "${UE_EDITOR}" "${PROJECT}" -log >"${LOG}" 2>&1 &
disown
echo "start-unreal-mcp: launched UE Editor (project ${PROJECT}, port ${PORT}, log ${LOG}, pid $!)"
exit 0
