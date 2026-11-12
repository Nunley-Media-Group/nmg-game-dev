# Defect Report: The Blender test runner repoints the user's Blender add-on link and races across worktrees

**Issue**: #189
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/95-fix-the-always-green-blender-gate-re-import-entry-lookup-notarization-secret-exposure-and-stale-lockfiles/

## Reproduction

1. Create two git worktrees of this repository.
2. Run `scripts/run-blender-tests.sh` in both at the same time.
3. Inspect `nmg_game_dev_blender_addon` in the user's Blender scripts `addons/` directory (on macOS `~/Library/Application Support/Blender/<version>/scripts/addons/`): it points at whichever worktree ran last, and the other run may import add-on code from the wrong checkout.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | Each gate run links the add-on into its own temporary user scripts location, imports the add-on from its own checkout, leaves the user's Blender scripts directory untouched, and removes the temporary location when it exits. |
| **Actual** | `tests/blender/_runner.py` replaces the `nmg_game_dev_blender_addon` symlink in the user's real Blender scripts directory with a link to the current checkout, so every run repoints the user's add-on and concurrent runs in different worktrees overwrite each other's link. |

## Acceptance Criteria

### AC1: Test runs do not touch the user's Blender scripts directory

**Given** the user's Blender add-on link points at some checkout
**When** `scripts/run-blender-tests.sh` runs
**Then** the link in the user's Blender scripts directory is unchanged

### AC2: Each run uses its own add-on location

**Given** two checkouts running `scripts/run-blender-tests.sh` at the same time
**When** both runs enable the add-on
**Then** each run imports the add-on from its own checkout

### AC3: The isolated location is cleaned up

**Given** a finished test run, passing or failing
**When** the runner exits
**Then** the temporary user scripts location it created is removed

### AC4: Existing Blender tests still pass

**Given** the current Blender test suite
**When** `scripts/run-blender-tests.sh` runs
**Then** it passes as before

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `scripts/run-blender-tests.sh` runs Blender with `BLENDER_USER_SCRIPTS` set to a per-run `mktemp -d` directory, overriding any inherited value, removes that directory when the script exits (pass or fail), and still exits with Blender's exit status | Must |
| FR2 | `tests/blender/_runner.py` links the add-on only inside the `BLENDER_USER_SCRIPTS` location and raises without writing anything when `BLENDER_USER_SCRIPTS` is unset or Blender's user scripts `addons` path does not resolve inside it | Must |
| FR3 | Tests cover the isolation: the runner's add-on link resolves under the per-run location, not the user's scripts directory | Must |

## Out of Scope

- Changing how `tests/blender/conftest.py` enables or disables the add-on.
- Isolating Blender's user config, extensions, or Python user site-packages.
- Changes to `scripts/start-blender-mcp.sh` or any other Blender launcher.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #189 | 2026-11-11 | Initial defect report |
