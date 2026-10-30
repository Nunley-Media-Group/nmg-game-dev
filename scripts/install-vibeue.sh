#!/usr/bin/env bash
# install-vibeue.sh — Clone or update the VibeUE Unreal plugin for the dogfood fixture.
#
# Usage:  scripts/install-vibeue.sh [plugins_dir]
#
# Default plugins_dir is <repo>/fixtures/Plugins. Clones VibeUE's default branch at depth 1
# into <plugins_dir>/VibeUE, or fast-forwards an existing clone. VibeUE is never pinned to a
# version: it tracks its latest release, and scripts/smoke-unreal-mcp.py verifies it.
#
# Exit: 0 installed or updated (prints the checked-out commit); 2 git missing or clone/update failed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

readonly VIBEUE_REPO_URL="https://github.com/kevinpbuckley/VibeUE.git"
readonly PLUGINS_DIR="${1:-${REPO_ROOT}/fixtures/Plugins}"
readonly DEST="${PLUGINS_DIR}/VibeUE"

if ! command -v git >/dev/null 2>&1; then
  echo "install-vibeue: git not found on PATH. Install Xcode Command Line Tools (xcode-select --install) or git, then re-run." >&2
  exit 2
fi

mkdir -p "${PLUGINS_DIR}"

if [[ -d "${DEST}/.git" ]]; then
  echo "install-vibeue: updating existing clone at ${DEST} (fast-forward only)"
  if ! git -C "${DEST}" pull --ff-only --quiet; then
    echo "install-vibeue: fast-forward update of ${DEST} failed. Resolve local changes in that clone, or delete it and re-run." >&2
    exit 2
  fi
else
  echo "install-vibeue: cloning ${VIBEUE_REPO_URL} into ${DEST} (depth 1, default branch)"
  if ! git clone --depth 1 --quiet "${VIBEUE_REPO_URL}" "${DEST}"; then
    echo "install-vibeue: clone of ${VIBEUE_REPO_URL} failed. Check network access, or remove a non-git ${DEST} and re-run." >&2
    exit 2
  fi
fi

commit="$(git -C "${DEST}" rev-parse --short HEAD)"
echo "install-vibeue: VibeUE ready at ${DEST} (commit ${commit})"
