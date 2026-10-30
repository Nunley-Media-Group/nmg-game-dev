#!/usr/bin/env bash
# Ship smoke (#6, FR11, AC10): a --dry-run "all" ship of fixtures/dogfood.uproject with placeholder
# credentials, into a temp release folder that is removed afterwards. It needs no Unreal Engine and
# runs no build, signing, notarization, or upload tool. Real NOTARIZATION_* and keystore values are
# never read: every credential below is a placeholder.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
release_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$release_dir"
}
trap cleanup EXIT

unset MACOS_SIGNING_IDENTITY
export NOTARIZATION_APPLE_ID="smoke@example.invalid"
export NOTARIZATION_APP_SPECIFIC_PASSWORD="smoke-placeholder"
export NOTARIZATION_TEAM_ID="SMOKE00000"
export IOS_PROVISIONING_PROFILE="smoke.mobileprovision"
export ANDROID_KEYSTORE="smoke.keystore"
export ANDROID_KEYSTORE_PASSWORD="smoke-placeholder"
export WINDOWS_BUILD_HOST="smoke.invalid"
export WINDOWS_BUILD_USER="smoke"
export WINDOWS_BUILD_SSH_KEY="smoke.key"
export WINDOWS_REMOTE_PROJECT_PATH='C:\smoke\dogfood.uproject'

cd "$repo_root"
uv run python -m nmg_game_dev.ship all \
  --project fixtures/dogfood.uproject \
  --release-dir "$release_dir" \
  --dry-run
