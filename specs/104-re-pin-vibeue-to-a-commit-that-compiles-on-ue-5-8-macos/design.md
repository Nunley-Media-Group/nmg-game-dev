# Root Cause Analysis: VibeUE onboarding installs a commit that does not compile on UE 5.8 macOS

**Issue**: #104
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs/

## Root Cause

`src/nmg_game_dev/onboard/unreal.py` fixes VibeUE at `VIBEUE_TAG = "v5.0-ue5.8"` and `VIBEUE_COMMIT = "bc7bc45…"`. In that commit, `UFoliageService.cpp`'s `GetOrCreateFoliageActor` returns from inside a `for (TActorIterator…; It; ++It)` loop. VibeUE builds with `bWarningsAsErrors = true`, so Apple Clang's `-Wunreachable-code-loop-increment` fails the editor build. Branch `5-8` already has the fix (`eabe83a`), but the frozen pin never moves to it. `scripts/install-vibeue.sh` clones the default branch `master` instead of the UE 5.8 line.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `src/nmg_game_dev/onboard/unreal.py` | `VIBEUE_TAG`, `VIBEUE_COMMIT`, `_clone`, `ensure_vibeue` | Frozen tag and commit pin |
| `scripts/install-vibeue.sh` | clone and update | Default branch, not 5-8 |
| `skills/onboard-consumer/references/install-steps.md` | `vibeue` row, Drift section | Documents the pin |
| `docs/mcp/unreal.md`, `docs/onboarding/upgrading.md` | VibeUE source | Say "default branch" and "re-pins" |
| `tests/unit/test_toolchain_guards.py` | install-script guards | Forbid `--branch`, expect default branch |

## Fix Strategy

In `onboard/unreal.py`, replace the tag and commit with `VIBEUE_BRANCH: Final = "5-8"`.

- `_clone` runs `git clone --depth 1 --branch 5-8 <url> <target>`. The `onboard.vibeue_clone_failed` message names the branch.
- New `_remote_head(run) -> str | None` runs `git ls-remote <url> refs/heads/5-8` and returns the first field's 40-hex SHA. It returns `None` on non-zero exit or empty output.
- `ensure_vibeue`:
  - Target missing: clone, then return `installed` with `cloned 5-8 (<head12>) into Plugins/VibeUE`.
  - Not a git checkout: as today, `drift`, or with `--refresh` remove it and re-clone.
  - Remote head is `None`: `unchanged`, detail `could not check the 5-8 head (git ls-remote failed); Plugins/VibeUE left at <head12>`.
  - HEAD equals the remote head: `unchanged`.
  - Otherwise: `drift`, detail `Plugins/VibeUE is at <head12>, branch 5-8 is at <remote12>`. With `--refresh`, run `git -C <target> fetch --depth 1 origin 5-8` then `git -C <target> checkout --force FETCH_HEAD`, and return `refreshed`. On failure, `onboard.vibeue_refresh_failed` keeps its remediation.

`scripts/install-vibeue.sh` declares `readonly VIBEUE_BRANCH="5-8"`. A fresh clone uses `git clone --depth 1 --branch "${VIBEUE_BRANCH}"`. For an existing clone, it runs `git -C "${DEST}" fetch --depth 1 origin "${VIBEUE_BRANCH}"`. If the current branch is not `5-8`, it runs `git -C "${DEST}" switch -C "${VIBEUE_BRANCH}" FETCH_HEAD` (this refuses when local changes would be lost). Otherwise it runs `git -C "${DEST}" merge --ff-only FETCH_HEAD`. It prints the short HEAD as today, and exit codes are unchanged.

The toolchain guard keeps rejecting tags, `checkout`, `==`, and `@<digit>` in the install scripts. It allows `--branch` only with the value `5-8` in `install-vibeue.sh`, and it checks `src/`, `scripts/`, `skills/`, and `docs/` for the retired pin strings.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `src/nmg_game_dev/onboard/unreal.py` | Branch tracking via `ls-remote` | AC1–AC3, FR1 |
| `scripts/install-vibeue.sh` | Branch `5-8` clone and update | AC4, FR2 |
| `skills/onboard-consumer/references/install-steps.md`, `docs/mcp/unreal.md`, `docs/onboarding/upgrading.md` | Describe branch tracking | FR3 |
| `tests/unit/onboard/test_unreal.py`, `tests/unit/onboard/test_runner.py`, `tests/onboard_fakes.py`, `tests/bdd/test_onboard_bdd.py`, `tests/bdd/features/onboard_consumer.feature`, `tests/unit/test_toolchain_guards.py` | Updated fakes and assertions | AC1–AC5 |

## Blast Radius

Only the VibeUE onboarding step and the dogfood installer change. Other onboarding steps, their statuses, and the runner report format are unchanged. Consumers already at `bc7bc45` see `drift` once, and `--refresh` moves them to the `5-8` head.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Track branch `5-8` head | Selected | The user's never-pin rule; the branch is VibeUE's UE 5.8 line and already holds the fix |
| Pin commit `eabe83a` | Rejected | A new frozen pin that repeats this defect class |
| Track the default branch `master` | Rejected | Not the UE 5.8 line |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #104 | 2026-10-31 | Initial defect report |
