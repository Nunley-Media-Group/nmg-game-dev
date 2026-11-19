---
name: ship
description: Gate, export, sign, notarize, and package the consumer's Godot project into per-platform artifacts under release/
required_mcp: []
required_env: [GODOT_BIN?, NOTARIZATION_KEYCHAIN_PROFILE?, NOTARIZATION_APPLE_ID?, NOTARIZATION_APP_SPECIFIC_PASSWORD?, NOTARIZATION_TEAM_ID, MACOS_SIGNING_IDENTITY?, IOS_PROVISIONING_PROFILE, IOS_TEAM_ID, ANDROID_KEYSTORE, ANDROID_KEYSTORE_PASSWORD, ANDROID_KEYSTORE_ALIAS?]
unattended_safe: true
---

# Ship

Ships a consumer's Godot project (`game/project.godot`) as store-ready builds. One command checks
every script, runs the project tests and the mobile budget gate, exports each platform headless
with Godot's export presets, signs and notarizes the macOS app, and writes each artifact to
`release/<platform>/` with `release/RELEASE-NOTES.md` listing every artifact and its SHA-256. Use it
when the developer asks to ship, package, export, or release the game. It is the only entry point
for building or signing a release; do not call `godot --export-release`, `codesign`, or
`notarytool` directly.

Each target needs only its own variables. Windows and web need none. The ship names any that are
missing and stops before any export. Never read, print, or echo a secret value. Report variable
names only.

## Flow

1. Find the consumer's `game/project.godot`, and confirm the target: `macos`, `ios`, `android`,
   `windows`, `web`, `desktop` (macos and windows), `mobile` (ios and android), or `all` (every
   platform). If the developer names no target, ask which one. Do not guess a target that would
   publish to a store.
2. For a plan without exporting, run the dry run. It prints each planned command with a `DRY-RUN:`
   prefix (secrets as `***`), runs no Godot, and writes `release/<platform>/DRY-RUN.txt`:
   `uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.ship <target> --project game/project.godot --dry-run`
3. To ship, run:
   `uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.ship <target> --project game/project.godot`
   Add `--release-dir <dir>` only when the developer names one. The release folder defaults to
   `release/` at the consumer root, beside `game/`.
   Pass `--bump major|minor|patch` or `--version X.Y.Z` only when the developer names a version
   bump or a version. The two flags are mutually exclusive. With neither, the project's current
   version ships unchanged. Pass the same flags to the dry run.
4. On success, report each artifact path and its SHA-256 from `release/RELEASE-NOTES.md`, the
   version it ships, and any `WARNING [ship.web_pack_large]` line.
5. On failure, the CLI prints `ERROR [<code>]: <message>` and `Remediation: <remediation>` to stderr
   and exits 1. Show both lines as printed, then stop. Do not retry an export, skip a gate, or
   publish a platform that failed.

Before any export the ship runs, in order: `godot --import` (a fresh clone has no `.godot/` class
cache until it runs), `godot --check-only` on every `.gd` file (skipping `.godot/`),
`game/tests/run_tests.gd` when it exists, the headless autoplay smoke run, and the mobile budget gate
for `ios`, `android`, and `web`. The smoke run starts the game headless for 600 frames with
`--nmg-autoplay --nmg-test-saves` and fails on any `SCRIPT ERROR`, `Parse Error`, or `ERROR:` line,
a non-zero exit, or a run past its timeout, so a game that crashes on its main scene never ships. Mobile and web presets exclude every `Desktop/` asset folder; desktop presets
exclude every `Mobile/` folder. Godot comes from `GODOT_BIN`, then `godot` on PATH, then
`/Applications/Godot.app`.

## Build version and changelog

Every ship names a version, and the player sees it. Before any Godot command, the ship resolves
the version and checks the consumer's root `CHANGELOG.md` (the folder above `game/`) for a
`## X.Y.Z` section (`## [X.Y.Z]` and a trailing date also count) with at least one line of text for
players. The ship refuses to start without that section, so no build goes out that players cannot
read about. After the gates and before the first export, the version is written to
`application/config/version` in `game/project.godot` and to every export preset: macOS and iOS get
`application/short_version` and `application/version`, Android gets `version/name` and a
`version/code` one higher, and Windows gets `application/file_version` and
`application/product_version` as `X.Y.Z.0`. Only those lines change. The game reads its version at
run time through `NmgBuild.version()` or an `NmgVersionLabel` node from the add-on.

`release/RELEASE-NOTES.md` is headed with the version and carries the changelog section under
`## Changes`, each gate that ran with its result under `## Gates`, and the artifact SHA-256 table
under `## Artifacts`. The ship never writes `CHANGELOG.md`; the developer writes the player text.

## Mobile budgets

Each `game/assets/<Category>/<Name>/Mobile/` folder needs `nmg-asset.json`, which finalize writes. A
consumer-root `nmg-budgets.json` may override the defaults per metric. Both formats are described in
`docs/skills/ship.md`.

## Failure modes and remediation

- `ship.env_missing`: a required variable is unset. The remediation names it. Ask the developer to
  set it in the environment or in `.claude/settings.local.json`, then rerun.
- `ship.unknown_target`, `ship.project_missing`: the target or `--project` path is wrong. Fix the
  argument and rerun.
- `ship.version_invalid`: `--version` is not `X.Y.Z`, both `--bump` and `--version` were given, or
  `application/config/version` in `game/project.godot` is not `X.Y.Z`. Fix the value and rerun.
- `ship.version_not_increased`: `--version` is not greater than the current version. Pick a higher
  version, or use `--bump`. Nothing was written. When `--version` equals the current version, an
  earlier ship already wrote it and then stopped: rerun with no version flag to ship it.
- A failure after the gates (export, signing, notarization) leaves the new version written to
  `game/project.godot` and the presets, which is intended because that version has not shipped
  yet. Fix the failure and rerun with no `--bump` or `--version`; a version flag would skip past an
  unshipped version.
- `ship.version_missing`: the project declares no `application/config/version` and no flag names
  one. Ask the developer for the first version, then rerun with `--version X.Y.Z`.
- `ship.changelog_missing`: `CHANGELOG.md` at the consumer root has no `## X.Y.Z` section for the
  version being shipped, or the section is blank. Ask the developer to write the player-facing
  entry, then rerun. Do not write the entry yourself. No Godot command ran.
- `ship.presets_missing`, `ship.preset_missing`: `game/export_presets.cfg` is missing or lacks the
  platform's preset. Run `/onboard-consumer --refresh`, then rerun.
- `godot.not_found`: no Godot binary. Install Godot 4 (latest stable) or set `GODOT_BIN`.
- `ship.import_failed`: `godot --import` failed or printed an `ERROR:` line. The message names the
  first error. Fix or remove that resource and rerun.
- `ship.script_check_failed`: a script does not parse. The message names the file. Fix it and rerun.
- `ship.tests_failed`: `game/tests/run_tests.gd` reported a failure. Fix the test or the game code.
- `ship.smoke_failed`: the headless smoke run failed. The message names the smoke code
  (`smoke.runtime_error` or `smoke.timeout`) and the first error lines. Fix the reported error in the
  game, then rerun. Reproduce it by running the game in Godot. No export ran.
- `ship.mobile_budget_exceeded`: a Mobile variant is over budget. The remediation gives the asset,
  the metric, the value, the budget, and the overage. Reduce the mobile asset or raise the budget in
  `nmg-budgets.json`, then rerun. Do not change the budget silently.
- `ship.budget_report_missing`: a Mobile folder has no `nmg-asset.json`. Finalize that asset.
- `ship.budget_report_invalid`, `ship.budget_override_invalid`: a JSON file is malformed. Fix it.
- `ship.signing_identity_missing`: no Developer ID Application identity matches the notarization
  team. The developer installs the certificate or sets `MACOS_SIGNING_IDENTITY`.
- `ship.ios_profile_invalid`: `security cms` could not read a UUID from `IOS_PROVISIONING_PROFILE`.
  Point it at a valid `.mobileprovision` file.
- `ship.export_failed`, `ship.artifact_not_found`: the Godot export failed or wrote nothing. Read the
  Godot output; usually the platform's export templates are missing (Editor > Manage Export
  Templates) or the preset's signing settings are wrong.
- `ship.sign_failed`, `ship.notarize_failed`: signing or notarization was rejected. Read the output.
  Do not staple an app that was not accepted.
- `ship.script_missing`: the plugin's `scripts/` directory is incomplete. Restore it.
- `ship.web_pack_large` (warning, not a failure): the web `index.pck` is over 38 MB. Tell the
  developer; large packs load slowly in browsers.

## Test fixtures

- `tests/godot/fixture/project.godot`: `scripts/ship-smoke.sh` runs a dry-run `all` ship of it with
  placeholder credentials. It needs no Godot install, and it exits 0 when the ship plan is sound.
