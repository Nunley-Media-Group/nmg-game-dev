# Defect Report: Always-green Blender gate, re-import entry lookup, notarization secret exposure, and stale lockfiles

**Issue**: #95
**Date**: 2026-10-30
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/6-ship-skills-per-platform-build-sign-notarize-package/

## Reproduction

1. Make one test under `tests/blender/` fail, run `scripts/run-blender-tests.sh`, and observe exit code 0.
2. Copy (do not symlink) `plugins/nmg-game-dev-blender-addon` into a Blender extensions folder outside the repo, run the re-import check, and observe `reimport.entry_missing`.
3. Run `scripts/notarize-macos.sh <app>` with a shimmed `xcrun` that records its arguments, and observe the app-specific password in the recorded argv.
4. Run `uv lock --check` in `mcp-servers/finalize` and observe that it fails. Change `VERSION`, run the release bump, and observe that all three lockfiles fail `uv lock --check`.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | The Blender gate exits non-zero when any Blender test fails or errors. The re-import check finds `scripts/blender/contract_entry.py` through `CLAUDE_PLUGIN_ROOT`, then through the add-on's own checkout. Notarization with `NOTARIZATION_KEYCHAIN_PROFILE` keeps every secret out of process arguments. A `VERSION` change leaves all three lockfiles in sync. |
| **Actual** | The gate always exits 0. A copied add-on raises `reimport.entry_missing`. The app-specific password is in notarytool's argv. Every version bump stales `uv.lock`, `mcp-servers/finalize/uv.lock` and `mcp-servers/texture-gen/uv.lock`, and both sub-locks are already stale on main. |

## Acceptance Criteria

### AC1: Blender gate fails on a failing test

**Given** a Blender test under `tests/blender/` that fails or errors
**When** `scripts/run-blender-tests.sh` runs
**Then** it exits non-zero, and it exits 0 when every Blender test passes

### AC2: Re-import resolves the entry script outside a checkout

**Given** an add-on copy that is not inside a framework checkout, and `CLAUDE_PLUGIN_ROOT` pointing at a framework root that contains `scripts/blender/contract_entry.py`
**When** the re-import check starts
**Then** it runs that entry script instead of raising `reimport.entry_missing`

### AC3: Re-import keeps the checkout fallback and a clear error

**Given** `CLAUDE_PLUGIN_ROOT` is unset, or names a root without the entry script
**When** the re-import check starts from the add-on inside a framework checkout
**Then** it uses the checkout's entry script; and when neither location has it, it raises `reimport.entry_missing` with a remediation that names `CLAUDE_PLUGIN_ROOT`

### AC4: Notarization with a keychain profile keeps secrets out of argv

**Given** `NOTARIZATION_KEYCHAIN_PROFILE` is set
**When** `scripts/notarize-macos.sh <app>` runs
**Then** notarytool is called with `--keychain-profile <profile>` and without `--apple-id` or `--password`, and `NOTARIZATION_APPLE_ID` and `NOTARIZATION_APP_SPECIFIC_PASSWORD` are not required

### AC5: The password path still works and warns

**Given** `NOTARIZATION_KEYCHAIN_PROFILE` is unset, and the Apple ID, app-specific password and team ID are set
**When** `scripts/notarize-macos.sh <app>` runs
**Then** it submits as before, keeps masking the password in its log, and prints a warning that the password is visible in process arguments and that `NOTARIZATION_KEYCHAIN_PROFILE` avoids it

### AC6: A version bump leaves every lockfile in sync

**Given** the committed `uv.lock`, `mcp-servers/finalize/uv.lock` and `mcp-servers/texture-gen/uv.lock`
**When** `VERSION` changes to a new semver value
**Then** `uv lock --check` passes in the repo root and in both MCP sub-projects without relocking, and the installed `nmg-game-dev` package reports the new version

### AC7: Lock drift is caught by a test

**Given** a lockfile that is out of sync with its `pyproject.toml`
**When** the unit test suite runs
**Then** a test fails and names the project whose lock needs `uv lock`

### AC8: Existing behavior is preserved

**Given** the existing Blender, re-import, ship and MCP server tests
**When** the full test suite runs and the `finalize` and `texture-gen` MCP servers are resolved as a consumer launches them
**Then** they pass and start as before, and `--dry-run` notarization still submits nothing

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `scripts/run-blender-tests.sh` propagates Blender test failures and errors as a non-zero exit code | Must |
| FR2 | The add-on's re-import check resolves `scripts/blender/contract_entry.py` from `CLAUDE_PLUGIN_ROOT` first, then from its own checkout. The `reimport.entry_missing` remediation names `CLAUDE_PLUGIN_ROOT` | Must |
| FR3 | `scripts/notarize-macos.sh` uses `--keychain-profile` when `NOTARIZATION_KEYCHAIN_PROFILE` is set. Otherwise it keeps the Apple ID and password path and prints the visibility warning. The macOS ship preflight accepts the profile in place of the Apple ID and password. `docs/skills/ship.md` documents the variable and recommends it | Must |
| FR4 | The `nmg-game-dev` package version is derived from `VERSION`, so no lockfile records a value that a bump changes. The steering versioning table no longer lists `pyproject.toml` `project.version` | Must |
| FR5 | `mcp-servers/finalize` and `mcp-servers/texture-gen` are relocked so both match the current root dependencies | Must |
| FR6 | A unit test runs `uv lock --check` for the root and each `mcp-servers/*` project | Must |

## Out of Scope

- Changing how the Python package (`src/nmg_game_dev/contract`, `pipeline`) locates `scripts/blender/`; it runs from the framework install.
- Removing the Apple ID and password notarization path.
- The `test_coexistence.py` assertion, the `JSONDecodeError` path in `texture/batch.py`, the docstring wrapping in `onboard/runner.py`, the missing steering gate scripts, and the markdownlint config.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #95 | 2026-10-30 | Initial defect report |
