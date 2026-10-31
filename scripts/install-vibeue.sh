#!/usr/bin/env bash
# install-vibeue.sh — Clone or update the VibeUE Unreal plugin for the dogfood fixture.
#
# Usage:  scripts/install-vibeue.sh [plugins_dir]
#
# Default plugins_dir is <repo>/fixtures/Plugins. VibeUE tracks its UE 5.8 branch, 5-8, and never
# a tag or commit. A fresh clone is depth 1 on that branch, and an existing clone is moved to
# origin's 5-8 head: fast-forward when it is already on 5-8, otherwise switched to it.
# scripts/smoke-unreal-mcp.py verifies the result.
#
# Exit: 0 installed or updated (prints the checked-out commit); 2 git missing or clone/update failed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

readonly VIBEUE_REPO_URL="https://github.com/kevinpbuckley/VibeUE.git"
readonly VIBEUE_BRANCH="5-8"
readonly PLUGINS_DIR="${1:-${REPO_ROOT}/fixtures/Plugins}"
readonly DEST="${PLUGINS_DIR}/VibeUE"

if ! command -v git >/dev/null 2>&1; then
  echo "install-vibeue: git not found on PATH. Install Xcode Command Line Tools (xcode-select --install) or git, then re-run." >&2
  exit 2
fi

mkdir -p "${PLUGINS_DIR}"

if [[ -d "${DEST}/.git" ]]; then
  echo "install-vibeue: updating existing clone at ${DEST} to branch ${VIBEUE_BRANCH}"
  # Not --depth 1: a depth-1 fetch leaves FETCH_HEAD with no parents, so the ff-only merge below
  # would refuse as unrelated histories. A plain fetch deepens the clone far enough to connect.
  if ! git -C "${DEST}" fetch --quiet origin "${VIBEUE_BRANCH}"; then
    echo "install-vibeue: fetch of branch ${VIBEUE_BRANCH} into ${DEST} failed. Check network access to github.com, then re-run." >&2
    exit 2
  fi
  current="$(git -C "${DEST}" symbolic-ref --quiet --short HEAD || true)"
  if [[ "${current}" = "${VIBEUE_BRANCH}" ]]; then
    if ! git -C "${DEST}" merge --ff-only --quiet FETCH_HEAD; then
      echo "install-vibeue: fast-forward of ${DEST} to branch ${VIBEUE_BRANCH} failed. Resolve local changes in that clone, or delete it and re-run." >&2
      exit 2
    fi
  elif ! git -C "${DEST}" switch --quiet -C "${VIBEUE_BRANCH}" FETCH_HEAD; then
    echo "install-vibeue: switching ${DEST} to branch ${VIBEUE_BRANCH} failed. Commit or discard local changes in that clone, or delete it and re-run." >&2
    exit 2
  fi
else
  echo "install-vibeue: cloning ${VIBEUE_REPO_URL} branch ${VIBEUE_BRANCH} into ${DEST} (depth 1)"
  if ! git clone --depth 1 --quiet --branch "${VIBEUE_BRANCH}" "${VIBEUE_REPO_URL}" "${DEST}"; then
    echo "install-vibeue: clone of branch ${VIBEUE_BRANCH} from ${VIBEUE_REPO_URL} failed. Check network access, or remove a non-git ${DEST} and re-run." >&2
    exit 2
  fi
fi

commit="$(git -C "${DEST}" rev-parse --short HEAD)"
echo "install-vibeue: VibeUE ready at ${DEST} (branch ${VIBEUE_BRANCH}, commit ${commit})"
