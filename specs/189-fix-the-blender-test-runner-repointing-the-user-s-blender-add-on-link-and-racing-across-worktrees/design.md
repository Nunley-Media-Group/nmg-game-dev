# Root Cause Analysis: The Blender test runner repoints the user's Blender add-on link and races across worktrees

**Issue**: #189
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/95-fix-the-always-green-blender-gate-re-import-entry-lookup-notarization-secret-exposure-and-stale-lockfiles/

## Root Cause

The add-on source lives in the hyphenated `plugins/nmg-game-dev-blender-addon/`, so `tests/blender/_runner.py` bridges it to the module id `nmg_game_dev_blender_addon` with a symlink. `_install_addon_link()` places that symlink in `bpy.utils.user_resource("SCRIPTS", path="addons", create=True)`. With no `BLENDER_USER_SCRIPTS` override, that is the user's real per-version Blender scripts directory, shared by the user's interactive Blender and by every checkout on the machine. `scripts/run-blender-tests.sh` `exec`s Blender with the caller's environment unchanged, so nothing scopes the link to one run: each run unlinks the existing symlink when it points elsewhere and links its own checkout. Concurrent runs in different worktrees therefore overwrite each other's link mid-run, and the last run leaves the user's Blender pointed at its worktree.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `scripts/run-blender-tests.sh` | final `exec "${BLENDER}" …` | Launches Blender with the user's real user-resource locations |
| `tests/blender/_runner.py` | `_install_addon_link()` | Writes the add-on symlink into whatever `user_resource('SCRIPTS')` resolves to |

## Fix Strategy

Give each gate run a private user scripts location and make the runner refuse any other target.

1. `scripts/run-blender-tests.sh` creates `user_scripts="$(mktemp -d "${TMPDIR:-/tmp}/nmg-blender-user-scripts.XXXXXX")"`, installs `trap 'rm -rf "${user_scripts}"' EXIT`, and replaces `exec` with `BLENDER_USER_SCRIPTS="${user_scripts}" "${BLENDER}" --background --python-exit-code 1 --python tests/blender/_runner.py -- "${target}" || status=$?` followed by `exit "${status}"` (with `status=0` initialised first). The Blender argv is unchanged. `rm -rf` removes the add-on symlink without following it, so the checkout's add-on source is never deleted. Blender 5.2 resolves `user_resource('SCRIPTS')` from `BLENDER_USER_SCRIPTS`, so every user-scripts path the run touches lives in the temporary directory.
2. `tests/blender/_runner.py` gains `_isolated_addons_dir() -> Path`: it reads `BLENDER_USER_SCRIPTS`, raises `RuntimeError` naming `scripts/run-blender-tests.sh` when it is unset or empty, resolves `bpy.utils.user_resource("SCRIPTS", path="addons")` **without** `create=True`, and raises `RuntimeError` when that resolved path is not inside the resolved `BLENDER_USER_SCRIPTS` directory. Both checks run before any filesystem write. `_install_addon_link()` uses it, then `mkdir(parents=True, exist_ok=True)` and the existing idempotent symlink logic (unchanged).

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `scripts/run-blender-tests.sh` | Per-run `mktemp -d` `BLENDER_USER_SCRIPTS`, `EXIT` trap removal, exit-status pass-through instead of `exec`; header comment documents the isolation | AC1, AC2, AC3, FR1 |
| `tests/blender/_runner.py` | `_isolated_addons_dir()` guard; `_install_addon_link()` links only inside it; docstring updated | AC1, AC2, FR2 |
| `tests/unit/test_run_blender_tests.py` | Shim tests for the per-run directory, its removal, and concurrent runs; a real headless-Blender test that the link and add-on import resolve to the per-run location and this checkout | AC1, AC2, AC3, FR3 |
| `tests/unit/test_blender_runner_isolation.py` | Fake-`bpy` tests of the runner guard | AC1, FR2, FR3 |

## Blast Radius

Only `gate-blender-headless` and the tests that call `scripts/run-blender-tests.sh` (`tests/unit/test_run_blender_tests.py`, via `tests/release_fakes.py` `run_gate`). The existing argv assertions stay valid because the Blender argv is unchanged. Running `_runner.py` directly under Blender without `BLENDER_USER_SCRIPTS` now fails with an actionable error instead of touching the user's scripts directory. Blender's Python user site-packages (where the runner's pytest bootstrap may install) is not under user scripts, so pytest availability is unaffected.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Per-run `BLENDER_USER_SCRIPTS` temp dir plus runner guard | Selected | Smallest change; isolates each run and the user; Blender 5.2 honours the variable |
| Add the checkout to `sys.path` under a snake_case alias instead of linking | Rejected | `addon_utils.enable` discovers add-ons through the scripts `addons` paths, so a path alias alone does not register the module id |
| Lock file serialising runs that share the user directory | Rejected | Still repoints the user's own Blender add-on link (AC1) and serialises parallel gates |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #189 | 2026-11-11 | Initial defect design |
