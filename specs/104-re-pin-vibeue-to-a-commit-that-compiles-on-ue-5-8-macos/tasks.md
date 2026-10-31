# Tasks: VibeUE onboarding installs a commit that does not compile on UE 5.8 macOS

**Issue**: #104
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs/

## Implementation Tasks

### T001: Track VibeUE branch 5-8 in onboarding

**File(s)**: `src/nmg_game_dev/onboard/unreal.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `VIBEUE_TAG` and `VIBEUE_COMMIT` are gone, and `VIBEUE_BRANCH = "5-8"` exists.
- A fresh install runs `git clone --depth 1 --branch 5-8 https://github.com/kevinpbuckley/VibeUE.git <consumer>/Plugins/VibeUE` and reports `installed` (AC1).
- HEAD different from the `git ls-remote … refs/heads/5-8` head reports `drift` naming both commits. `--refresh` runs `fetch --depth 1 origin 5-8` and `checkout --force FETCH_HEAD` and reports `refreshed` (AC2).
- HEAD equal to the remote head, or a failed `ls-remote`, reports `unchanged` with the documented detail (AC3).

### T002: Track branch 5-8 in the dogfood installer

**File(s)**: `scripts/install-vibeue.sh`
**Type**: Modify
**Depends**: none
**Acceptance**:
- A fresh clone uses `git clone --depth 1 --branch "${VIBEUE_BRANCH}"` with `VIBEUE_BRANCH="5-8"`. An existing clone is fetched and switched (`switch -C`) or fast-forwarded (`merge --ff-only FETCH_HEAD`) to `5-8`, and the script prints the commit (AC4, FR2).
- The header comment says VibeUE tracks branch `5-8`'s head. The script passes `shellcheck -S style`.

### T003: Update docs

**File(s)**: `skills/onboard-consumer/references/install-steps.md`, `docs/mcp/unreal.md`, `docs/onboarding/upgrading.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- The `vibeue` install row shows the `--branch 5-8` clone and drift against the branch head. The Drift section and `upgrading.md` say `--refresh` moves VibeUE to the `5-8` head. `docs/mcp/unreal.md` says VibeUE comes from branch `5-8` (FR3).
- None of these files names `v5.0-ue5.8` or `bc7bc45` (AC5).
- `CHANGELOG.md` `[Unreleased]` has a Fixed bullet that ends with `(#104)`.

### T004: Regression coverage

**File(s)**: `tests/unit/onboard/test_unreal.py`, `tests/unit/onboard/test_runner.py`, `tests/onboard_fakes.py`, `tests/bdd/test_onboard_bdd.py`, `tests/bdd/features/onboard_consumer.feature`, `tests/unit/test_toolchain_guards.py`
**Type**: Modify
**Depends**: T001, T002, T003
**Acceptance**:
- The fake runner answers `git ls-remote` with a configurable `5-8` head (default `eabe83aba0708aeb79ce586f23684417d17cb852`) or a failure. `PINNED_COMMIT` is replaced by that head constant.
- `test_unreal.py` covers AC1 (clone argv with `--branch 5-8`), AC2 (`bc7bc45` HEAD → `drift`, then `--refresh` issues fetch `origin 5-8` and `checkout --force FETCH_HEAD` → `refreshed`), and AC3 (equal head → `unchanged`; `ls-remote` failure → `unchanged` with the could-not-check detail).
- `test_runner.py` and the onboarding BDD scenario expect the `--branch 5-8` clone. The feature step reads "VibeUE is cloned from branch 5-8 into Plugins/VibeUE".
- `test_toolchain_guards.py` allows `--branch 5-8` only in `install-vibeue.sh`, still rejects tags, `checkout`, `==`, and `@<digit>`, and asserts AC5 over `src/`, `scripts/`, `skills/`, and `docs/`. `pytest tests/unit tests/bdd` passes.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #104 | 2026-10-31 | Initial defect tasks |
