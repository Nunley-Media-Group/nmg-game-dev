# Verification Report: Bake each tiling material in isolation so the asset does not occlude its AO

**Date**: 2026-11-18
**Issue**: #240
**Reviewer**: Claude (nmg-sdlc verify worker, gate phase)
**Scope**: Implementation verification against spec

**Verification head**: 092a239dd6b872c3d42d2c044d748c4cf4ceb7e5

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 5 |
| Testability | 5 |
| Error Handling | 5 |
| **Overall** | 5.0 |

### Implementation Status: Pass
**Total Issues**: 0 above info (1 info note from review)

The tiling bake now runs every channel bake inside `tiling.isolated(tile)`, which hides every scene object but the temporary bake tile and restores each object's `hide_render` in a `finally`. The bake cache version moved to `"2"` in both the add-on cache and the finalize step cache, so stale tiling bakes miss. The review passed at `d550e3a` with only one info note. This gate ran every applicable registered validation once at the queue head `092a239`, which has the default branch integrated and the version prepared. All of them passed.

Deterministic steering artifact: `.nmg-sdlc/verification/240.json` (generated 2026-11-19T02:30:19Z), identity head `092a239dd6b872c3d42d2c044d748c4cf4ceb7e5`, tree clean. Ceiling: none. Coverage: declared 11, recorded 11, complete, no missing, duplicate or unknown entries.

---

## Issue Scope

- Active issue: #240
- Spec: `specs/240-bake-each-tiling-material-in-isolation-so-the-asset-does-not-occlude-its-ao`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4]; FR [FR1, FR2, FR3, FR4, FR5]; tasks [T001, T002, T003]; scenarios [SCN001, SCN002, SCN003, SCN004]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":240,"specPath":"specs/240-bake-each-tiling-material-in-isolation-so-the-asset-does-not-occlude-its-ao","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5"],"tasks":["T001","T002","T003"],"scenarios":["SCN001","SCN002","SCN003","SCN004"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Acceptance Criteria Verification

The evidence comes from the review record `.nmg-sdlc/verification/240-review.json` (reviewed head `d550e3a`). The gate run executed those tests at `092a239`. No criterion's tests mock the path under test (`mockedEntryPoints: []`).

| AC | Description | Status | Exercised | Evidence |
|----|-------------|--------|-----------|----------|
| AC1 | Asset geometry does not occlude the tiling bake | Pass | real entry point | `bake_core/core.py:314` wraps image creation and every `bake.bake_channel` in `tiling.isolated(tile)`. `tiling.py:52-67` hides every object but the tile. `tests/blender/test_bake_tiling.py` SCN001 drives `bake_asset` on the Reproduction collection, records the render-visible objects for each real `bake_channel` call (only the tile), and asserts that every Desktop and Mobile texture passes the seam check. It passed in `gate-blender-headless`. |
| AC2 | Tiling AO depends only on the material | Pass | real entry point | SCN002 bakes the plane alone and then the plane with the box through `bake_asset`, and asserts that the mean ORM red difference is at most 0.02. It passed in `gate-blender-headless`. |
| AC3 | Scene state is restored after the bake | Pass | real entry point | `test_scn003_tiling_bake_restores_scene_state[success\|not_seamless]` (`test_bake_tiling.py:343-380`) asserts that `hide_render`, the scene, the view layer, the world and AO distance 0.37 are unchanged and that no `__nmg_bake_tile` object or mesh is left. `:383-424` also checks that the visibility flags are restored when a raise happens inside the isolation. Passed in `gate-blender-headless`. |
| AC4 | Related behaviour is preserved | Pass | real entry point | The diff only adds tests, and no existing test changed. The seam rule and its thresholds are unchanged. The existing suites passed: `repository.tests` (1724 passed, 14 skipped, including `tiling_seam_check.feature`) and `gate-blender-headless` (395 passed, 4 skipped). |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `tiling.py:59-61` sets `hide_render = (obj != tile)` for every scene object, independent of the world AO distance. |
| FR2 | Pass | `isolated()` snapshots and restores the flags in `finally`. In `core.py`, the tile-removal `finally` sits outside the `with` block, so the flags are restored before the tile is removed, on success and on failure. |
| FR3 | Pass | `bake_core/cache.py` `BAKE_VERSION = "2"`. `pipeline/steps.py` `_BAKE_VERSION = "2"` is part of the bake `settings_hash`. A unit test pins that the two values match and that the key changed. |
| FR4 | Pass | `tests/blender/test_bake_tiling.py` SCN001–SCN003 bake the Reproduction collection (`bake_fixtures.add_tiling_occluder`). |
| FR5 | Pass | The tiling bullet in `docs/skills/bake-materials.md:55-58` documents the isolation. `docs/mcp/finalize.md:345-348` documents the bake version in the cache key. |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Bake each tiling material on an isolated tile | Complete | `tiling.isolated`, `core.py` wiring, and `BAKE_VERSION` bumps in the add-on and the pipeline step cache |
| T002 | Document tile isolation | Complete | `docs/skills/bake-materials.md`, `docs/mcp/finalize.md`, CHANGELOG |
| T003 | Add Blender headless regression tests | Complete | `tests/blender/test_bake_tiling.py` (+152), `tests/blender/bake_fixtures.py` (+35), `tests/unit/pipeline/test_steps.py` (+34) |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Isolation is one context manager in `tiling.py`, and `core.py` only composes it. |
| Open/Closed | 5 | The change is additive: the seam rule and the channel bake are untouched. |
| Liskov Substitution | 5 | Not applicable beyond preserved call contracts. |
| Interface Segregation | 5 | `isolated(tile)` takes only the tile. |
| Dependency Inversion | 5 | The pipeline mirrors the bake version as a constant, and a test pins it so it cannot drift. |

### Layer Separation

The fix stays inside the step-implementation layer (`bake_core/`). The pipeline layer changes only its cache key (`steps.py`), as `steering/snippets/project-structure.md` requires.

### Dependency Flow

There is no new cross-layer import. `steps.py` mirrors `BAKE_VERSION` instead of importing add-on code into the host package.

---

## Security Assessment

- [x] Authentication: not applicable
- [x] Authorization: not applicable
- [x] Input validation: not applicable (no new external input)
- [x] Injection prevention: not applicable
- [x] Data protection: no credentials or secrets touched

## Performance Assessment

- [x] Async patterns: not applicable
- [x] Caching: the cache key now includes the bake version, so stale tiling bakes rebake once
- [x] Resource management: the temporary tile and its mesh are removed on every path, and the visibility snapshot is O(objects)
- [x] Query optimization: not applicable

## Error Handling

The design paths DP1–DP4 pass in review:

- DP1: success restore.
- DP2: a raise inside the isolation restores the flags before the tile is removed. A test covers it.
- DP3: a `not_seamless` failure restores scene state.
- DP4: an object deleted while isolated is skipped on restore.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (Blender headless) | Yes |
| AC2 | Yes (SCN002) | Yes (Blender headless) | Yes |
| AC3 | Yes (SCN003) | Yes (Blender headless) | Yes |
| AC4 | Yes (SCN004) | Existing suites | Yes |

### Coverage Summary

- Feature files: 4 scenarios in `feature.gherkin`. Tests live in `tests/blender/test_bake_tiling.py`.
- Step definitions: Implemented
- Unit tests: `tests/unit/pipeline/test_steps.py` adds the bake-version cache-key tests
- Test execution: Pass

---

## Steering Doc Verification Gates

Tier: pre-merge. No validation declares a `tier`, so every required validation was evaluated (`tier: null`, `selection: null`). No validation recorded a heavy-pool slot.

| Gate | Tier / Selection | Status | Evidence |
|------|------------------|--------|----------|
| repository.tests | null / null | Pass | `uv run pytest tests/unit tests/bdd -q`: 1724 passed, 14 skipped |
| repository.lint | null / null | Pass | `uv run ruff check .`: All checks passed |
| repository.format | null / null | Pass | `uv run ruff format --check .`: 418 files already formatted |
| repository.types | null / null | Pass | `uv run mypy src tests`: no issues in 265 source files |
| gate-blender-headless | null / null | Pass | `scripts/run-blender-tests.sh`: 395 passed, 4 skipped |
| gate-ue-compile | null / null | Pass | `project.ue-compile`: DogfoodEditor compiled against UE 5.8. It applies because the version bump touches `nmg-game-dev.uplugin`. |
| gate-mcp-schema | null / null | Not applicable | No `mcp-servers/**` change |
| gate-shellcheck | null / null | Not applicable | No `scripts/**.sh` change |
| gate-ship-smoke | null / null | Not applicable | No ship-path change |
| plugin.validate | null / null | Pass | `claude plugin validate .`: passed (with warnings) |
| plugin.session-smoke | null / null | Pass | Plugin loaded via `--plugin-dir`, and `nmg-game-dev:blender` connected |

**Gate Summary**: 8/8 applicable gates passed, 0 failed, 0 incomplete (3 not applicable)

### Gate diagnosis before the green run

`gate-ue-compile` failed in two earlier runs at this same head. Both failures were host-environment problems, and neither was a source defect:

1. The worktree had no `fixtures/Plugins/VibeUE`, which steering lists as a host prerequisite (UBT: "Unable to find plugin 'VibeUE'"). I installed it with `scripts/install-vibeue.sh` into the gitignored `fixtures/Plugins/`.
2. Clang segfaulted inside UBA's `libUbaDetours.dylib` during the first VibeUE build, which left a corrupt shared PCH ("input is not a PCH file"). I deleted the gitignored `fixtures/Intermediate`, `fixtures/Binaries` and the VibeUE build products. A direct `Build.sh DogfoodEditor` probe through the heavy pool then compiled cleanly in 671 s.

The registered runner was then re-run in full against the unchanged head and recorded every result above. No source, steering or spec file changed, and the tree stayed clean throughout.

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | Environment | `fixtures/Plugins/VibeUE` (gitignored) | VibeUE host prerequisite missing in the worktree | Installed it with `scripts/install-vibeue.sh` | direct |
| — | Environment | `fixtures/Intermediate` (gitignored) | Corrupt shared PCH left by a clang segfault inside UBA | Deleted the build output and rebuilt | direct |

No source changes were made in the gate phase.

## Remaining Issues

None above info.

- **Info (review F1)**: The review read the Blender headless tests for AC1–AC3 and DP2 but did not run them. This gate ran them in `gate-blender-headless` at the exact head, and they passed, which resolves the note.

---

## Positive Observations

- Isolation is a single context manager with a snapshot-and-restore `finally`, and the `finally` that removes the tile is ordered after it.
- The failure-path test compares the flags at the moment isolation exits, so another restore cannot mask a missing one.
- A unit test pins that the pipeline's copy of the bake version matches the add-on value.

---

## Recommendations Summary

### Before PR (Must)
- None

### Short Term (Should)
- Mark `gate-ue-compile` `heavy` in `steering/manifest.json`, so that cold UE builds take a heavy-pool slot instead of competing with other worktrees' builds.

### Long Term (Could)
- None

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| plugins/nmg-game-dev-blender-addon/bake_core/tiling.py | 0 | `isolated()` |
| plugins/nmg-game-dev-blender-addon/bake_core/core.py | 0 | Isolation wiring |
| plugins/nmg-game-dev-blender-addon/bake_core/cache.py | 0 | `BAKE_VERSION = "2"` |
| src/nmg_game_dev/pipeline/steps.py | 0 | `_BAKE_VERSION` in the bake settings hash |
| tests/blender/test_bake_tiling.py | 0 | SCN001–SCN003 plus the failure-path isolation test |
| tests/blender/bake_fixtures.py | 0 | `add_tiling_occluder` |
| tests/unit/pipeline/test_steps.py | 0 | Cache-key tests |
| docs/skills/bake-materials.md, docs/mcp/finalize.md, CHANGELOG.md | 0 | Docs |

---

## Recommendation

**Ready for PR**

Every acceptance criterion and functional requirement passes through its real entry point. The review left no finding above info, and every applicable registered pre-merge validation passed at `092a239dd6b872c3d42d2c044d748c4cf4ceb7e5`, with coverage complete.
