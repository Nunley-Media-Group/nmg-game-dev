# Verification Report: Tiling seam check rejects high-frequency textures that tile correctly

**Date**: 2026-11-11
**Issue**: #147
**Reviewer**: Claude (nmg-sdlc verify worker, architecture-reviewer)
**Scope**: Implementation verification against spec (defect fix)

**Verification head**: a82841e5a732dc8e13bcb7f5c90075c89eaff751

---

## Executive Summary

The bake seam check now judges each wrap against the texture's own interior adjacent-pixel difference (`max(1.5 × interior, 2/255)`) through a new bpy-free `bake_core/seam_metric.py`. texture-gen's `is_seamless` uses the same definition, and a new `python -m nmg_game_dev.texture seamless` subcommand makes an existing PNG tile. Every acceptance criterion maps to code and passing tests. All applicable registered validations passed at the verification head.

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
**Verification type**: defect fix
**Total Issues**: 2 (both Low, not blocking)

---

## Issue Scope

- Active issue: #147
- Spec: `specs/147-fix-the-tiling-seam-check-rejecting-high-frequency-textures-that-tile-correctly`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5, AC6, AC7]; FR [FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9]; tasks [T001, T002, T003, T004, T005, T006, T007, T008]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005, SCN006, SCN007]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":147,"specPath":"specs/147-fix-the-tiling-seam-check-rejecting-high-frequency-textures-that-tile-correctly","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/147.json` (generated 2026-11-11T22:44:27Z, head `a82841e5a732dc8e13bcb7f5c90075c89eaff751`, clean tree)
- Coverage: declared 11, recorded 11, complete `true`; no missing, duplicate, or unknown ids
- Ceiling: none (`ok: true`)

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 985 passed, 9 skipped |
| `repository.lint` | Pass | `uv run ruff check .`: All checks passed |
| `repository.format` | Pass | `uv run ruff format --check .`: 312 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: no issues in 199 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 181 passed (includes `tests/blender/test_bake_tiling.py`) |
| `gate-ue-compile` | Pass | DogfoodEditor compiled against UE 5.8 (applies only because the version bump touched `nmg-game-dev.uplugin` `VersionName`) |
| `gate-mcp-schema` | Not applicable | No `mcp-servers/**` change |
| `gate-shellcheck` | Not applicable | No `scripts/**.sh` change |
| `gate-ship-smoke` | Not applicable | No ship path change |
| `plugin.validate` | Pass | `claude plugin validate .` exited 0 (existing LICENSE/icon directory warnings only) |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 8/8 applicable gates passed, 0 failed, 0 incomplete (3 not applicable)

**gate-ue-compile diagnosis.** The first two runs of the gate runner at this same head recorded `gate-ue-compile` as failed. The first failure was a link error (`LINKEDIT content 'symbol table strings' extends beyond end of segment` on VibeUE objects). The second was `input is not a PCH file` with UBA session-server segmentation faults that referenced paths in another checkout. Both runs overlapped with UnrealBuildTool builds from other lane worktrees. A direct diagnostic `Build.sh DogfoodEditor` succeeded. The full runner was then rerun once while no other lane's UnrealBuildTool was running, and every gate passed. #147 changes no UE source.

---

## Acceptance Criteria Verification

Reproduction re-executed against the fixed code (old absolute rule vs new relative rule, same images):

| Image | Old wrap error | Old verdict (≤ 0.04) | New verdict | Detail |
|-------|----------------|----------------------|-------------|--------|
| Periodic busy noise (AC1) | 0.068 | fail (the bug) | pass | wrap 0.068 vs interior 0.069 |
| Non-periodic crop (AC2) | 0.134 | fail | fail | wrap 0.134 vs interior 0.024 |
| Smooth 0–0.03 ramp (AC3) | 0.030 | pass (the bug) | fail | wrap 0.030 vs interior 0.000 |
| Constant / near-flat uint8 (AC4) | 0.000 / 0.003 | pass | pass | allowed = floor 0.008 |
| `make_seamless(white noise u8)` (AC5) | 0.291 | fail (the bug) | pass | wrap 0.291 vs interior 0.246 |

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Exactly tileable busy texture passes | Pass | `bake_core/seam_metric.py` `_axis`/`passes`; `tests/unit/texture/test_seam_metric.py::test_ac1_*`; BDD SCN001; Blender `test_ac1_periodic_fine_noise_tiling_material_bakes_seamless` |
| AC2 | Real wrap discontinuity on a busy texture fails and names the channel | Pass | `bake_core/tiling.py` `check_seams` + `seam_metric.failure_detail`; `test_ac2_*`; BDD SCN002; Blender `test_ac2_non_periodic_material_fails_not_seamless` |
| AC3 | Visible seam on a smooth texture fails | Pass | Relative ratio with the 2/255 floor; `test_ac3_*`; BDD SCN003 |
| AC4 | Flat and near-flat textures pass with no division by zero | Pass | `allowed = max(ratio × interior, SEAM_FLOOR)` (no division); `failure_detail` divides by `allowed ≥ 2/255`; `test_ac4_*` runs under `np.errstate(divide="raise", invalid="raise")`; BDD SCN004 |
| AC5 | texture-gen output bakes without edits | Pass | `test_ac5_make_seamless_output_passes_the_bake_metric`; Blender `test_ac5_make_seamless_output_bakes_without_edits` (SCN005) |
| AC6 | Bake and texture-gen agree | Pass | `src/nmg_game_dev/texture/seamless.py` `is_seamless` with the same `_normalize`, `SEAM_RATIO`, `SEAM_FLOOR`; `test_ac6_*` asserts equal constants and identical verdicts on a 48-image corpus (8-bit/float, RGB/single-channel) holding both outcomes; BDD SCN006 |
| AC7 | Error and docs describe the measure and a fix | Pass | `tiling.py` message reports `<kind> wrap X vs interior Y` per failing channel plus the 1.5x / 0.008 rule; `errors.py` `REASONS["not_seamless"]` names `python -m nmg_game_dev.texture seamless`; `docs/skills/bake-materials.md`, `docs/asset-contract.md` §4, `docs/onboarding/texture-models.md`; `test_ac7_*`; BDD SCN007 also runs the CLI |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `seam_metric._axis`: wrap = mean abs(last − first), interior = mean abs(`np.diff`), pass when `wrap <= max(1.5 × interior, 2/255)`; a channel fails when either axis fails |
| FR2 | Pass | `seam_metric.normalize` divides integer dtypes by `np.iinfo(...).max` |
| FR3 | Pass | `seamless.is_seamless` same definition; parity test `test_ac6_*` |
| FR4 | Pass | Unit, BDD and Blender regressions listed above |
| FR5 | Pass | Unit and Blender `make_seamless` coverage |
| FR6 | Pass | Per-channel wrap/interior in the message; remediation names the subcommand |
| FR7 | Pass | `__main__.py` `seamless` subcommand; `tests/unit/texture/test_cli.py` covers in place, `--out` (nested parent created, input unchanged), and missing input (exit 1, `ERROR [texture.input_missing]`, `Remediation:`) |
| FR8 | Pass | Three docs updated |
| FR9 | Pass | `not_seamless` reason kept; `check_seams` still returns `dict[str, float]` (max wrap per channel); sole caller `core._pack` ignores the return value |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Shared bpy-free seam metric | Complete | `bake_core/seam_metric.py` (numpy + stdlib only) |
| T002 | Correct bake seam check and remediation | Complete | `SEAM_TOLERANCE` removed; message as designed |
| T003 | Align texture-gen `is_seamless` | Complete | `seam_mad`, `interior_mad`, `make_seamless` signatures unchanged |
| T004 | `seamless` CLI subcommand | Complete | |
| T005 | Docs | Complete | |
| T006 | Unit regression and parity | Complete | `tests/texture_fakes.py` generators + `load_bake_core`; `test_seam_metric.py`; `test_cli.py` |
| T007 | BDD acceptance | Complete | `tests/bdd/features/tiling_seam_check.feature` (SCN001–004, 006, 007) |
| T008 | Blender bake regression | Complete | `noise_image` fixture; absolute 0.04 assertions replaced by `seam_metric.passes` |

---

## Architecture Assessment (defect path: blast radius)

- **Other callers of the changed path**: `bake_core/core.py` `_pack` is the only caller of `tiling.check_seams`; it relies only on the `not_seamless` reason and ignores the return value. `is_seamless` callers (`tests/unit/texture/test_seamless.py`, `test_maps.py`, `tests/bdd/test_texture_bdd.py`) still pass (the floor only widens the pass set by at most 2/255).
- **Public contract changes**: `SEAM_TOLERANCE` removed from `bake_core/tiling.py` (no remaining references in the repo). `check_seams` return shape and reason code unchanged. `is_seamless(img, ratio=1.5)` signature unchanged; integer images are now normalised, which leaves the ratio comparison unchanged and only changes the floor's meaning. The `not_seamless` message text changed, as the spec requires.
- **Silent data changes**: none. The check reads pixels only; the `seamless` CLI overwrites its input only when `--out` is omitted, as documented.
- **Layering**: the duplicated metric (add-on module + `seamless.py`) is the design's selected alternative, because the add-on cannot import `nmg_game_dev`. The parity test enforces it.

| Area | Score | Notes |
|------|-------|-------|
| SOLID | 5 | `seam_metric` has one responsibility; `tiling` composes it; frozen `AxisSeam` value type |
| Security | 5 | No external input beyond a local PNG path; no shell, no secrets |
| Performance | 5 | Vectorised numpy, O(pixels) per channel; same order as before |
| Testability | 5 | Pure functions, deterministic seeded fixtures, by-path loading keeps tests bpy-free |
| Error Handling | 4 | Structured `BakeError`/`TextureGenError` with remediation; see Low findings |

### Minimal-change check

`git diff main...HEAD` also contains spec directories for #134, #140, #150. Those came from the approve-spec commits already on `origin/main` (the local `main` ref is stale), so they are not part of this change. The version commit `a82841e` (VERSION 0.21.2, CHANGELOG, plugin manifests) is the delivery-prep bump for a `bug` label (patch). No unrelated refactors.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes | Yes |
| AC5 | Yes (SCN005, Blender headless) | Yes | Yes |
| AC6 | Yes (SCN006) | Yes | Yes |
| AC7 | Yes (SCN007) | Yes | Yes |

All scenarios are tagged `@regression`.

### Coverage Summary

- Feature files: 6 pytest-bdd scenarios + 1 Blender headless scenario
- Step definitions: Implemented
- Unit tests: 7 in `test_seam_metric.py`, 3 new in `test_cli.py`
- Blender tests: 2 new, 1 updated in `test_bake_tiling.py`

---

## Exercise Test Results

Not applicable: no changes under `workflows/`, `agents/`, or `skills/`.

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | Environment | `fixtures/` UE build intermediates | `gate-ue-compile` failed twice because of concurrent cross-lane UnrealBuildTool/UBA builds | Diagnostic rebuild, then one full gate rerun while no other lane was building; no source change | direct |

No code fixes were needed.

## Remaining Issues

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `plugins/nmg-game-dev-blender-addon/bake_core/tiling.py` `check_seams` |
| **Issue** | The full `not_seamless` message string (joined per-channel details plus the trailing rule) is asserted only through `failure_detail` in unit/BDD tests. The Blender test asserts the reason and target, not the text. |
| **Impact** | A formatting regression in the trailing clause would not be caught. |
| **Reason Not Fixed** | Outside verify publication scope (report only); behaviour matches the design. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Error Handling |
| **Location** | `src/nmg_game_dev/texture/__main__.py` `_make_seamless_file` |
| **Issue** | An image narrower than 2 px on an axis would yield a NaN interior mean; not reachable for real textures. A write failure on save raises an unstructured `OSError`. |
| **Impact** | Edge-case error message quality only. |
| **Reason Not Fixed** | Out of spec scope. |

---

## Positive Observations

- One seam definition with named constants shared by bake and texture-gen, held together by a parity test that also asserts the corpus contains both outcomes.
- `AxisSeam` carries wrap, interior, and allowance, so the error message reports actionable numbers.
- The remediation is now a concrete one-line command, documented in all three consumer-facing docs.

---

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- [ ] Assert the full `not_seamless` message in the Blender non-periodic test.

### Long Term (Could)
- [ ] Map `OSError` on save in the `seamless` CLI to a structured `TextureGenError`.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `plugins/nmg-game-dev-blender-addon/bake_core/seam_metric.py` | 0 | New |
| `plugins/nmg-game-dev-blender-addon/bake_core/tiling.py` | 1 (Low) | |
| `plugins/nmg-game-dev-blender-addon/bake_core/errors.py` | 0 | |
| `src/nmg_game_dev/texture/seamless.py` | 0 | |
| `src/nmg_game_dev/texture/__main__.py` | 1 (Low) | |
| `docs/skills/bake-materials.md`, `docs/asset-contract.md`, `docs/onboarding/texture-models.md` | 0 | |
| `tests/texture_fakes.py`, `tests/unit/texture/test_seam_metric.py`, `tests/unit/texture/test_cli.py` | 0 | |
| `tests/bdd/features/tiling_seam_check.feature`, `tests/bdd/test_tiling_seam_check_bdd.py` | 0 | |
| `tests/blender/bake_fixtures.py`, `tests/blender/test_bake_tiling.py` | 0 | |

---

## Recommendation

**Ready for PR**

The defect reproduces before the fix and not after. Every AC, FR, task, and scenario has passing evidence. All applicable registered gates pass at `a82841e5a732dc8e13bcb7f5c90075c89eaff751` with complete coverage.
