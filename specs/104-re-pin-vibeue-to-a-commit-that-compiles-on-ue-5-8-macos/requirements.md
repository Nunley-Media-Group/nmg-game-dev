# Defect Report: VibeUE onboarding installs a commit that does not compile on UE 5.8 macOS

**Issue**: #104
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs/

## Reproduction

1. Onboard a consumer project, so that `Plugins/VibeUE` is cloned at tag `v5.0-ue5.8` (commit `bc7bc45c1e2025123778560f45c15d1f8e1be41d`).
2. Run `Build.sh UnrealEditor Mac Development -Project=<uproject> -TargetType=Editor`.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | Onboarding installs VibeUE from its UE 5.8 branch `5-8`, which compiles on UE 5.8 macOS, and the drift check compares against that branch's current head. |
| **Actual** | Onboarding clones tag `v5.0-ue5.8` and requires HEAD to equal `bc7bc45`. That commit fails with `UFoliageService.cpp:44:61: error: loop will run at most once (loop increment never executed) [-Werror,-Wunreachable-code-loop-increment]`. `scripts/install-vibeue.sh` clones the default branch `master`, not the UE 5.8 line. |

## Acceptance Criteria

### AC1: Onboarding installs branch 5-8

**Given** a fresh consumer project
**When** onboarding installs VibeUE
**Then** it runs `git clone --depth 1 --branch 5-8 https://github.com/kevinpbuckley/VibeUE.git Plugins/VibeUE`, and the step reports `installed` with the cloned commit

### AC2: Drift is measured against the 5-8 head, and refresh moves to it

**Given** `Plugins/VibeUE` at a commit other than the current head of `origin` branch `5-8` (for example the old pin `bc7bc45`)
**When** onboarding runs without `--refresh`, then with `--refresh`
**Then** the first run reports `drift` naming both commits, and the `--refresh` run fetches `5-8` and leaves HEAD at that branch head, reporting `refreshed`

### AC3: A current checkout is unchanged, and an unreachable origin is not drift

**Given** `Plugins/VibeUE` at the current `5-8` head, or `git ls-remote` failing
**When** onboarding runs
**Then** it reports `unchanged`. When the remote cannot be reached, the detail says the `5-8` head could not be checked and the checkout is left as is

### AC4: The dogfood installer tracks branch 5-8

**Given** `scripts/install-vibeue.sh` with no clone, or with an existing clone on any branch
**When** it runs
**Then** the clone ends on branch `5-8` at its origin head (a fresh clone uses `--depth 1 --branch 5-8`, and an existing clone is updated fast-forward only), and the script prints the commit

### AC5: No tag or commit pin remains

**Given** the repository after the fix
**When** the toolchain guard tests run
**Then** no VibeUE tag or commit pin (`v5.0-ue5.8`, `bc7bc45…`, `VIBEUE_TAG`, `VIBEUE_COMMIT`) appears in `src/`, `scripts/`, `skills/`, or `docs/`. The installers may name only the branch `5-8`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `src/nmg_game_dev/onboard/unreal.py` replaces `VIBEUE_TAG`/`VIBEUE_COMMIT` with `VIBEUE_BRANCH = "5-8"`, clones that branch, and checks and refreshes against the remote branch head | Must |
| FR2 | `scripts/install-vibeue.sh` clones or updates branch `5-8` instead of the default branch | Must |
| FR3 | `skills/onboard-consumer/references/install-steps.md`, `docs/mcp/unreal.md`, and `docs/onboarding/upgrading.md` describe tracking branch `5-8` | Must |

## Out of Scope

- Changes to VibeUE's own source
- Selecting the VibeUE branch from the installed UE version

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #104 | 2026-10-31 | Initial defect report |
