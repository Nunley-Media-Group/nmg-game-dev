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

readonly PORT="${UE_MCP_PORT:-8000}"
readonly LOG="/tmp/unreal-mcp.log"
readonly BUILD_LOG="/tmp/unreal-mcp-build.log"
readonly UE_ROOT="${UE_ROOT:-/Users/Shared/Epic Games/UE_5.8}"
readonly UE_EDITOR="${UE_ROOT}/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
readonly BUILD_SH="${UE_ROOT}/Engine/Build/BatchFiles/Mac/Build.sh"

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

# Source-only project plugins (Plugins/ and AdditionalPluginDirectories, as onboarding installs them)
# need their editor dylibs compiled before the editor loads them. A fresh checkout has none, and the
# editor started with -unattended exits on the missing module. So a missing or stale dylib makes the
# engine's Build.sh build the project's editor target in the foreground, and a failed build stops the
# launch with the log path and first error.

# Prints each editor-loaded module name of the .uplugin at $1 that applies to Mac.
editor_modules() {
  local uplugin="$1" index=0 name type allow deny
  while name="$(plutil -extract "Modules.${index}.Name" raw -o - "${uplugin}" 2>/dev/null)"; do
    type="$(plutil -extract "Modules.${index}.Type" raw -o - "${uplugin}" 2>/dev/null || true)"
    allow="$(plutil -extract "Modules.${index}.PlatformAllowList" json -o - "${uplugin}" 2>/dev/null || true)"
    deny="$(plutil -extract "Modules.${index}.PlatformDenyList" json -o - "${uplugin}" 2>/dev/null || true)"
    index=$((index + 1))
    case "${type}" in
      Runtime | RuntimeNoCommandlet | RuntimeAndProgram | Editor | EditorNoCommandlet | EditorAndProgram | Developer | DeveloperTool | UncookedOnly) ;;
      *) continue ;;
    esac
    if [[ -n "${allow}" ]] && ! grep -q '"Mac"' <<<"${allow}"; then
      continue
    fi
    if grep -q '"Mac"' <<<"${deny}"; then
      continue
    fi
    echo "${name}"
  done
}

# Returns 0 when the .uplugin at $2 (in plugin directory $1) needs an editor build.
plugin_needs_build() {
  local plugin_dir="$1" uplugin="$2" name dylib mtime oldest="" oldest_mtime=""
  if ! plutil -p "${uplugin}" >/dev/null 2>&1; then
    return 0
  fi
  while IFS= read -r name; do
    dylib="${plugin_dir}/Binaries/Mac/UnrealEditor-${name}.dylib"
    if [[ ! -f "${dylib}" ]]; then
      return 0
    fi
    mtime="$(stat -f %m "${dylib}")"
    if [[ -z "${oldest}" ]] || (( mtime < oldest_mtime )); then
      oldest="${dylib}"
      oldest_mtime="${mtime}"
    fi
  done < <(editor_modules "${uplugin}")
  if [[ -z "${oldest}" ]]; then
    return 1
  fi
  [[ -n "$(find "${plugin_dir}/Source" "${uplugin}" -newer "${oldest}" -print -quit 2>/dev/null)" ]]
}

# Returns 0 when the .uproject lists the plugin named $1 with "Enabled": false.
plugin_disabled() {
  local name="$1" index=0 listed enabled
  while listed="$(plutil -extract "Plugins.${index}.Name" raw -o - "${PROJECT}" 2>/dev/null)"; do
    if [[ "${listed}" == "${name}" ]]; then
      enabled="$(plutil -extract "Plugins.${index}.Enabled" raw -o - "${PROJECT}" 2>/dev/null || true)"
      if [[ "${enabled}" == "false" ]]; then
        return 0
      fi
      return 1
    fi
    index=$((index + 1))
  done
  return 1
}

# Prints the .uplugin of each enabled project plugin that has Source/. Candidates are the children of
# Plugins/ and of each AdditionalPluginDirectories entry; relative entries resolve against the
# .uproject's directory.
project_source_plugins() {
  local project_dir index=0 entry root dir uplugin name
  local -a roots found
  project_dir="$(cd "$(dirname "${PROJECT}")" && pwd)"
  roots=("${project_dir}/Plugins")
  while entry="$(plutil -extract "AdditionalPluginDirectories.${index}" raw -o - "${PROJECT}" 2>/dev/null)"; do
    index=$((index + 1))
    if [[ "${entry}" == /* ]]; then
      roots+=("${entry}")
    else
      roots+=("${project_dir}/${entry}")
    fi
  done
  shopt -s nullglob
  for root in "${roots[@]}"; do
    for dir in "${root}"/*/; do
      found=("${dir}"*.uplugin)
      if (( ${#found[@]} != 1 )) || [[ ! -d "${dir}Source" ]]; then
        continue
      fi
      uplugin="${found[0]}"
      name="$(basename "${uplugin}" .uplugin)"
      if plugin_disabled "${name}"; then
        continue
      fi
      echo "${uplugin}"
    done
  done
}

build_names=""
while IFS= read -r uplugin; do
  if plugin_needs_build "$(dirname "${uplugin}")" "${uplugin}"; then
    build_names+="${build_names:+, }$(basename "${uplugin}" .uplugin)"
  fi
done < <(project_source_plugins)

if [[ -n "${build_names}" ]]; then
  if [[ ! -x "${BUILD_SH}" ]]; then
    echo "start-unreal-mcp: cannot build project plugins (${build_names}): Build.sh is missing or not executable at ${BUILD_SH} — set UE_ROOT to a UE 5.8 install" >&2
    exit 1
  fi
  echo "start-unreal-mcp: building project plugins (${build_names}) — log ${BUILD_LOG}" >&2
  build_status=0
  "${BUILD_SH}" UnrealEditor Mac Development -Project="${PROJECT}" -TargetType=Editor -NoEngineChanges \
    >"${BUILD_LOG}" 2>&1 || build_status=$?
  if (( build_status != 0 )); then
    first_error="$(grep -m1 'error:' "${BUILD_LOG}" || true)"
    echo "start-unreal-mcp: plugin build failed (exit ${build_status}) — see ${BUILD_LOG}" >&2
    echo "start-unreal-mcp: first error: ${first_error:-no compiler error found}" >&2
    exit "${build_status}"
  fi
fi

# Epic's Unreal MCP server (ModelContextProtocol plugin) binds the port from these flags;
# VibeUE registers its toolsets on that endpoint. This script only launches the editor.
# -unattended suppresses modal dialogs (such as the module rebuild prompt), which would
# otherwise leave the editor hung and the endpoint never listening.
nohup "${UE_EDITOR}" "${PROJECT}" \
  -ModelContextProtocolStartServer \
  -ModelContextProtocolPort="${PORT}" \
  -unattended \
  -log >"${LOG}" 2>&1 &
disown
echo "start-unreal-mcp: launched UE Editor (project ${PROJECT}, port ${PORT}, log ${LOG}, pid $!)"
exit 0
