#!/usr/bin/env bash
# Ship smoke (gate-ship-smoke): a --dry-run "all" ship of tests/godot/fixture/project.godot with
# placeholder credentials, into a temp release folder that is removed afterwards. It needs no Godot
# install and runs no Godot, signing, notarization, or upload tool. Real NOTARIZATION_*, iOS, and
# keystore values are never read: every credential below is a placeholder.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
release_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$release_dir"
}
trap cleanup EXIT

unset MACOS_SIGNING_IDENTITY NOTARIZATION_KEYCHAIN_PROFILE ANDROID_KEYSTORE_ALIAS
export NOTARIZATION_APPLE_ID="smoke@example.invalid"
export NOTARIZATION_APP_SPECIFIC_PASSWORD="smoke-placeholder"
export NOTARIZATION_TEAM_ID="SMOKE00000"
export IOS_PROVISIONING_PROFILE="smoke.mobileprovision"
export IOS_TEAM_ID="SMOKE00000"
export ANDROID_KEYSTORE="smoke.keystore"
export ANDROID_KEYSTORE_PASSWORD="smoke-placeholder"

cd "$repo_root"
uv run python -m nmg_game_dev.ship all \
  --project tests/godot/fixture/project.godot \
  --release-dir "$release_dir" \
  --dry-run

for platform in macos windows ios android web; do
  [[ -s "$release_dir/$platform/DRY-RUN.txt" ]] || {
    printf 'ERROR: no DRY-RUN.txt for %s\n' "$platform" >&2
    exit 1
  }
done
