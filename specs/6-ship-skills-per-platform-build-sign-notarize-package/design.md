# Design: Ship skills — per-platform build, sign, notarize, package

**Issue**: #6
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## Overview

The ship flow uses three layers, following `steering/structure.md` § Ship Flow:

1. **Skill** — `skills/ship/SKILL.md` runs `uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.ship <target> --project <uproject>` and shows the remediation on failure.
2. **Python orchestrator** — `src/nmg_game_dev/ship/` (fills the #1 stub; no new top-level package). Handles target expansion, env preflight, gate ordering, signing-identity resolution, artifact location/copy, and release notes.
3. **Scripts** — `scripts/*.sh` / `scripts/audit-mobile-budgets.py`. Each one talks to exactly one tool (UAT, codesign, notarytool, ssh/scp) and supports `--dry-run`.

The budget-check logic lives in `src/nmg_game_dev/quality/mobile_budgets.py`, beside the existing quality gates.

## Architecture

```
python -m nmg_game_dev.ship <target> --project P [--release-dir R] [--dry-run]
  expand target → ordered platforms (macos, windows, ios, android subset)
  preflight env for every platform           → ShipError ship.env_missing
  if any mobile platform: gate-mobile-budgets → ShipError ship.mobile_budget_exceeded | ship.budget_report_missing
  per platform:
    macos:   build-macos.sh → verify-cook-manifest.sh --variant desktop Saved/Cooked/Mac
             → resolve identity → sign-macos.sh → notarize-macos.sh → copy .app
    ios:     build-ios.sh → verify-cook-manifest.sh --variant mobile Saved/Cooked/IOS → copy .ipa
    android: build-android.sh → verify-cook-manifest.sh --variant mobile Saved/Cooked/Android* → copy .aab
    windows: build-windows.sh (remote UAT, writes cooked listing + scp of archive)
             → verify-cook-manifest.sh --variant desktop <listing> → copy packaged folder
  write release/RELEASE-NOTES.md
```

Groups expand in the fixed order `desktop = [macos, windows]`, `mobile = [ios, android]`, `all = [macos, windows, ios, android]`. Any step failure raises `ShipError` and stops the run; a platform that already finished keeps its release artifact.

Script locations resolve from `Path(__file__).resolve().parents[3] / "scripts"` (the plugin/repo root). `run_ship()` takes `scripts_dir` as a parameter so tests can inject it. Scripts run via `subprocess.run([...], check=False)` with an explicit env. A non-zero exit becomes `ShipError(code=f"ship.{step}_failed")`, carrying the script's stderr remediation line.

### Modules (`src/nmg_game_dev/ship/`)

| Module | Contents |
|--------|----------|
| `__init__.py` | Re-exports `ShipError`, `Target`, `Platform`, `run_ship` |
| `errors.py` | `ShipError(PipelineError)`, with `stage` set to the ship step name |
| `targets.py` | `Platform = Literal["macos","ios","android","windows"]`, `Target` adds `desktop/mobile/all`; `expand_target()`; `REQUIRED_ENV: dict[Platform, tuple[str, ...]]`; `preflight_env(platforms, env)` |
| `identity.py` | `resolve_signing_identity(env, run=subprocess.run, dry_run=False) -> str` per FR8; dry-run returns `"<Developer ID Application for team TEAM>"` without running `security` |
| `artifacts.py` | `PLATFORM_ARTIFACT = {"macos": ".app", "ios": ".ipa", "android": ".aab", "windows": ".exe"}`; `locate_artifact(archive_dir, platform)` (exactly one match, else `ShipError ship.artifact_not_found` / `ship.artifact_ambiguous`); `publish_artifact(src, release_dir, platform)` clears `release/<platform>/` then copies (`.app` bundle via `copytree`; Windows copies the folder containing the `.exe`) |
| `release_notes.py` | `write_release_notes(release_dir, target, entries, dry_run) -> Path`; entries hold platform, relative path, SHA-256 (of the file; for a directory artifact, SHA-256 over sorted relative paths + file bytes) |
| `runner.py` | `run_ship(target, project, release_dir, dry_run, env, scripts_dir) -> list[ReleaseEntry]` composing the flow above |
| `__main__.py` | argparse CLI; on `ShipError` prints `ERROR [<code>]: <message>` and `Remediation: <remediation>` to stderr and exits 1 |

`REQUIRED_ENV`:

| Platform | Variables |
|----------|-----------|
| macos | `NOTARIZATION_APPLE_ID`, `NOTARIZATION_APP_SPECIFIC_PASSWORD`, `NOTARIZATION_TEAM_ID` |
| ios | `IOS_PROVISIONING_PROFILE` |
| android | `ANDROID_KEYSTORE`, `ANDROID_KEYSTORE_PASSWORD` |
| windows | `WINDOWS_BUILD_HOST`, `WINDOWS_BUILD_USER`, `WINDOWS_BUILD_SSH_KEY`, `WINDOWS_REMOTE_PROJECT_PATH` |

Optional: `UE_ROOT` (default `/Users/Shared/Epic Games/UE_5.8`), `WINDOWS_UE_ROOT` (default `C:\Program Files\Epic Games\UE_5.8`), `MACOS_SIGNING_IDENTITY`, `ANDROID_KEYSTORE_ALIAS` (default `upload`). Preflight runs even in dry-run. Error messages name variables, never values.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `python -m nmg_game_dev.ship` | `target`, `--project`, `--release-dir`, `--dry-run` | exit 0; exit 1 + `ERROR [code]` / `Remediation:` on stderr; exit 2 on bad args | FR1, FR2, FR7, FR9 |
| `scripts/build-macos.sh` / `build-ios.sh` / `build-android.sh` | `--project <uproject> --archive <dir> [--dry-run]` | exit 0 / 2 | `"${UE_ROOT}/Engine/Build/BatchFiles/RunUAT.sh" BuildCookRun -project=<p> -platform=<Mac|IOS|Android> -clientconfig=Shipping -build -cook -stage -pak -package -archive -archivedirectory=<dir> -unattended -utf8output -nop4`; iOS adds `-distribution -ini:Engine:[/Script/IOSRuntimeSettings.IOSRuntimeSettings]:MobileProvision=<basename of IOS_PROVISIONING_PROFILE>`; Android adds `-distribution` and `-ini:Engine:[/Script/AndroidRuntimeSettings.AndroidRuntimeSettings]:bEnableBundle=True,KeyStore=<ANDROID_KEYSTORE>,KeyAlias=<alias>,KeyStorePassword=<ANDROID_KEYSTORE_PASSWORD>`, printing the password as `***` |
| `scripts/build-windows.sh` | `--archive <local dir> --listing <file> [--dry-run]` | exit 0 / 2 | `ssh -i KEY -o BatchMode=yes USER@HOST` runs `"<WINDOWS_UE_ROOT>\Engine\Build\BatchFiles\RunUAT.bat" BuildCookRun -project=<WINDOWS_REMOTE_PROJECT_PATH> -platform=Win64 ... -archivedirectory=<remote dir>\Saved\NmgShip`; then `ssh ... cmd /c dir /s /b <remote dir>\Saved\Cooked\Windows` into `--listing`; then `scp -i KEY -r USER@HOST:<remote archive>\Windows <archive>` |
| `scripts/sign-macos.sh` | `<app> --identity <id> [--dry-run]` | exit 0 / 1 / 2 | `codesign --force --deep --options runtime --timestamp --sign "<id>" <app>` then `codesign --verify --strict --verbose=2 <app>` |
| `scripts/notarize-macos.sh` | `<app> [--dry-run]` | exit 0 / 1 / 2 | `ditto -c -k --keepParent <app> <app>.zip`; `xcrun notarytool submit <zip> --apple-id … --password … --team-id … --wait`; exit 1 unless output contains `status: Accepted`; `xcrun stapler staple <app>`; dry-run prints `DRY-RUN: notarization pass (no submission) for team <TEAM>` |
| `scripts/verify-cook-manifest.sh` | `--variant desktop|mobile <dir-or-listing-file>` | exit 0 / 1 / 2 | Collects paths (`find <dir> -type f`, or the file's lines with `\` normalized to `/`); mobile fails on `/Content/(.+/)?Desktop/`, desktop on `/Content/(.+/)?Mobile/`; prints each offending path and a remediation |
| `scripts/audit-mobile-budgets.py` | `--project-root <dir>` | exit 0 / 1 | Thin CLI over `check_mobile_budgets` |
| `nmg_game_dev.quality.mobile_budgets.check_mobile_budgets(project_root)` | project root `Path` | `MobileBudgetAudit` (`passed`, `findings`) | FR6 |
| `scripts/ship-smoke.sh` | none | exit 0 / non-zero | Exports placeholder values for every `REQUIRED_ENV` variable, runs `uv run python -m nmg_game_dev.ship all --project fixtures/dogfood.uproject --release-dir <mktemp dir> --dry-run`, removes the temp dir |

Every bash script uses `#!/usr/bin/env bash` and `set -euo pipefail`. In `--dry-run` mode they skip binary existence checks but still validate their arguments. Outside dry-run, a missing `RunUAT.sh`, `codesign`, `xcrun`, or `ssh` exits 2 with `Remediation:` text.

## Data / Storage Changes

**Per-asset report** `Content/<Category>/<Name>/Mobile/nmg-asset.json` (the schema this issue defines; finalize writes it later):

```json
{ "class": "standard_prop", "tris": 2800, "max_texture_px": 1024, "materials": 1 }
```

`class` ∈ `small_prop | standard_prop | hero_prop | character | environment_piece`. A report that is malformed or missing a key fails with `ship.budget_report_invalid`.

**Mobile defaults** (asset-contract §6), as `DEFAULT_MOBILE_BUDGETS`:

| class | tris | max_texture_px | materials |
|-------|------|----------------|-----------|
| small_prop | 500 | 512 | 1 |
| standard_prop | 3000 | 1024 | 1 |
| hero_prop | 10000 | 2048 | 2 |
| character | 15000 | 2048 | 2 |
| environment_piece | 10000 | 1024 | 3 |

**Override** `<project root>/nmg-budgets.json`: `{ "<class>": { "<metric>": int, ... } }`. Values merge per metric over the defaults; an unknown class or metric fails with `ship.budget_override_invalid`.

**Gate codes**: `ship.mobile_budget_exceeded` (remediation lists `<Category>/<Name>: <metric> <value> > <budget> (+<overage>)` for every violation) and `ship.budget_report_missing` (lists every `Mobile/` folder without a report and says "finalize <Category>/<Name> to write Mobile/nmg-asset.json").

**Release layout**: `release/<platform>/<artifact>`, `release/<platform>/DRY-RUN.txt` (dry-run only), and `release/RELEASE-NOTES.md`. UAT archives go to `<project dir>/Saved/NmgShip/<platform>/`.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Python orchestrator calling single-tool bash scripts | Selected | Matches structure steering (scripts per tool, `ship/` composes) and keeps orchestration unit-testable |
| One bash script doing the whole ship | Rejected | Hard to test the gate ordering and env preflight; duplicates logic across platforms |
| Budget numbers from the in-memory pipeline sidecars | Rejected | Not persisted at ship time; per-asset report chosen in interview |
| Missing report only warns | Rejected | Interview decision: a missing report fails the gate |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #6 | 2026-10-29 | Initial feature design |
