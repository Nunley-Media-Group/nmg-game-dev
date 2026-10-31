---
name: ship
description: Build, gate, sign, notarize, and package the UE project into per-platform artifacts under release/
required_mcp: []
required_env: [UE_ROOT?, NOTARIZATION_KEYCHAIN_PROFILE?, NOTARIZATION_APPLE_ID?, NOTARIZATION_APP_SPECIFIC_PASSWORD?, NOTARIZATION_TEAM_ID, IOS_PROVISIONING_PROFILE, ANDROID_KEYSTORE, ANDROID_KEYSTORE_PASSWORD, ANDROID_KEYSTORE_ALIAS?, WINDOWS_BUILD_HOST, WINDOWS_BUILD_USER, WINDOWS_BUILD_SSH_KEY, WINDOWS_REMOTE_PROJECT_PATH, WINDOWS_UE_ROOT?, MACOS_SIGNING_IDENTITY?]
unattended_safe: true
---

# Ship

Ships a consumer's Unreal project as store-ready builds. One command builds each platform, runs the
quality gates, signs and notarizes the macOS app, and publishes each artifact to `release/<platform>/`
with `release/RELEASE-NOTES.md` listing every artifact and its SHA-256. Use it when the developer asks
to ship, package, or release the game. It is the only entry point for building or signing a release;
do not call UAT, `codesign`, `notarytool`, or `scp` directly.

Each target needs only its own variables. The ship names any that are missing, and it stops before
any build. Never read, print, or echo a secret value. Report variable names only.

## Flow

1. Find the consumer's `.uproject`, and confirm the target: `macos`, `ios`, `android`, `windows`,
   `desktop` (macos and windows), `mobile` (ios and android), or `all`. If the developer names no
   target, ask which one. Do not guess a target that would publish to a store.
2. For a plan without building, run the dry run. It prints each planned command with a `DRY-RUN:`
   prefix and writes `release/<platform>/DRY-RUN.txt`:
   `uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.ship <target> --project <uproject> --dry-run`
3. To ship, run:
   `uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.ship <target> --project <uproject>`
   Add `--release-dir <dir>` only when the developer names one. The release folder defaults to
   `<project dir>/release`.
4. On success, report each artifact path and its SHA-256 from `release/RELEASE-NOTES.md`.
5. On failure, the CLI prints `ERROR [<code>]: <message>` and `Remediation: <remediation>` to stderr
   and exits 1. Show both lines as printed, then stop. Do not retry a build, skip a gate, or publish
   a platform that failed.

## Mobile budgets

Mobile targets run `gate-mobile-budgets` before any build. Each `Content/<Category>/<Name>/Mobile/`
folder needs `nmg-asset.json`, which finalize writes. A project-root `nmg-budgets.json` may override
the defaults per metric. Both formats are described in `docs/skills/ship.md`.

## Failure modes and remediation

- `ship.env_missing`: a required variable is unset. The remediation names it. Ask the developer to set
  it in the environment or in `.claude/settings.local.json`, then rerun.
- `ship.unknown_target`, `ship.project_missing`: the target or `--project` path is wrong. Fix the
  argument and rerun.
- `ship.mobile_budget_exceeded`: a Mobile variant is over budget. The remediation gives the asset, the
  metric, the value, the budget, and the overage. Reduce the mobile asset or raise the budget in
  `nmg-budgets.json`, then rerun. Do not change the budget silently.
- `ship.budget_report_missing`: a Mobile folder has no `nmg-asset.json`. Finalize that asset.
- `ship.budget_report_invalid`, `ship.budget_override_invalid`: a JSON file is malformed. Fix it.
- `ship.signing_identity_missing`: no Developer ID Application identity matches the notarization team.
  The developer installs the certificate or sets `MACOS_SIGNING_IDENTITY`.
- `ship.build_failed`: UAT or the remote build failed. Read the UAT log in the output, fix it, rerun.
- `ship.cook_manifest_failed`: a cooked package contains the other variant's `Content/` paths. Fix the
  cook rules, recook, then rerun. The platform has no artifact.
- `ship.sign_failed`, `ship.notarize_failed`: signing or notarization was rejected. Read the output.
  Do not staple an app that was not accepted.
- `ship.artifact_not_found`, `ship.artifact_ambiguous`, `ship.script_missing`: the archive or the
  scripts directory is wrong. Rerun the build, or restore the scripts directory.

## Test fixtures

- `fixtures/dogfood.uproject`: `scripts/ship-smoke.sh` runs a dry-run `all` ship of it with placeholder
  credentials. It needs no Unreal Engine, and it exits 0 when the ship plan is sound.
