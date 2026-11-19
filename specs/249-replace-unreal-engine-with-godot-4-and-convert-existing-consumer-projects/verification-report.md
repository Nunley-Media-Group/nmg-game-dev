# Verification Report: Replace Unreal Engine with Godot 4 and convert existing consumer projects

**Date**: 2026-11-19
**Issue**: #249
**Reviewer**: Claude (nmg-sdlc verify worker, gate phase)
**Scope**: Pre-merge gate at the merge-queue head; the review passed earlier at `e5fcce82bca2a1d23eb7d12f5dc7ca2ea8ace2ca`
**Verification head**: 380635554442d1f0209c95c774dd41009f014fcf

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 4 |
| Performance | 4 |
| Testability | 4 |
| Error Handling | 4 |
| **Overall** | 4.2 |

### Implementation Status: Pass
**Total Issues**: 0 blocking, 0 major, 0 minor; 14 info notes carried from the review

The review of `e5fcce8` (full mode, three lenses) passed with only `info` findings. Since then the branch only took two merges of `origin/main` and the version-preparation commit (`3806355`, VERSION 0.26.0). All 11 registered pre-merge validations passed at the verification head. Coverage is complete: 11 declared and 11 recorded, with none missing, duplicated or unknown, and there is no ceiling.

---

## Issue Scope

- Active issue: #249
- Spec: `specs/249-replace-unreal-engine-with-godot-4-and-convert-existing-consumer-projects`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1-AC14]; FR [FR1-FR14]; tasks [T001-T017]; scenarios [SCN001-SCN015]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":249,"specPath":"specs/249-replace-unreal-engine-with-godot-4-and-convert-existing-consumer-projects","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9","AC10","AC11","AC12","AC13","AC14"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9","FR10","FR11","FR12","FR13","FR14"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008","T009","T010","T011","T012","T013","T014","T015","T016","T017"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009","SCN010","SCN011","SCN012","SCN013","SCN014","SCN015"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Acceptance Criteria Verification

This evidence comes from the review record (`.nmg-sdlc/verification/249-review.json`). Each criterion marked **mocked** has suite tests that exercise its path through fakes (FakeGodotRunner, fake ffmpeg, onboarding and conversion fakes). For several of these, the review also ran real Godot 4.7.2 and Blender 5.2 probes as noted.

| AC | Description | Status | Exercised | Evidence |
|----|-------------|--------|-----------|----------|
| AC1 | Finalize lands both variants in Godot | Pass | mocked | `pipeline/steps.py:38-47` STEP_ORDER; `engine.py:457-481` `_run_import`; SCN001; real-Godot probe of `import_variants` on fixture Crate.glb matched |
| AC2 | Godot import failures stop finalize with a remediation | Pass | mocked | `engine.py:463` `godot.not_found`; `godot/runner.py:153-168` fails on a non-zero exit or an `ERROR:` line; real-Godot mismatch probe |
| AC3 | Animation clips import per clip | Pass | mocked | `finalize_core/anims.py:41`; real Blender `test_finalize_anims.py` 8 passed; `probe_anims.gd` against `expected-anims.json` in gate-godot-headless |
| AC4 | Terrain becomes chunked meshes with collision | Pass | mocked | `godot/terrain.py` with HeightMapShape3D; `probe_terrain.gd` against `expected-terrain.json` in gate-godot-headless |
| AC5 | Audio imports into Godot | Pass | mocked | Real-Godot `import_audio` produced an AudioStreamWAV with a loop; `audio.ffmpeg_not_found` raised before any write; OGG encoding tested only with a fake ffmpeg |
| AC6 | Material variants are listed without an editor | Pass | real_entry_point | `finalize/mcp_tools.py:185-201`; `material_variants.py:226-260`; `forbid_godot` tests |
| AC7 | Design scaffolding writes Godot files | Pass | real_entry_point | `design/scaffold.py`; `nmg_variant_scene.gd` @tool preview; real Godot run_tests.gd 18 passed |
| AC8 | The runtime add-on routes variants | Pass | real_entry_point | Add-on tests run under gate-godot-headless; hermetic `user://` variant tests |
| AC9 | Ship exports every target through Godot | Pass | real_entry_point | `ship/runner.py:133` runs `--import` before `--check-only`; `ship.import_failed`; real CLI dry run; gate-ship-smoke |
| AC10 | Onboarding sets up a Godot consumer | Pass | mocked | `onboard/godot.py:43-81,146-153`; `onboard/runner.py:247-268`; tests/unit/onboard |
| AC11 | Converting an Unreal consumer to Godot | Pass | mocked | `convert/` runner and state; tests/unit/convert; SCN011 |
| AC12 | Partial conversion keeps Unreal and resumes | Pass | mocked | Persisted resume lists; resumed-report assertions in tests/unit/convert |
| AC13 | Conversion guards and dry run | Pass | real_entry_point | `convert/runner.py` `_guard`; the dry run returns before any state is created (`:409-413`) |
| AC14 | Unreal is gone from nmg-game-dev | Pass | real_entry_point | `tests/unit/test_no_unreal_references.py`; manifest has no UE gates |

Criteria whose tests mock the path under test: AC1, AC2, AC3, AC4, AC5, AC10, AC11, AC12.

Functional requirements FR1-FR14, design paths DP1-DP39 and consumers C1-C15 all passed in the review. DP0 is not applicable: the design paths were extracted into DP1-DP39.

---

## Task Completion

| Task | Description | Status |
|------|-------------|--------|
| T001 | Add the Godot boundary package | Complete |
| T002 | Export `.glb` variants, clips, terrain chunks, and per-variant `nmg-asset.json` from Blender | Complete |
| T003 | Replace `import_ue` with `import_godot` in the finalize pipeline | Complete |
| T004 | Import animation clips as Godot animation libraries | Complete |
| T005 | Finalize terrain into a chunked scene with heightmap collision | Complete |
| T006 | Import sound effects as `AudioStreamWAV` and music as `AudioStreamOggVorbis` | Complete |
| T007 | List material variants from finalize-written files | Complete |
| T008 | Scaffold design entries as Godot files | Complete |
| T009 | Add the Godot runtime add-on, fixture project, and `gate-godot-headless` | Complete |
| T010 | Rework `/ship` around Godot export presets | Complete |
| T011 | Rework `/onboard-consumer` for a Godot consumer | Complete |
| T012 | Add `/convert-to-godot` | Complete |
| T013 | Rewrite contracts, skills, docs, and steering for Godot | Complete |
| T014 | Remove Unreal from the repository | Complete |
| T015 | Guard the repository against Unreal references | Complete |
| T016 | BDD scenarios for the Godot engine and conversion | Complete |
| T017 | Record the breaking change | Complete |

---

## Architecture Assessment

Scores are taken from the review lenses (acceptance, failure-paths, test-quality).

| Area | Score (1-5) | Notes |
|------|-------------|-------|
| SOLID Principles | 4 | `src/nmg_game_dev/godot/` is the only engine boundary. Some long functions remain (P10). |
| Security | 4 | Godot downloads are checked against SHA512-SUMS. Unvalidated material-variant names could write outside the variant folder (P9, input comes from finalize's own sidecar). |
| Performance | 4 | Clips are imported twice (A5); terrain is decoded in pure Python (P10). |
| Testability | 4 | Repairs carry regression-sensitive tests verified against real Godot; several ACs are exercised through fakes. |
| Error Handling | 4 | Structured error codes with remediations. Timeouts report exit code 124 with a generic remediation (P6); a hard kill can leave a target without its `.import` file (P5). |

**Layer separation**: skills call the CLIs and MCP tools, the pipeline composes the steps, and only `nmg_game_dev.godot` runs Godot headless. No editor bridge or engine MCP server remains.

---

## Test Results

All validations run under the pre-merge tier. This project declares no tiers, so every result records `tier: null` and `selection: null`. No validation is marked heavy.

| Validation | Provider | Status | Tier | Selection | Evidence |
|------------|----------|--------|------|-----------|----------|
| repository.tests | builtin.command | Pass | null | null | `uv run pytest tests/unit tests/bdd -q` exited 0 |
| repository.lint | builtin.command | Pass | null | null | `uv run ruff check .` exited 0 |
| repository.format | builtin.command | Pass | null | null | `uv run ruff format --check .` exited 0 |
| repository.types | builtin.command | Pass | null | null | `uv run mypy src tests` exited 0 |
| gate-blender-headless | builtin.command | Pass | null | null | `scripts/run-blender-tests.sh` exited 0 |
| gate-godot-headless | builtin.command | Pass | null | null | `scripts/run-godot-tests.sh` exited 0 |
| gate-mcp-schema | builtin.command | Pass | null | null | `scripts/validate-mcp-tools.py` exited 0 |
| gate-shellcheck | builtin.command | Pass | null | null | shellcheck exited 0 |
| gate-ship-smoke | builtin.command | Pass | null | null | `scripts/ship-smoke.sh` exited 0 |
| plugin.validate | builtin.command | Pass | null | null | `claude plugin validate .` exited 0 |
| plugin.session-smoke | project.plugin-session-smoke | Pass | null | null | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 11/11 passed, 0 failed, 0 incomplete. Coverage: declared 11, recorded 11, complete true. Artifact: `.nmg-sdlc/verification/249.json`.

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests / lint / format / types | Pass | command exited 0 |
| gate-blender-headless | Pass | command exited 0 |
| gate-godot-headless | Pass | command exited 0 |
| gate-mcp-schema | Pass | command exited 0 |
| gate-shellcheck | Pass | command exited 0 |
| gate-ship-smoke | Pass | command exited 0 |
| plugin.validate | Pass | command exited 0 |
| plugin.session-smoke | Pass | MCP servers connected through the session smoke |

No `nmg-sdlc-smoke` validation is registered in this project's manifest, so the smoke requirement does not apply.

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None in the gate phase. Earlier review findings (P1, P2, A1-A3) were fixed by implement before the review passed at `e5fcce8`. | — | — |

## Remaining Issues

Every remaining issue is an `info` note; none blocks the merge.

| ID | Location | Note |
|----|----------|------|
| I1, A4, P4 | `design.md`, `steering/manifest.json` | design.md lags the implementation in three places: ship runs `--import` first, gate-ship-smoke includes more paths, and the convert `not_unreal` check is skipped on resume. Reconcile at the next spec amendment. |
| I2 | `steering/snippets/project-structure.md` | The "Doesn't Do" cell for the Godot add-on contradicts the NmgVariantScene editor preview. |
| A5 | `src/nmg_game_dev/godot/anims.py` | Clips are imported twice. |
| A6 | `addons/nmg_game_dev/plugin.gd` | The autoload is added in `_enter_tree` rather than `_enable_plugin`. |
| A7 | `src/nmg_game_dev/onboard/godot.py` | Preset drift is a byte comparison. |
| A8 | `variants_core/export.py` | The material slot count when two slots share one material is unverified. |
| P5 | `src/nmg_game_dev/audio/godot_import.py` | A crash window can leave a target without its `.import` file; the remediation wording is incomplete. |
| P6 | `src/nmg_game_dev/ship/runner.py` | Export and import timeouts report a generic remediation. |
| P7 | `src/nmg_game_dev/godot/runner.py` | A timeout kills only the direct child process. |
| P8 | `scripts/run-godot-tests.sh`, manifest | Cache race; the gate is not marked heavy; GODOT_GATE_TIMEOUT is not forwarded. |
| P9 | `src/nmg_game_dev/godot/material_variants.py` | Variant names are not restricted to `[A-Za-z0-9_]`. |
| P10 | several | Carried residuals: concurrency races, long functions, unregistered pytest marks. |

---

## Recommendation

**Ready for PR**

The review passed with only info notes. Every registered pre-merge validation passed at the verification head `380635554442d1f0209c95c774dd41009f014fcf`, and coverage is complete.
