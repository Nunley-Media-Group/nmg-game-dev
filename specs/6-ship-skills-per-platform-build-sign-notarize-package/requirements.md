# Requirements: Ship skills — per-platform build, sign, notarize, package

**Issue**: #6
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As a** consumer project maintainer shipping an NMG game
**I want** one `ship` command that builds, gates, signs, notarizes, and packages my UE project per platform
**So that** store-ready `.app`, `.ipa`, `.aab`, and Windows `.exe` builds land in `release/<platform>/` and a quality regression stops the ship

## Background

`src/nmg_game_dev/ship/__init__.py` is an empty stub (from #1). This issue fills it with the Python ship orchestrator. It also adds per-platform bash scripts that drive Unreal Automation Tool (UAT), `codesign`, `xcrun notarytool`, and a remote Windows host over `ssh`/`scp`, plus a single `skills/ship/SKILL.md` entry point.

Targets are `macos`, `ios`, `android`, `windows`, and the groups `desktop` (macos + windows), `mobile` (ios + android), and `all`. UE defaults to UE 5.8 (`/Users/Shared/Epic Games/UE_5.8`, overridable with `UE_ROOT`).

Mobile ships run `gate-mobile-budgets` first. It reads a per-asset report, `Content/<Category>/<Name>/Mobile/nmg-asset.json`, and checks it against the mobile budgets in `docs/asset-contract.md` §6. Every platform runs a cook-manifest gate that enforces the split-variant convention: no `Desktop/` content in mobile packages, no `Mobile/` content in desktop packages.

## Acceptance Criteria

### AC1: Ship macOS packages, signs, notarizes, and releases the app

**Given** a consumer project `.uproject`, a `UE_ROOT` containing `Engine/Build/BatchFiles/RunUAT.sh`, and `NOTARIZATION_APPLE_ID`, `NOTARIZATION_APP_SPECIFIC_PASSWORD`, `NOTARIZATION_TEAM_ID` set
**When** `python -m nmg_game_dev.ship macos --project <uproject>` runs
**Then** `RunUAT.sh BuildCookRun` is invoked with `-platform=Mac`, `-clientconfig=Shipping`, `-cook`, `-stage`, `-pak`, `-package`, and `-archive`
**And** the archived `.app` is signed with `codesign --force --deep --options runtime --timestamp --sign <identity>` using the identity resolved for the team
**And** a zip of the `.app` is submitted with `xcrun notarytool submit ... --team-id <team> --wait`, and the `.app` is stapled with `xcrun stapler staple`
**And** the signed `.app` is in `release/macos/`, replacing any `.app` a previous run left there
**And** `release/RELEASE-NOTES.md` lists the artifact with its SHA-256

### AC2: Dry-run ship reports the plan without building

**Given** the same project and notarization variables, and no Unreal Engine installed
**When** `python -m nmg_game_dev.ship macos --project <uproject> --dry-run` runs
**Then** no UAT, `codesign`, `security`, or `xcrun` process runs
**And** the output prints each planned command prefixed with `DRY-RUN:`, including a notarization line that reports a dry-run pass
**And** `release/macos/DRY-RUN.txt` records the planned commands, and the command exits 0

### AC3: Ship mobile produces an .ipa and an .aab

**Given** `IOS_PROVISIONING_PROFILE`, `ANDROID_KEYSTORE`, and `ANDROID_KEYSTORE_PASSWORD` set, and every `Mobile/` folder has a within-budget `nmg-asset.json`
**When** `python -m nmg_game_dev.ship mobile --project <uproject>` runs
**Then** UAT is invoked once with `-platform=IOS` and once with `-platform=Android`
**And** an `.ipa` is in `release/ios/` and an `.aab` is in `release/android/`
**And** the mobile cook-manifest gate passed for both platforms before their artifacts were copied
**And** the Android keystore password never appears in the command output

### AC4: Cook-manifest gate blocks cross-variant leakage

**Given** a mobile platform whose cooked content contains a path under `Content/<Category>/<Name>/Desktop/`
**When** the ship for that platform reaches the cook-manifest gate
**Then** `scripts/verify-cook-manifest.sh --variant mobile` exits 1 and lists the offending path
**And** the ship exits non-zero with remediation text, and no artifact for that platform is in `release/<platform>/`
**And** a desktop platform whose cooked content contains a `Mobile/` path is blocked the same way with `--variant desktop`

### AC5: Windows build runs on the remote host

**Given** `WINDOWS_BUILD_HOST`, `WINDOWS_BUILD_USER`, `WINDOWS_BUILD_SSH_KEY`, and `WINDOWS_REMOTE_PROJECT_PATH` set
**When** `python -m nmg_game_dev.ship windows --project <uproject>` runs
**Then** `ssh -i <key> <user>@<host>` invokes `RunUAT.bat BuildCookRun` with `-platform=Win64` against the remote project path
**And** the remote cooked-file listing passes the desktop cook-manifest gate
**And** the packaged Windows folder is copied back with `scp` so that a `.exe` is in `release/windows/`

### AC6: Mobile budget gate blocks an over-budget asset before any build

**Given** a `Content/Props/Crate/Mobile/nmg-asset.json` with class `standard_prop` and `tris` 4,200 (mobile default 3,000)
**When** `python -m nmg_game_dev.ship mobile --project <uproject>` runs
**Then** `gate-mobile-budgets` fails before any UAT invocation
**And** no build artifact is in `release/ios/` or `release/android/`
**And** the command exits 1 with a remediation naming `Props/Crate`, the metric, the value, the budget, and the overage

### AC7: A Mobile variant without a report fails the budget gate

**Given** a `Content/Props/Lamp/Mobile/` folder with no `nmg-asset.json`
**When** `gate-mobile-budgets` runs
**Then** it fails with code `ship.budget_report_missing` and a remediation telling the developer to finalize `Props/Lamp`

### AC8: Consumer budget overrides apply

**Given** a project-root `nmg-budgets.json` that sets `standard_prop.tris` to 5,000
**When** `gate-mobile-budgets` runs against a `standard_prop` report with `tris` 4,200
**Then** the gate passes

### AC9: Missing prerequisites fail fast without leaking secrets

**Given** a ship target whose required environment variable (for example `NOTARIZATION_TEAM_ID`, `ANDROID_KEYSTORE_PASSWORD`, or `WINDOWS_BUILD_HOST`) is unset, or a macOS ship where no signing identity matches the team
**When** the ship starts
**Then** it exits 1 before any UAT invocation, naming the missing variable or identity in an actionable remediation
**And** no secret value appears in the output

### AC10: Ship smoke dry-run succeeds on the fixture project

**Given** the repository checkout with no Unreal Engine install required
**When** `scripts/ship-smoke.sh` runs
**Then** it runs a `--dry-run` ship of target `all` against `fixtures/dogfood.uproject` with placeholder credentials and exits 0

### AC11: The ship skill is the single Claude Code entry point

**Given** the plugin checkout
**When** `skills/ship/SKILL.md` is loaded
**Then** its frontmatter has `name: ship`, a one-line `description`, `required_mcp: []`, `required_env`, and `unattended_safe: true`
**And** its flow invokes `python -m nmg_game_dev.ship <target>` and documents the targets, `--dry-run`, and the remediation shown on failure

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `python -m nmg_game_dev.ship <target> --project <uproject> [--release-dir DIR] [--dry-run]` accepts `macos`, `ios`, `android`, `windows`, `desktop`, `mobile`, `all`; the release dir defaults to `<project dir>/release` | Must |
| FR2 | Preflight checks every platform's required environment variables before any build step and fails with `ShipError` naming the missing variable | Must |
| FR3 | `scripts/build-macos.sh`, `scripts/build-ios.sh`, `scripts/build-android.sh` invoke `RunUAT.sh BuildCookRun` for their platforms; `scripts/build-windows.sh` invokes `RunUAT.bat` on the remote host over `ssh` and copies the packaged folder back with `scp` | Must |
| FR4 | `scripts/sign-macos.sh` codesigns and verifies the `.app`; `scripts/notarize-macos.sh` zips, submits, requires an `Accepted` status, and staples | Must |
| FR5 | `scripts/verify-cook-manifest.sh --variant desktop|mobile <dir-or-listing>` fails on cross-variant `Content/` paths and lists them | Must |
| FR6 | `gate-mobile-budgets` (`nmg_game_dev.quality.mobile_budgets` + `scripts/audit-mobile-budgets.py`) checks every `Mobile/nmg-asset.json` against §6 mobile defaults merged with `nmg-budgets.json`; a missing report fails | Must |
| FR7 | Mobile targets run `gate-mobile-budgets` before any build; every platform runs the cook-manifest gate before its artifact is copied to `release/<platform>/` | Must |
| FR8 | macOS signing identity resolves from `MACOS_SIGNING_IDENTITY`, else the first `Developer ID Application` identity from `security find-identity -v -p codesigning` whose team matches `NOTARIZATION_TEAM_ID` | Must |
| FR9 | Each platform's release dir is cleared before its new artifact is copied, and `release/RELEASE-NOTES.md` lists target, platforms, artifact paths, SHA-256, and a dry-run marker | Must |
| FR10 | Every script supports `--dry-run`, which prints `DRY-RUN:` commands with secrets shown as `***`, needs no engine or signing binaries, and exits 0; scripts fail with exit 2 and a one-line remediation when a prerequisite is missing | Must |
| FR11 | `scripts/ship-smoke.sh` runs a dry-run `all` ship against `fixtures/dogfood.uproject` | Must |
| FR12 | `skills/ship/SKILL.md` and `docs/skills/ship.md` document the single ship entry point | Must |

## Out of Scope

- Uploading artifacts to App Store Connect or Google Play
- Writing `nmg-asset.json` reports during finalize (#69 / #30)
- Console and Linux targets
- A GitHub Actions workflow job for ship smoke
- Per-step skills for build, sign, or notarize

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #6 | 2026-10-29 | Initial feature spec |
