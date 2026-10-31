# ship

`ship` builds a consumer's Unreal project for each platform, runs the quality gates, signs and
notarizes the macOS app, and publishes each artifact to `release/<platform>/`. It is the single entry
point for release builds. The `/ship` skill and the `python -m nmg_game_dev.ship` CLI run the same flow.

## Flow

```
python -m nmg_game_dev.ship <target> --project <uproject> [--release-dir DIR] [--dry-run]

1. Preflight: every required variable for the target's platforms (ship.env_missing)
2. macOS identity: MACOS_SIGNING_IDENTITY, or the Developer ID Application identity for the team
3. Mobile targets only: gate-mobile-budgets over every Mobile/ variant, before any build
4. Per platform, in order:
     build (UAT or the remote Windows build)
     cook-manifest gate (no cross-variant Content/ paths)
     macOS only: codesign, then notarize and staple
     publish the artifact into release/<platform>/
5. Write release/RELEASE-NOTES.md with each artifact and its SHA-256
```

A failing gate or script stops the run and leaves no artifact for that platform. A platform that
already finished keeps its artifact.

## Targets

| Target | Platforms, in order | Notes |
|---|---|---|
| `macos` | macos | `.app`, signed, notarized, stapled |
| `ios` | ios | `.ipa` |
| `android` | android | `.aab` |
| `windows` | windows | Built on a remote host over SSH; `.exe` |
| `desktop` | macos, windows | |
| `mobile` | ios, android | Runs the budget gate first |
| `all` | macos, windows, ios, android | |

## Environment variables

Each target needs its own group. The ship names every missing variable and never prints a value.

| Variable | Needed by | Purpose |
|---|---|---|
| `NOTARIZATION_KEYCHAIN_PROFILE` | macos (recommended) | Name of a profile saved with `xcrun notarytool store-credentials`. notarytool reads the credentials from the keychain, so no secret appears in its arguments. Set it, and the Apple ID and app-specific password are not needed |
| `NOTARIZATION_APPLE_ID` | macos, without the profile | Apple ID for notarytool |
| `NOTARIZATION_APP_SPECIFIC_PASSWORD` | macos, without the profile | App-specific password (never printed). Without the profile it is passed in notarytool's arguments, where it is visible in process arguments while notarytool runs; the ship warns before it submits. Set `NOTARIZATION_KEYCHAIN_PROFILE` to avoid this |
| `NOTARIZATION_TEAM_ID` | macos | Team that owns the signing identity |
| `MACOS_SIGNING_IDENTITY` | optional, macos | Pins the codesign identity by name |
| `IOS_PROVISIONING_PROFILE` | ios | Path to the `.mobileprovision` file |
| `ANDROID_KEYSTORE` | android | Path to the upload keystore |
| `ANDROID_KEYSTORE_PASSWORD` | android | Keystore password. Kept off UAT's command line: written to the project's `Config/UserEngine.ini` for the run only, between `; BEGIN nmg-game-dev ship` and `; END nmg-game-dev ship` markers, and restored afterwards. Every run removes a marked block an interrupted run left behind. In a git repo, a real run stops unless git ignores `Config/UserEngine.ini`: add it to the project's `.gitignore`. Shown as `***` and redacted from UAT output |
| `ANDROID_KEYSTORE_ALIAS` | optional, android | Defaults to `upload` |
| `WINDOWS_BUILD_HOST`, `WINDOWS_BUILD_USER` | windows | SSH target |
| `WINDOWS_BUILD_SSH_KEY` | windows | Path to the SSH private key |
| `WINDOWS_REMOTE_PROJECT_PATH` | windows | Remote `.uproject` path |
| `WINDOWS_UE_ROOT` | optional, windows | Defaults to `C:\Program Files\Epic Games\UE_5.8` |
| `UE_ROOT` | optional | Defaults to `/Users/Shared/Epic Games/UE_5.8` |

## Mobile budget files

Each Mobile variant is `Content/<Category>/<Name>/Mobile/nmg-asset.json`. Finalize writes it.

```json
{ "class": "standard_prop", "tris": 2800, "max_texture_px": 1024, "materials": 1 }
```

`class` is one of `small_prop`, `standard_prop`, `hero_prop`, `character`, or `environment_piece`.
The defaults come from the Mobile column of `docs/asset-contract.md` §6.

A project-root `nmg-budgets.json` overrides individual metrics. Values merge per metric over the
defaults. An unknown class or metric is an error.

```json
{ "standard_prop": { "tris": 5000 } }
```

## Release layout

```
<project dir>/release/
  RELEASE-NOTES.md          target, platforms, each artifact with its SHA-256
  macos/Dogfood.app         signed, notarized, stapled
  ios/Dogfood.ipa
  android/Dogfood.aab
  windows/Dogfood.exe       plus the packaged folder beside it
```

A dry run writes `release/<platform>/DRY-RUN.txt` with the planned commands, and `RELEASE-NOTES.md`
marked as a dry run. It writes no artifact. UAT archives go to `<project dir>/Saved/NmgShip/<platform>/`.

## Dry run and smoke

`--dry-run` sends `--dry-run` to every script. Each script prints `DRY-RUN:` lines, runs no tool, and
exits 0. The ship skips the cook-manifest gate and the artifact copy. `scripts/ship-smoke.sh` runs a
dry-run `all` ship of `fixtures/dogfood.uproject` with placeholder credentials. It needs no Unreal
Engine install.

## Failure codes

| Code | Meaning | Remediation |
|---|---|---|
| `ship.env_missing` | A required variable is unset | Set the named variable |
| `ship.unknown_target`, `ship.project_missing` | Bad target or `--project` path | Fix the argument |
| `ship.mobile_budget_exceeded` | A Mobile variant is over budget | Reduce the asset, or raise the budget |
| `ship.budget_report_missing` | A Mobile folder has no `nmg-asset.json` | Finalize the named asset |
| `ship.budget_report_invalid` | A report is malformed | Rewrite the report |
| `ship.budget_override_invalid` | `nmg-budgets.json` is invalid | Fix or delete the file |
| `ship.signing_identity_missing` | No identity matches the team | Install the certificate or set `MACOS_SIGNING_IDENTITY` |
| `ship.build_failed` | UAT or the remote build failed | Read the log and fix the error |
| `ship.cook_manifest_failed` | Cross-variant `Content/` paths in a package | Fix the cook rules and recook |
| `ship.sign_failed`, `ship.notarize_failed` | Signing or notarization rejected | Read the output |
| `ship.artifact_not_found`, `ship.artifact_ambiguous` | The archive has no single artifact | Rebuild the platform |
| `ship.script_missing` | A `scripts/` file is missing | Restore the scripts directory |
