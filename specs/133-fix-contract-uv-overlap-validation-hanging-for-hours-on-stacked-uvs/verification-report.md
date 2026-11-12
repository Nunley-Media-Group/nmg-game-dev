# Verification Report: Contract UV overlap validation hangs for hours on stacked UVs

**Date**: 2026-11-11
**Issue**: #133
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Implementation verification against spec
**Verification head**: 746d794d724f3a8efc23d4490e64c765a27c8532

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

The UV overlap rasterizer is now vectorized with numpy and stops once the shared-texel count exceeds `OVERLAP_LIMIT × GRID²`. That bound is outcome-preserving because covered texels can never exceed `GRID²`. Early-exit findings say "at least", and the validate step emits per-mesh, per-check `NMG_PROGRESS` lines. The stacked-UV regression suite ran in about 5 s (the old code hung for hours). The full registered gate passed at the exact head with complete coverage: 8 applicable gates passed and 3 did not apply.

---

## Issue Scope

- Active issue: #133
- Spec: `specs/133-fix-contract-uv-overlap-validation-hanging-for-hours-on-stacked-uvs`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5, AC6]; FR [FR1–FR6]; tasks [T001–T006]; scenarios [SCN001–SCN006]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":133,"specPath":"specs/133-fix-contract-uv-overlap-validation-hanging-for-hours-on-stacked-uvs","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6"],"tasks":["T001","T002","T003","T004","T005","T006"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact

- Artifact: `.nmg-sdlc/verification/133.json` (`sdlc-verify-steering.mjs --issue 133 --base main --controller-run-id fbd9a88c-37d4-4a19-81bb-f1ae6ee01cf3`)
- Identity: head `746d794d724f3a8efc23d4490e64c765a27c8532`, tree clean
- Coverage: declared 11, recorded 11, complete `true`, with no missing, duplicate or unknown entries
- Ceiling: none

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Stacked UVs (≥100k tris) fail fast with `uv.overlap` within 10 s | Pass | `contract_core/uv.py` `_overlap_core` early exit; `tests/blender/test_contract_uv_overlap.py` AC1 tests pass under `gate-blender-headless` (the whole file runs in about 5 s) |
| AC2 | Early exit never changes the outcome; stops once shared > `OVERLAP_LIMIT × GRID²` | Pass | `_overlap_core` checks `shared_count > limit` after each batch, and `fraction = shared/GRID² ≤ shared/covered`. The seeded random comparison against the reference pure-Python rasterizer in `test_contract_uv_overlap.py` passes, and so does the 1,000-quad `exact=False` case |
| AC3 | Early-exit message states a lower bound and names the limit | Pass | `uv.py` `_overlap_message` adds the `"at least "` prefix when `exact=False`. Tested in `test_contract_uv_overlap.py` and `test_contract_validate.py` |
| AC4 | ≥200k-tri non-overlapping layout passes within 30 s | Pass | `test_ac4_large_separate_layout_passes_fast` passes |
| AC5 | Existing contract-validate and bake-unique fixtures unchanged | Pass | `polygon_overlap_fraction` and `overlap_fraction` keep their signatures. `bake_core/uv.py` is untouched. The existing tests in `test_contract_validate.py` and `test_bake_unique.py` pass (189 passed in `gate-blender-headless`) |
| AC6 | Validate reports per-check progress | Pass | `validate.py` `_CheckUnits` and `finalize_core/steps.py` `report_progress` (`0.01 + 0.98·f`). Covered by `tests/blender/test_finalize_core.py` (Blender) and `tests/unit/pipeline/test_jobs.py` (host, `repository.tests`) |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Vectorize rasterizer with outcome-preserving early exit | Complete | `_BATCH_TEXELS = 1 << 20`; an oversized triangle forms its own batch; the per-texel `_rasterize` is removed; `foreach_get` reads the mesh UVs and loop ranges |
| T002 | Lower-bound early-exit message | Complete | Rule code stays `uv.overlap` |
| T003 | Per-mesh, per-check validate progress | Complete | `progress=None` leaves the report unchanged |
| T004 | Regression tests for stacked, early-exit, and large valid layouts | Complete | `tests/blender/test_contract_uv_overlap.py` (8 tests) |
| T005 | Existing overlap fixtures unchanged, plus a lower-bound assertion | Complete | `tests/blender/test_contract_validate.py` |
| T006 | Progress-line and job-status relay tests | Complete | `test_finalize_core.py`, `tests/unit/pipeline/test_jobs.py` |

Commit 746d794 also changes `steering/extensions/ue-compile.mjs` and the matching tech-steering row: the UE compile gate now builds with `-NoUBA`. That stopped cross-lane UBA object-cache corruption, which had failed `gate-ue-compile` on this branch. `gate-ue-compile` now passes.

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Separate helpers for preparation (`_prepare`), batching (`_overlap_core`), rasterization (`_rasterize_batch`) and hit folding (`_record_hits`) |
| Open/Closed | 4 | The public API is preserved. `OverlapResult` is added without changing existing callers |
| Liskov Substitution | 5 | `polygon_overlap_fraction` and `overlap_fraction` keep the same contract |
| Interface Segregation | 5 | `progress` is an optional keyword-only callback |
| Dependency Inversion | 4 | Validate takes the progress sink as a callable, and the finalize step owns the `NMG_PROGRESS` wire format |

### Layer Separation

Changes stay in `contract_core/` (the check) and `finalize_core/steps.py` (step wiring). This follows the step-implementation and pipeline split in structure steering.

---

## Security Assessment

- [x] No new inputs, secrets, subprocesses or network access
- [x] Huge UV coordinates are clamped before the integer cast (`_clamped_span`)
- [x] Progress messages carry only object names and check labels

## Performance Assessment

- [x] Bounded memory: each batch holds at most about 1M candidate texels, apart from a single oversized triangle, which is capped at `GRID²`
- [x] Early exit bounds the stacked-UV worst case
- [x] Bulk `foreach_get` replaces per-loop RNA access

## Testability and Error Handling

- Testability (4.5): a reference rasterizer in the test file gives an oracle comparison. The timing assertions depend on the machine but have generous bounds.
- Error handling (4.5): degenerate and empty triangles are skipped through `width = 0`. Empty meshes return an exact 0.0. Progress is skipped when there are zero units.

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

- `repository.tests`: 970 passed, 9 skipped
- `gate-blender-headless`: 189 passed in 122 s

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | 970 passed, 9 skipped in 79.8 s |
| repository.lint | Pass | ruff: All checks passed |
| repository.format | Pass | 310 files already formatted |
| repository.types | Pass | mypy: no issues in 197 source files |
| gate-blender-headless | Pass | 189 passed in 122 s; add-on loaded from the lane-1 checkout (see note) |
| gate-ue-compile | Pass | DogfoodEditor compiled against UE 5.8 (`-NoUBA`) |
| gate-mcp-schema | N/A | Not applicable (no `mcp-servers/**` change) |
| gate-shellcheck | N/A | Not applicable (no `scripts/**.sh` change) |
| gate-ship-smoke | N/A | Not applicable |
| plugin.validate | Pass | `claude plugin validate .` passed (with warnings) |
| plugin.session-smoke | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 8/8 applicable gates passed, 0 failed, 0 incomplete (3 not applicable)

**Blender add-on isolation note.** The previous run was Incomplete. The orchestrator killed it after 2h26m, because the shared user add-on symlink `~/Library/Application Support/Blender/5.2/scripts/addons/nmg_game_dev_blender_addon` had been repointed to another lane's checkout (`spec-1`), so the stacked-UV test imported the old O(n) rasterizer. To prevent that, this run set the forwarded `BLENDER_BIN` to a scratch wrapper. The wrapper exports a lane-private `BLENDER_USER_RESOURCES` and execs the same `BLENDER_APP` binary. `tests/blender/_runner.py` then created its add-on link inside that private directory, pointing at `lane-1/plugins/nmg-game-dev-blender-addon` (confirmed after the run), and no other lane could repoint it. The `blender_mcp.py` host add-on was linked in as well, so `requires_host` tests keep parity. No repository source was changed.

---

## Fixes Applied

None. No source changes were needed; verification only isolated the Blender user-resource path for this run.

## Remaining Issues

### Low

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Low | Testability / infra | `tests/blender/_runner.py` `_install_addon_link` | The headless runner repoints one per-user add-on symlink, which every checkout shares. Concurrent runs from several worktrees can import another checkout's add-on code. | Outside #133's scope, and verify's publication scope covers only this report. Recommend a follow-up issue: have the runner import the add-on from a private path (for example a temp dir with the snake_case link prepended to `sys.path`, or a private `BLENDER_USER_RESOURCES`) instead of the shared user addons directory. |

## Recommendation

Ready for PR.
