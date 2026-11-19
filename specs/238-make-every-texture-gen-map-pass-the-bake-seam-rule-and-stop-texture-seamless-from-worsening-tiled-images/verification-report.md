# Verification Report: Generated texture maps fail the bake seam rule and `texture seamless` worsens tiled images

**Date**: 2026-11-19
**Issue**: #238
**Reviewer**: Claude (nmg-sdlc verify worker, gate phase)
**Scope**: Implementation verification against spec
**Verification head**: 6da3259bbd94aa050314b9951777128f35067867

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
**Total Issues**: 0 (four `info` notes, no defects)

The review passed in full mode at head `92c3fa87be81c19dc4f7ee933bf1ca369f7e0c66` with no finding above `info` (four `info` notes, I1-I4). Since that head the branch has two commits. `096a6db` merges `origin/main` at `273e969` (#279, #278), which brings no change to any #238 path. `6da3259 fix: deliver issue #238` prepares version 0.28.1: it changes `VERSION`, `.claude-plugin/plugin.json`, `plugins/nmg-game-dev-blender-addon/blender_manifest.toml`, `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/plugin.cfg` and `CHANGELOG.md`. No #238 source changed. The branch is at the head of the merge queue with `origin/main` (`273e969`) integrated. The registered pre-merge gate ran once at the verification head `6da3259bbd94aa050314b9951777128f35067867`. All 11 registered validations were recorded: 8 applied and passed, and 3 did not apply to the changed paths.

---

## Issue Scope

- Active issue: #238
- Spec: `specs/238-make-every-texture-gen-map-pass-the-bake-seam-rule-and-stop-texture-seamless-from-worsening-tiled-images`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5, AC6]; FR [FR1, FR2, FR3, FR4, FR5, FR6]; tasks [T001, T002, T003, T004, T005, T006]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005, SCN006]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":238,"specPath":"specs/238-make-every-texture-gen-map-pass-the-bake-seam-rule-and-stop-texture-seamless-from-worsening-tiled-images","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6"],"tasks":["T001","T002","T003","T004","T005","T006"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/238.json`. Its identity is head `6da3259bbd94aa050314b9951777128f35067867`, steering `sha256:f7a60903…805cfa`, spec `sha256:aaedde37…abe22`, with a clean tree.
- Ceiling: none.
- Coverage: declared 11, recorded 11, complete `true`, with nothing missing, duplicated or unknown.
- Tiers: the project declares none, so every result records `tier: null` and `selection: null`.

---

## Acceptance Criteria Verification

The evidence comes from the passed review record `.nmg-sdlc/verification/238-review.json`. The criteria whose tests mock the path under test: **none**. Every acceptance criterion is exercised through its real entry point.

| AC | Description | Status | Exercised | Evidence |
|----|-------------|--------|-----------|----------|
| AC1 | Generated maps pass the seam rule | Pass | real entry point | `tests/unit/texture/test_generate.py::test_every_generated_map_passes_the_seam_rule_for_a_low_contrast_albedo` and SCN001 drive `generate.run` with the low-contrast crop. Albedo, N, R, M and AO all pass `is_seamless`. In a probe, the derived AO fails on main and passes at this head. |
| AC2 | Derived maps pass for any passing albedo | Pass | real entry point | `tests/unit/texture/test_maps.py::test_every_derived_map_passes_the_seam_rule[seamless-synthetic\|seamless-low-contrast]` and SCN002 call `maps.derive` on a written PNG. |
| AC3 | `texture seamless` leaves a passing image unchanged | Pass | real entry point | `tests/unit/texture/test_cli.py::test_seamless_leaves_a_passing_png_unchanged` covers cross-faded and natively tiling inputs, written in place and with `--out`. A mutation probe that reverted the CLI to `make_seamless` made 2 tests fail. |
| AC4 | `texture seamless` repairs failing maps without making them worse | Pass | real entry point | `tests/unit/texture/test_cli.py:292-308` runs `main(['seamless', png])` on 4 failing inputs, including `cross_fade_failing_crop`. It asserts that the output passes and that neither axis's wrap is larger than the input's. A mutation probe that bypassed `fix_seam` made the cross-fade-failing case fail. |
| AC5 | Existing behaviour is preserved | Pass | real entry point | `git diff main...HEAD -- tests/unit` only adds test functions and imports. SCN005 reruns the texture unit and BDD suites. The full `repository.tests` run passed: 1911 passed, 19 skipped. |
| AC6 | Docs tell consumers to reload or repack after fixing files on disk | Pass | real entry point | `docs/onboarding/texture-models.md` and `docs/skills/bake-materials.md` both contain the reload/repack note, which SCN006 asserts. |

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `src/nmg_game_dev/texture/generate.py:549-554` applies `repair_seam` when the cross-faded albedo fails. A mutation probe confirmed a test pins this. |
| FR2 | Pass | `src/nmg_game_dev/texture/maps.py:97-109` (`_seam_safe_normal`, which renormalizes) and `src/nmg_game_dev/texture/maps.py:149-151` (AO repair). A unit-vector test passes. |
| FR3 | Pass | `src/nmg_game_dev/texture/seamless.py:112-153`: `edge_band` and `repair_seam`, which rechecks for up to two passes and keeps dtype and shape. |
| FR4 | Pass | `src/nmg_game_dev/texture/seamless.py:156-164`: `fix_seam` returns a passing image unchanged, uses the band for narrow failures and cross-fades then bands gross failures. The output is never worse than the input on either axis. |
| FR5 | Pass | Tests assert that every map passes for the low-contrast and synthetic fixtures. |
| FR6 | Pass | The docs note is present. `plugins/nmg-game-dev-blender-addon/bake_core/errors.py` `REASONS['not_seamless']` repeats it. |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Add the edge-band seam repair and severity-based fix | Complete | `src/nmg_game_dev/texture/seamless.py` |
| T002 | Guarantee generated albedos and derived maps pass the seam rule | Complete | `src/nmg_game_dev/texture/generate.py`, `src/nmg_game_dev/texture/maps.py` |
| T003 | Make `texture seamless` leave passing images alone and never worsen a wrap | Complete | `src/nmg_game_dev/texture/__main__.py` |
| T004 | Document the repair and the reload/repack step | Complete | `docs/onboarding/texture-models.md`, `docs/skills/bake-materials.md` and `plugins/nmg-game-dev-blender-addon/bake_core/errors.py` |
| T005 | Add regression fixtures and unit tests | Complete | `tests/texture_fakes.py`, `tests/unit/texture/test_cli.py`, `tests/unit/texture/test_generate.py`, `tests/unit/texture/test_maps.py` and `tests/unit/texture/test_seamless.py` |
| T006 | Add BDD scenarios for the seam repair | Complete | `tests/bdd/features/texture_seam_repair.feature` and `tests/bdd/test_texture_seam_repair_bdd.py` |

---

## Changed Paths

Every changed path on this branch, written as its exact repo-relative path (`git diff --name-only main...HEAD`):

- `.claude-plugin/plugin.json`
- `CHANGELOG.md`
- `VERSION`
- `docs/onboarding/texture-models.md`
- `docs/skills/bake-materials.md`
- `plugins/nmg-game-dev-blender-addon/bake_core/errors.py`
- `plugins/nmg-game-dev-blender-addon/blender_manifest.toml`
- `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/plugin.cfg`
- `src/nmg_game_dev/texture/__main__.py`
- `src/nmg_game_dev/texture/generate.py`
- `src/nmg_game_dev/texture/maps.py`
- `src/nmg_game_dev/texture/seamless.py`
- `tests/bdd/features/texture_seam_repair.feature`
- `tests/bdd/test_texture_seam_repair_bdd.py`
- `tests/texture_fakes.py`
- `tests/unit/texture/test_cli.py`
- `tests/unit/texture/test_generate.py`
- `tests/unit/texture/test_maps.py`
- `tests/unit/texture/test_seam_metric.py`
- `tests/unit/texture/test_seamless.py`
- `specs/238-make-every-texture-gen-map-pass-the-bake-seam-rule-and-stop-texture-seamless-from-worsening-tiled-images/verification-report.md` (the report-only commit)

## Architecture Assessment

The scores come from the three review lenses: acceptance, failure-paths and test-quality.

| Area | Score (1-5) | Notes |
|------|-------------|-------|
| SOLID Principles | 5 | The seam repair stays in `src/nmg_game_dev/texture/seamless.py`. `src/nmg_game_dev/texture/maps.py` and `src/nmg_game_dev/texture/generate.py` consume it, and `src/nmg_game_dev/texture/__main__.py` wraps `fix_seam`. Layering is unchanged. |
| Security | 5 | Local image processing only. There is no new input surface. The CLI's existing missing-input path is unchanged and tested. |
| Performance | 5 | The band repair touches at most 8 lines per axis, with at most two passes. |
| Testability | 5 | Every criterion is driven through its real entry point, and mutation probes confirm the new branches are pinned. |
| Error Handling | 5 | Design paths DP1-DP8 pass. The normal-map band never yields a zero vector because nz > 0. |

**Average**: 5.0

### Layer Separation and Dependency Flow

`nmg_game_dev.texture.seamless` is the lowest layer. `maps`, `generate` and `__main__` depend on it, and nothing depends upward. The Blender add-on's `bake_core/seam_metric.py` parity functions are unchanged.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes | Yes |
| AC5 | Yes (SCN005) | Yes | Yes |
| AC6 | Yes (SCN006) | Yes | Yes |

---

## Steering Doc Verification Gates

None of these validations is marked heavy.

| Gate | Status | Tier / Selection | Evidence |
|------|--------|------------------|----------|
| `repository.tests` | Pass | null / null | `uv run pytest tests/unit tests/bdd -q`: 1911 passed, 19 skipped in 213.60s |
| `repository.lint` | Pass | null / null | `uv run ruff check .`: All checks passed! |
| `repository.format` | Pass | null / null | `uv run ruff format --check .`: 430 files already formatted |
| `repository.types` | Pass | null / null | `uv run mypy src tests`: Success, no issues found in 278 source files |
| `gate-blender-headless` | Pass | null / null | `scripts/run-blender-tests.sh`: 420 passed, 4 skipped in 181.45s. It applies because `plugins/nmg-game-dev-blender-addon/bake_core/errors.py` and `plugins/nmg-game-dev-blender-addon/blender_manifest.toml` changed. |
| `gate-godot-headless` | Pass | null / null | `scripts/run-godot-tests.sh`: import, add-on tests, and probes passed. It applies because `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/plugin.cfg` changed its version. |
| `gate-mcp-schema` | Not applicable | null / null | The change touches no `mcp-servers/**` path |
| `gate-shellcheck` | Not applicable | null / null | The change touches no `scripts/**.sh` path |
| `gate-ship-smoke` | Not applicable | null / null | The change touches no ship path |
| `plugin.validate` | Pass | null / null | `claude plugin validate .`: Validation passed with warnings. It applies because `.claude-plugin/plugin.json` changed. |
| `plugin.session-smoke` | Pass | null / null | `project.plugin-session-smoke`: the plugin loaded through `--plugin-dir` and `nmg-game-dev:blender` connected |

**Gate Summary**: 8 of 8 applicable gates passed, 0 failed, 0 incomplete. 3 gates did not apply. Coverage is complete (11 of 11 recorded).

No `repository.nmg-sdlc-smoke` or `project.nmg-sdlc-smoke` validation is registered in `steering/manifest.json`, so no smoke lifecycle evidence applies.

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None in the gate phase | — | — |

The review's earlier findings were fixed in implement before the review passed. F1 to F4 and the prior I1 and I2 are recorded in `.nmg-sdlc/verification/238-review.md`.

## Remaining Issues

None blocking, major or minor.

The passed review record carries four `info` notes, none of which blocks delivery:

- **Info (I1)**: for an image with a 1-px axis, `interior_mad` on that axis is NaN, so `is_seamless` never passes and `fix_seam` writes an image that reports `seamless: false` (`src/nmg_game_dev/texture/seamless.py`). This is a pre-existing seam-metric limitation; no real texture has a 1-px axis.
- **Info (I2)**: design.md's Blast Radius says `bake_core` is untouched, but the branch edits the `not_seamless` remediation string in `plugins/nmg-game-dev-blender-addon/bake_core/errors.py`. The change is string-only and consistent with FR6, and it brought `gate-blender-headless` into scope, which passed.
- **Info (I3)**: the spec-named AC4 fixtures also pass under a `make_seamless`-only CLI, so SCN004 alone would not catch that regression; `tests/unit/texture/test_cli.py` (`cross_fade_failing_crop`) and the narrow-branch tests in `tests/unit/texture/test_seamless.py` do.
- **Info (I4)**: SCN005 in `tests/bdd/test_texture_seam_repair_bdd.py` reruns the texture unit tests and two texture BDD modules in a child pytest, so those tests run twice per gate.

---

## Positive Observations

- Mutation probes confirm that the new FR1, AC3 and AC4 branches are pinned by tests.
- The normal-map repair works on float vectors and renormalizes them, so the encoding stays valid.

---

## Recommendation

**Ready for PR**

All acceptance criteria, functional requirements and tasks are delivered. Every applicable registered pre-merge gate passed at the exact verification head.
