# ship

`ship` exports a consumer's Godot project for each platform, runs the quality gates first, signs and
notarizes the macOS app, and writes each artifact to `release/<platform>/`. It is the single entry
point for release builds. The `/ship` skill and the `python -m nmg_game_dev.ship` CLI run the same
flow. Every Godot call is headless (`godot --headless --path game ...`); no editor is opened.

## Flow

```
python -m nmg_game_dev.ship <target> --project game/project.godot [--release-dir DIR] [--dry-run]

1. Preflight: the target, game/project.godot, game/export_presets.cfg with each platform's preset,
   every required variable (ship.env_missing), and the macOS signing identity
2. godot --import, so a fresh clone has its class cache and imports         (ship.import_failed)
3. godot --check-only -s res://<path> for every .gd file, skipping .godot/   (ship.script_check_failed)
4. godot -s res://tests/run_tests.gd, when that file exists                   (ship.tests_failed)
5. ios, android, web: the mobile budget gate over game/assets/**/Mobile/      (also in a dry run)
6. Per platform, in order:
     ios: patch the iOS preset's team and provisioning-profile UUID, restore it afterwards
     android: --install-android-build-template when game/android/build/ is missing
     godot --export-release "<preset>" release/<platform>/<artifact>          (ship.export_failed)
     macos: sign-macos.sh, then notarize-macos.sh (notarize and staple)
     web: WARNING [ship.web_pack_large] when index.pck is over 38 MB
7. Write release/RELEASE-NOTES.md with each artifact and its SHA-256
```

The import runs first because `game/.godot/` is git-ignored: on a fresh clone or CI checkout Godot
has no global class cache yet, so `--check-only` would fail on any script that names a `class_name`
type.

A failing gate or export stops the run and leaves no artifact for that platform. A platform that
already finished keeps its artifact. Godot is resolved from `GODOT_BIN`, then `godot` on PATH, then
`/Applications/Godot.app/Contents/MacOS/Godot` (`godot.not_found` otherwise).

## Targets

| Target | Platforms, in order | Godot preset | Artifact |
|---|---|---|---|
| `macos` | macos | `macOS` | `<App>.app`, signed, notarized, stapled |
| `windows` | windows | `Windows Desktop` | `<App>.exe` with the pack embedded; exported locally |
| `ios` | ios | `iOS` | `<App>.ipa` |
| `android` | android | `Android` | `<App>.aab` (Gradle build) |
| `web` | web | `Web` | the `web/` folder with `index.html`; Compatibility renderer, no threads |
| `desktop` | macos, windows | | |
| `mobile` | ios, android | | |
| `all` | macos, windows, ios, android, web | | |

`<App>` is the project's `application/config/name` with every non-alphanumeric character removed,
or `Game` when that leaves nothing. The presets come from `game/export_presets.cfg`, which
`/onboard-consumer` writes. Mobile and web presets exclude `assets/*/Desktop/*`; desktop presets
exclude `assets/*/Mobile/*`, so a package never carries the other variant. Install Godot's export
templates for each platform (Editor > Manage Export Templates) before a real ship.

## Environment variables

Each target needs its own group. Windows and web need none. The ship names every missing variable
and never prints a value.

| Variable | Needed by | Purpose |
|---|---|---|
| `GODOT_BIN` | optional | Path to the Godot 4 executable |
| `NOTARIZATION_KEYCHAIN_PROFILE` | macos (recommended) | Name of a profile saved with `xcrun notarytool store-credentials`. notarytool reads the credentials from the keychain, so no secret appears in its arguments. Set it, and the Apple ID and app-specific password are not needed |
| `NOTARIZATION_APPLE_ID` | macos, without the profile | Apple ID for notarytool |
| `NOTARIZATION_APP_SPECIFIC_PASSWORD` | macos, without the profile | App-specific password (never printed). Without the profile it is passed in notarytool's arguments, where it is visible in process arguments while notarytool runs; the ship warns before it submits. Set `NOTARIZATION_KEYCHAIN_PROFILE` to avoid this |
| `NOTARIZATION_TEAM_ID` | macos | Team that owns the signing identity |
| `MACOS_SIGNING_IDENTITY` | optional, macos | Pins the codesign identity by name |
| `IOS_PROVISIONING_PROFILE` | ios | Path to the `.mobileprovision` file. Its UUID is read with `security cms -D -i` |
| `IOS_TEAM_ID` | ios | App Store team id written into the iOS preset for the export |
| `ANDROID_KEYSTORE` | android | Path to the upload keystore |
| `ANDROID_KEYSTORE_PASSWORD` | android | Keystore password. Passed to Godot only in the export's own environment as `GODOT_ANDROID_KEYSTORE_RELEASE_PASSWORD`; never on a command line, never printed (shown as `***`) |
| `ANDROID_KEYSTORE_ALIAS` | optional, android | Defaults to `upload` |

The iOS preset is patched only for the export: `export_presets.cfg` is restored byte-for-byte
afterwards, even when the export fails, so the team id and profile UUID never land in git.

## Mobile budget files

Each Mobile variant is `game/assets/<Category>/<Name>/Mobile/nmg-asset.json`. Finalize writes it.

```json
{ "class": "standard_prop", "tris": 2800, "max_texture_px": 1024, "materials": 1 }
```

`class` is one of `small_prop`, `standard_prop`, `hero_prop`, `character`, `environment_piece`, or
`terrain`. The defaults come from the Mobile column of `docs/asset-contract.md` §6. Other keys
finalize writes (such as `meshes`) are ignored by the gate.

A terrain variant's file holds `heightmap_px`, `layers`, and `max_texture_px` in place of `tris` and
`materials`. `layers` is the layer count:

```json
{ "class": "terrain", "heightmap_px": 1009, "layers": 3, "max_texture_px": 1024 }
```

A consumer-root `nmg-budgets.json` (beside `game/`) overrides individual metrics. Values merge per
metric over the defaults. An unknown class or metric is an error.

```json
{ "standard_prop": { "tris": 5000 } }
```

For `terrain`, the metrics are `heightmap_px`, `layers`, and `max_texture_px`. A `heightmap_px`
override must be 127, 253, 505, 1009, 2017, or 4033:

```json
{ "terrain": { "heightmap_px": 505, "layers": 2 } }
```

`scripts/audit-mobile-budgets.py --project-root <consumer>` runs the same gate on its own.

## Release layout

```
<consumer root>/release/
  RELEASE-NOTES.md          target, platforms, each artifact with its SHA-256
  macos/MyGame.app          signed, notarized, stapled
  windows/MyGame.exe
  ios/MyGame.ipa
  android/MyGame.aab
  web/index.html            plus index.js, index.wasm, index.pck; hashed as one folder
```

A dry run writes `release/<platform>/DRY-RUN.txt` with the planned commands, and `RELEASE-NOTES.md`
marked as a dry run. It writes no artifact and leaves earlier artifacts in place.

## Dry run and smoke

`--dry-run` prints every Godot, `security`, sign, and notarize command with a `DRY-RUN:` prefix and
secrets as `***`. It runs no Godot and sends `--dry-run` to the sign and notarize scripts, which run
no tool. The mobile budget gate still runs, because it only reads files. `scripts/ship-smoke.sh`
(`gate-ship-smoke`) runs a dry-run `all` ship of `tests/godot/fixture/project.godot` with placeholder
credentials. It needs no Godot install.

## Failure codes

| Code | Meaning | Remediation |
|---|---|---|
| `ship.env_missing` | A required variable is unset | Set the named variable |
| `ship.unknown_target`, `ship.project_missing` | Bad target or `--project` path | Fix the argument |
| `ship.presets_missing`, `ship.preset_missing` | `export_presets.cfg` or a platform preset is missing | Run `/onboard-consumer --refresh` |
| `godot.not_found` | No Godot binary | Install Godot 4 or set `GODOT_BIN` |
| `ship.import_failed` | `godot --import` exited non-zero or printed an `ERROR:` line | Fix or remove the named resource |
| `ship.script_check_failed` | A `.gd` file does not parse | Fix the named script |
| `ship.tests_failed` | `game/tests/run_tests.gd` failed | Fix the failing test |
| `ship.mobile_budget_exceeded` | A Mobile variant is over budget. A terrain variant reports each over-budget metric | Reduce the asset, or raise the budget |
| `ship.budget_report_missing` | A Mobile folder has no `nmg-asset.json` | Finalize the named asset |
| `ship.budget_report_invalid` | A report is malformed | Rewrite the report |
| `ship.budget_override_invalid` | `nmg-budgets.json` is invalid | Fix or delete the file |
| `ship.signing_identity_missing` | No identity matches the team | Install the certificate or set `MACOS_SIGNING_IDENTITY` |
| `ship.ios_profile_invalid` | No UUID in the provisioning profile | Point `IOS_PROVISIONING_PROFILE` at a valid profile |
| `ship.export_failed` | `godot --export-release` exited non-zero | Read the Godot output; install export templates, fix the preset |
| `ship.artifact_not_found` | The export exited 0 but wrote no artifact | Read the Godot output; install export templates |
| `ship.sign_failed`, `ship.notarize_failed` | Signing or notarization rejected | Read the output |
| `ship.script_missing` | A `scripts/` file is missing | Restore the scripts directory |
| `ship.web_pack_large` | Warning: the web `index.pck` is over 38 MB | Trim web content; the build still ships |
