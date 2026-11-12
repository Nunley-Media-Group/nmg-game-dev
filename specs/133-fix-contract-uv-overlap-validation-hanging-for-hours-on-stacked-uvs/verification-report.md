# Verification Report: Contract UV overlap validation hangs for hours on stacked UVs

**Date**: 2026-11-11
**Issue**: #133
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Implementation verification against spec (re-verification after reverting the out-of-scope UE compile gate change)

**Verification head**: 4ca661653a9522d9416153e1e5ca47dd1d60d5c6

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4.6 |
| Security | 5 |
| Performance | 5 |
| Testability | 4.5 |
| Error Handling | 4.5 |
| **Overall** | 4.8 |

### Implementation Status: Pass
**Total Issues**: 1 (low, outside this issue's scope; recorded as a recommendation)

The UV overlap rasterizer is vectorized with numpy. It stops once the shared-texel count exceeds `OVERLAP_LIMIT × GRID²`. That early exit cannot change the pass/fail outcome, because covered texels never exceed `GRID²`. An early-exit finding says "at least". The validate step emits an `NMG_PROGRESS` line for each mesh check.

Since the last verification, commit `4ca6616` reverted `746d794`, so the branch no longer changes the UE compile gate (`steering/extensions/ue-compile.mjs` and its row in tech steering). That change will ship under its own issue. The branch's net change against `origin/main` is now limited to #133's files, the CHANGELOG entry and this report. The whole registered gate ran again at `4ca6616`, and all 10 applicable gates passed with complete coverage.

---

## Issue Scope

- Active issue: #133
- Spec: `specs/133-fix-contract-uv-overlap-validation-hanging-for-hours-on-stacked-uvs`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5, AC6]; FR [FR1, FR2, FR3, FR4, FR5, FR6]; tasks [T001, T002, T003, T004, T005, T006]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005, SCN006]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":133,"specPath":"specs/133-fix-contract-uv-overlap-validation-hanging-for-hours-on-stacked-uvs","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6"],"tasks":["T001","T002","T003","T004","T005","T006"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact

- Artifact: `.nmg-sdlc/verification/133.json`, written by `sdlc-verify-steering.mjs --issue 133 --base main --controller-run-id ccabf717-4994-44b3-bb04-fedc2e7669d9` at 2026-11-12T04:25:06Z
- Identity: head `4ca661653a9522d9416153e1e5ca47dd1d60d5c6`, tree clean, steering `sha256:795f9897…`, spec `sha256:5e6ad702…`
- Coverage: 11 declared, 11 recorded, complete `true`; nothing missing, duplicated or unknown
- Ceiling: none

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Stacked UVs (≥100k tris) fail fast with `uv.overlap` within 10 s | Pass | `contract_core/uv.py` `_overlap_core` stops after the first batch that pushes the shared count past the limit. `test_ac1_stacked_uvs_on_a_100k_triangle_mesh_fail_fast` asserts both the < 10 s bound and the `uv.overlap` finding. It passes in `gate-blender-headless` |
| AC2 | Early exit never changes the outcome; stops once shared > `OVERLAP_LIMIT × GRID²` | Pass | The exit test `shared_count > OVERLAP_LIMIT * GRID * GRID` runs after each batch. The returned `shared/GRID²` is ≤ the full `shared/covered`, so it is a lower bound that is still above the limit. The edge functions, the `>= 0` test, texel-center sampling and the clamped box match the pre-change `_rasterize` term for term. `_clamped_span` keeps empty ranges empty. `_record_hits` keeps the distinct-face shared rule (lowest/highest face per texel within a batch, plus the prior owner). The seeded random comparison against a reference copy of the old rasterizer passes, and so does the 1,000-quad `exact=False` case |
| AC3 | Early-exit message states a lower bound and names the limit | Pass | `_overlap_message` adds `"at least "` when `exact=False`. Covered by `test_ac3_early_exit_finding_states_a_lower_bound`, `test_ac3_exact_overlap_keeps_the_original_message`, and `test_uv_overlap_defect_reports_the_lower_bound_form` |
| AC4 | A ≥200k-tri layout with no overlap passes within 30 s | Pass | `test_ac4_large_separate_layout_passes_fast` asserts both the < 30 s bound and that neither `uv_findings` nor `validate_asset` reports a `uv.overlap` finding |
| AC5 | Existing contract-validate and bake-unique fixtures unchanged | Pass | `polygon_overlap_fraction` and `overlap_fraction` keep their signatures, and `bake_core/uv.py` is untouched. The existing tests in `test_contract_validate.py` and `test_bake_unique.py` pass with their assertions unmodified (257 passed in `gate-blender-headless`) |
| AC6 | Validate reports per-check progress | Pass | `validate.py` `_CheckUnits` reports one unit per mesh check, and the unit count matches the meshes `_mesh_findings` visits. `steps.py` `report_progress` maps it to `0.01 + 0.98·f`, and the highest started fraction `(n-1)/n` keeps that at or below 0.99. Covered by `test_validate_step_prints_per_check_progress_lines` (Blender) and `test_a_validate_progress_event_is_in_the_job_status_mid_step` (host, `repository.tests`) |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Vectorize the rasterizer with an outcome-preserving early exit | Complete | `_BATCH_TEXELS = 1 << 20`; an oversized triangle forms its own batch (`max(end, start + 1)`); the per-texel `_rasterize` is removed; `mesh_overlap` reads UVs, `loop_start` and `loop_total` with `foreach_get` |
| T002 | Lower-bound early-exit message | Complete | The rule code stays `uv.overlap` |
| T003 | Per-mesh, per-check validate progress | Complete | `progress` is keyword-only and defaults to `None`. Without it the report is unchanged. The `started` and final lines from `run_step` are unchanged too |
| T004 | Regression tests for stacked, early-exit and large valid layouts | Complete | `tests/blender/test_contract_uv_overlap.py` |
| T005 | Existing overlap fixtures unchanged, plus a lower-bound assertion | Complete | `tests/blender/test_contract_validate.py` |
| T006 | Progress-line and job-status relay tests | Complete | `tests/blender/test_finalize_core.py`, `tests/unit/pipeline/test_jobs.py` |

The branch has no remaining changes outside these six tasks. Merge commit `f2641c1` brings in `origin/main`. In `validate.py` it carries main's per-slot texel-density changes, which sit alongside #133's progress units without conflict: `environment_piece` still counts three checks per mesh and other classes count two. The `-NoUBA` UE compile gate change (`746d794`) is reverted at `4ca6616`, and `gate-ue-compile` passed without it.

`origin/main` has three commits that are newer than this branch (`375a65b`, `c0d2908`, `0548c42`). `git merge-tree` shows they merge into this head without conflict. Deliver's base reconciliation will bring them in.

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Each stage has its own helper: preparation (`_prepare`, `_clamped_span`), batching (`_overlap_core`), rasterization (`_rasterize_batch`) and hit folding (`_record_hits`) |
| Open/Closed | 4 | The public API is preserved. `OverlapResult`, `polygon_overlap` and `mesh_overlap` are additions that leave existing callers unchanged |
| Liskov Substitution | 5 | `polygon_overlap_fraction` and `overlap_fraction` keep the same contract for `bake_core/uv.py` |
| Interface Segregation | 5 | `progress` is an optional keyword-only callback |
| Dependency Inversion | 4 | Validate receives the progress sink as a callable, and the finalize step owns the `NMG_PROGRESS` wire format |

### Layer Separation

The changes stay in `contract_core/` (the check) and `finalize_core/steps.py` (step wiring), which matches structure steering's split between step implementations and the pipeline. Nothing changes on the host side, because the existing relay already writes `NMG_PROGRESS` events into `status.json`.

## Security Assessment (5)

- [x] No new inputs, secrets, subprocesses or network access
- [x] Huge or out-of-range UV coordinates are clamped before the integer cast (`_clamped_span`). Triangles with NaN corners have a NaN area and are dropped as non-live before any texel indexing
- [x] Progress messages carry only variant, check and object names

## Performance Assessment (5)

- [x] Memory is bounded: a batch holds at most about 1M candidate texels, and a single oversized triangle is capped at `GRID²`
- [x] The early exit bounds the stacked-UV worst case
- [x] Bulk `foreach_get` replaces per-loop RNA access
- [x] The whole `gate-blender-headless` suite, including the 100k- and 200k-triangle cases, ran in 97 s

## Testability (4.5) and Error Handling (4.5)

- Testability: a reference rasterizer in the test file serves as an oracle for the comparison tests. The timing assertions depend on the machine, but their bounds are generous.
- Error handling: degenerate and empty triangles are skipped by setting `width = 0`. Meshes with no polygons return an exact 0.0. Progress is not reported when there are zero units, so there is no division by zero.

---

## Test Coverage

| Acceptance Criterion | Has Scenario | Has Tests | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes | Yes |
| AC5 | Yes (SCN005) | Yes | Yes |
| AC6 | Yes (SCN006) | Yes | Yes |

- BDD scenarios: 6/6 acceptance criteria covered
- Test execution: Pass

No exercise test was required, because the branch does not change any nmg-sdlc plugin `workflows/` or `agents/` files.

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | 1129 passed, 9 skipped in 96 s |
| repository.lint | Pass | ruff: All checks passed |
| repository.format | Pass | 333 files already formatted |
| repository.types | Pass | mypy: no issues found in 210 source files |
| gate-blender-headless | Pass | 257 passed in 97 s; add-on loaded from the lane-1 checkout (see note) |
| gate-ue-compile | Pass | DogfoodEditor compiled against UE 5.8 at `/Users/Shared/Epic Games/UE_5.8` (no `-NoUBA`, after the revert); Result: Succeeded |
| gate-mcp-schema | Pass | `validate-mcp-tools.py` exited 0 (applies because the stale local `main` base adds main's paths to the diff) |
| gate-shellcheck | Pass | `shellcheck -S style` exited 0 (applies for the same reason) |
| gate-ship-smoke | N/A | Not applicable; no matching paths |
| plugin.validate | Pass | `claude plugin validate .` passed with warnings |
| plugin.session-smoke | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

**Gate rerun note.** The first gate run at this head recorded one `repository.tests` failure: `tests/bdd/steps/test_scaffold.py::test_unreal_launcher_detaches` measured 2.19 s against its 2.0 s bound. The run had no code change to account for it. The host's load average was 381 on 10 cores, from the parallel lanes. The test exercises `scripts/start-unreal-mcp.sh`, which this branch does not touch, and alone it passed three times in about 0.9 s. Under that failure the runner deferred `gate-ue-compile` and `plugin.session-smoke` as incomplete. The full gate ran again at the same head once the 5-minute load average fell below 60, and every gate in the table above comes from that run.

**Blender add-on isolation note.** At this head, `tests/blender/_runner.py` points one per-user add-on symlink at the add-on it should test, and every lane shares that symlink. When this run started, the shared link pointed at the `spec-1` lane. To keep the gate testing lane-1's code, `BLENDER_BIN` was set to a scratch wrapper. The wrapper exports a lane-private `BLENDER_USER_RESOURCES` and execs the same `BLENDER_APP` binary. `BLENDER_BIN` is one of the two variables the gate forwards, so this changes no gate config. After the run, the private link pointed at `lane-1/plugins/nmg-game-dev-blender-addon`. The private directory also linked in the host `blender_mcp.py` add-on, so the `requires_host` tests ran as usual. No repository source changed.

---

## Fixes Applied

None. No source changes were needed.

## Remaining Issues

### Low

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Low | Testability / infra | `tests/bdd/steps/test_scaffold.py` `script_returns_quickly` | The 2.0 s wall-clock bound on the Unreal launcher fails when the host is heavily overloaded, even though the launcher detaches correctly. | Outside #133's scope, and verify may publish only this report. Recommend a follow-up that measures detachment without depending on host load, or that widens the bound. The shared add-on symlink noted in the last report is already addressed on `origin/main` (`tests/blender/_runner.py` and `tests/unit/test_blender_runner_isolation.py`), and arrives with deliver's base merge. |

## Recommendation

Ready for PR.
