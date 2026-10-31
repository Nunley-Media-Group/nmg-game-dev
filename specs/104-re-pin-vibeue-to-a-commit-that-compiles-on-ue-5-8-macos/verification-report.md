# Verification Report: VibeUE onboarding installs a commit that does not compile on UE 5.8 macOS

**Date**: 2026-10-31
**Issue**: #104
**Reviewer**: Claude Code (nmg-sdlc verify worker)
**Scope**: Implementation verification against spec (defect fix)

**Verification head**: 606994c824fccc39b066cfbc6d2a95ada8bdf031

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 5 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.8 |

### Implementation Status: Pass
**Change type**: defect fix
**Total Issues**: 1 (Low, not blocking)

Onboarding (`src/nmg_game_dev/onboard/unreal.py`) and the dogfood installer (`scripts/install-vibeue.sh`) now track VibeUE branch `5-8`. Onboarding no longer uses the frozen tag `v5.0-ue5.8` / commit `bc7bc45`. Drift is now measured against the `git ls-remote` head of `refs/heads/5-8`. `--refresh` fetches that branch and checks out `FETCH_HEAD`. No retired pin remains in `src/`, `scripts/`, `skills/`, or `docs/`. All five manifest-registered validations passed at the verification head.

---

## Issue Scope

- Active issue: #104
- Spec: `specs/104-re-pin-vibeue-to-a-commit-that-compiles-on-ue-5-8-macos`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5]; FR [FR1, FR2, FR3]; tasks [T001, T002, T003, T004]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":104,"specPath":"specs/104-re-pin-vibeue-to-a-commit-that-compiles-on-ue-5-8-macos","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5"],"functionalRequirements":["FR1","FR2","FR3"],"tasks":["T001","T002","T003","T004"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 104 --spec specs/104-… --base main --controller-run-id 1d8c53d8-6b3c-4e22-a1d5-e8a4c8a68d96`
- Artifact: `.nmg-sdlc/verification/104.json`. Identity: head `606994c824fccc39b066cfbc6d2a95ada8bdf031`, tree clean, spec `sha256:489b92f5…`, steering `sha256:19b4c539…`
- Ceiling: none (`ok: true`)
- Coverage: declared 5, recorded 5, complete `true`; nothing missing, duplicated, or unknown

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Onboarding installs branch 5-8 | Pass | `src/nmg_game_dev/onboard/unreal.py` `_clone` runs `git clone --depth 1 --branch 5-8 <url> <target>`, and `ensure_vibeue` reports `installed` with the cloned short SHA. Test: `tests/unit/onboard/test_unreal.py::test_vibeue_is_cloned_from_branch_5_8` (exact argv and detail); BDD `onboard_consumer.feature` "VibeUE is cloned from branch 5-8 into Plugins/VibeUE" |
| AC2 | Drift against the 5-8 head; refresh moves to it | Pass | `ensure_vibeue` compares HEAD to `_remote_head` (`git ls-remote <url> refs/heads/5-8`, 40-hex validated). The drift detail names both commits. `--refresh` runs `fetch --depth 1 origin 5-8` and `checkout --force FETCH_HEAD` and reports `refreshed`. Tests: `test_vibeue_old_pin_is_drift_naming_both_commits_then_refresh_moves_to_branch_head`, `test_runner.py::test_vibeue_branch_drift_is_repaired_with_refresh` |
| AC3 | Current checkout is unchanged; unreachable origin is not drift | Pass | HEAD equal to the remote head gives `unchanged`. When `ls-remote` fails, the result is `unchanged` with the detail "could not check the 5-8 head (git ls-remote failed); Plugins/VibeUE left at …". Neither case runs a fetch or checkout. Tests: `test_vibeue_at_current_branch_head_is_unchanged`, `test_vibeue_unreachable_origin_is_unchanged_not_drift` |
| AC4 | Dogfood installer tracks branch 5-8 | Pass | `scripts/install-vibeue.sh`: a fresh clone runs `--depth 1 --branch "${VIBEUE_BRANCH}"`. An existing clone runs `fetch origin 5-8`, then `merge --ff-only FETCH_HEAD` when already on 5-8, or else `switch -C 5-8 FETCH_HEAD`. The script prints the commit. **Real run** (scratch dirs, live GitHub): fresh clone → branch `5-8` at `eabe83a`; re-run on the same clone → fast-forward, `eabe83a`; existing clone on `master` (`8828906`) → switched to `5-8` at `eabe83aba0708aeb79ce586f23684417d17cb852`. Static guards: `test_install_vibeue_tracks_only_branch_5_8`, `test_install_vibeue_clones_and_updates_branch_5_8_shallow` |
| AC5 | No tag or commit pin remains | Pass | `grep -rnE 'v5\.0-ue5\.8\|bc7bc45\|VIBEUE_TAG\|VIBEUE_COMMIT' src scripts skills docs` returns no matches. Guard: `test_toolchain_guards.py::test_no_vibeue_tag_or_commit_pin_remains`. `--branch` is allowed only in `install-vibeue.sh`, and only as `"${VIBEUE_BRANCH}"` |

### Reproduction check (defect path)

- Before: the old pin `bc7bc45` is what onboarding cloned. The spec records `UFoliageService.cpp:44:61: error: loop will run at most once … [-Werror,-Wunreachable-code-loop-increment]`.
- After: onboarding and the installer resolve `refs/heads/5-8` = `eabe83aba0708aeb79ce586f23684417d17cb852` (live `git ls-remote`). In that checkout, `Source/VibeUE/Private/PythonAPI/UFoliageService.cpp` `GetOrCreateFoliageActor` uses `if (TActorIterator<…> It(World); It) { return *It; }` and has no `for` loop with an early return. The construct that triggered `-Wunreachable-code-loop-increment` is gone.
- A full UE 5.8 editor build of VibeUE was not run in this verification. No registered validation requires it, and the fix lives upstream on branch `5-8`.

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `VIBEUE_BRANCH: Final = "5-8"` replaces `VIBEUE_TAG`/`VIBEUE_COMMIT`; clone, drift check, and refresh all use the branch |
| FR2 | Pass | `scripts/install-vibeue.sh` `readonly VIBEUE_BRANCH="5-8"`; clone and update target it |
| FR3 | Pass | `skills/onboard-consumer/references/install-steps.md` (vibeue row + Drift section), `docs/mcp/unreal.md` (Setup + Versions), `docs/onboarding/upgrading.md` describe tracking `5-8`; `SKILL.md`, `fixtures/README.md`, CLI `--refresh` help also updated |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Track VibeUE branch 5-8 in onboarding | Complete | `unreal.py` `_remote_head`, `_clone`, `ensure_vibeue` |
| T002 | Track branch 5-8 in the dogfood installer | Complete | `shellcheck -S style scripts/*.sh` exit 0; header comment updated |
| T003 | Update docs | Complete | CHANGELOG Fixed bullet ends `(#104)`. The delivery bump moved it from `[Unreleased]` into `[0.15.3]` |
| T004 | Regression coverage | Complete | `FakeRunner` answers `ls-remote` with a configurable `remote`, or a failure. `BRANCH_HEAD` replaces `PINNED_COMMIT` |

---

## Architecture Assessment (defect path — blast radius)

- **Other callers of the changed path**: `ensure_vibeue` is called only by the onboarding runner (`install`). `_remote_head` is new and private. `scripts/install-vibeue.sh` is used only for dogfood fixtures.
- **Public contract change**: the module constants `VIBEUE_TAG`/`VIBEUE_COMMIT` were removed and `VIBEUE_BRANCH` added. Repo-wide grep finds no remaining importers. The step statuses (`installed`/`unchanged`/`drift`/`refreshed`) and error codes (`onboard.vibeue_clone_failed`, `onboard.vibeue_refresh_failed`) are unchanged. Detail strings changed wording, as the spec requires.
- **Silent data changes**: `--refresh` still uses `checkout --force`, as it did before, so local edits inside `Plugins/VibeUE` are discarded on refresh only. Without `--refresh`, nothing is modified. When the remote is unreachable, nothing is modified.
- **Minimal-change check**: the diff is limited to the VibeUE onboarding and installer code, its tests, docs, and the delivery commit's version bump (`VERSION`, `plugin.json`, `blender_manifest.toml`, `.uplugin`, CHANGELOG). There are no unrelated refactors.

| Area | Score | Notes |
|------|-------|-------|
| SOLID | 5 | `_remote_head` has a single responsibility, and git access goes through the injected `Runner` |
| Security | 5 | Fixed HTTPS URL. Argv lists are used, so there is no shell interpolation. The remote SHA is validated against `[0-9a-f]{40}` before use. No secrets are involved |
| Performance | 5 | One `ls-remote` per re-run. Fetches are shallow on the onboarding path |
| Testability | 5 | Every branch is covered through `FakeRunner`, including the `ls-remote` failure |
| Error Handling | 4 | Clone and refresh failures raise structured `OnboardError` with a remediation, and an unreachable origin degrades to `unchanged` with an explicit detail. One Low finding is listed below |

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps / Test | Passes |
|---------------------|-------------|-----------|--------|
| AC1 (SCN001) | Yes | `tests/bdd/features/onboard_consumer.feature` + `test_onboard_bdd.py`; `test_unreal.py` | Yes |
| AC2 (SCN002) | Yes | `test_unreal.py`, `test_runner.py` | Yes |
| AC3 (SCN003) | Yes | `test_unreal.py` (two tests) | Yes |
| AC4 (SCN004) | Yes | `test_toolchain_guards.py` (two tests) + real installer run | Yes |
| AC5 (SCN005) | Yes | `test_toolchain_guards.py::test_no_vibeue_tag_or_commit_pin_remains` | Yes |

All five scenarios are tagged `@regression`.

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. The diff doesn't touch nmg-sdlc `workflows/` or `agents/`. The plugin load is covered by the registered `plugin.validate` and `plugin.session-smoke` validations |

---

## Steering Doc Verification Gates (manifest-registered)

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` (`uv run pytest tests/unit tests/bdd -q`) | Pass | command exited 0 |
| `repository.lint` (`uv run ruff check .`) | Pass | command exited 0 |
| `repository.types` (`uv run mypy src tests`) | Pass | command exited 0 |
| `plugin.validate` (`claude plugin validate .`) | Pass | command exited 0 |
| `plugin.session-smoke` (`project.plugin-session-smoke`) | Pass | plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

Supplementary check: `shellcheck -S style scripts/*.sh` exited 0, because the diff touches `scripts/install-vibeue.sh`.

**Gate Summary**: 5/5 passed, 0 failed, 0 incomplete

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | No fixes were needed | — | — |

## Remaining Issues

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `src/nmg_game_dev/onboard/unreal.py` (`ensure_vibeue`, refreshed return) |
| **Issue** | The `refreshed` detail reports the SHA from `ls-remote`, not the HEAD actually checked out from `FETCH_HEAD` |
| **Impact** | The SHA in the message can be stale only if someone pushes to `5-8` between `ls-remote` and `fetch`, which takes seconds. The checkout itself is still correct: it is the branch head |
| **Reason Not Fixed** | Cosmetic, and outside the verify publication scope, which allows only the report |

---

## Positive Observations

- An unreachable origin is reported as `unchanged`, not `drift`, so offline re-runs don't nag.
- The installer comment explains why the update fetch is not depth 1: the ff-only merge would otherwise refuse unrelated histories.
- The guard tests keep the no-pin rule strict and allow only the one branch name.

## Recommendations Summary

### Before PR (Must)
- [x] None

### Long Term (Could)
- [ ] Report the post-checkout `rev-parse HEAD` in the `refreshed` detail

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `src/nmg_game_dev/onboard/unreal.py` | 1 (Low) | |
| `src/nmg_game_dev/onboard/__main__.py` | 0 | help text |
| `scripts/install-vibeue.sh` | 0 | real-run verified |
| `skills/onboard-consumer/SKILL.md`, `references/install-steps.md` | 0 | |
| `docs/mcp/unreal.md`, `docs/onboarding/upgrading.md`, `fixtures/README.md` | 0 | |
| `tests/onboard_fakes.py`, `tests/unit/onboard/test_unreal.py`, `tests/unit/onboard/test_runner.py`, `tests/bdd/*`, `tests/unit/test_toolchain_guards.py` | 0 | |
| `CHANGELOG.md`, `VERSION`, manifests | 0 | delivery bump 0.15.3 |

---

## Recommendation

**Ready for PR**

All five ACs, three FRs, and four tasks are satisfied. All five scenarios have passing tests. The live installer run confirms the clone, fast-forward, and branch-switch paths land on the `5-8` head, which no longer contains the construct that failed the build. All five registered validations passed at `606994c824fccc39b066cfbc6d2a95ada8bdf031`.
