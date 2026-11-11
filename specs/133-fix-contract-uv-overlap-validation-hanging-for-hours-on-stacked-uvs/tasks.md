# Tasks: Contract UV overlap validation hangs for hours on stacked UVs

**Issue**: #133
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Vectorize the UV overlap rasterizer with an outcome-preserving early exit

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/uv.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- Rasterization uses numpy in batches of whole triangles (at most `1 << 20` candidate texels per batch, an oversized triangle alone), with the existing degenerate-triangle skip, clamped bounding box, texel-center `(col + 0.5, row + 0.5)` sampling, inclusive `>= 0` edge-function test, and distinct-face shared rule; `GRID = 512` and `OVERLAP_LIMIT = 0.005` are unchanged (FR2).
- After each batch, if the shared-texel count exceeds `OVERLAP_LIMIT * GRID * GRID`, rasterization stops and the result is `OverlapResult(fraction=shared / GRID², exact=False, …)`; otherwise the result is the full `shared / covered` (0.0 when nothing is covered) with `exact=True` (FR1, AC2).
- `polygon_overlap(faces)` and `mesh_overlap(mesh, uv_data)` return `OverlapResult` with `fraction`, `exact`, `triangles_rasterized`, `triangles_total`; `mesh_overlap` reads UVs and polygon `loop_start`/`loop_total` with `foreach_get` and builds fan triangles with numpy (FR6).
- `polygon_overlap_fraction(faces)` and `overlap_fraction(mesh, uv_data)` keep their signatures and return the result's `fraction`; `bake_core/uv.py` needs no change (FR3).
- The pure-Python `_rasterize` per-texel loop is removed.

### T002: State early-exit overlap findings as a lower bound

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/uv.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- `uv_findings` uses `mesh_overlap`; an exact result over the limit keeps the current message, and an early-exit result reads `"{name}: at least {fraction:.1%} of covered UV texels are shared by two or more faces; the limit is {OVERLAP_LIMIT:.1%}."` (FR4, AC3).
- The rule code remains `uv.overlap` (AC5).

### T003: Emit per-mesh, per-check progress from the validate step

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/validate.py`, `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `validate_asset` accepts keyword-only `progress: Callable[[float, str], None] | None = None` and, through `_mesh_findings`, calls it before each mesh/check unit (`geometry`, `UV overlap` or `UV map`, and `texel density` for `environment_piece`) with `done_units / total_units` and a message `"{variant}: {check} check on {object name}"`; with `progress=None` the report is unchanged.
- `steps._validate` passes a callback emitting `NMG_PROGRESS` with step `validate`, progress `0.01 + 0.98 * fraction` (strictly between 0 and 1 after rounding), and the message (FR5, AC6).
- The `started` (0.0) and final (1.0) progress lines from `run_step` are unchanged.

### T004: Add regression tests for stacked, early-exit, and large valid UV layouts

**File(s)**: `tests/blender/test_contract_uv_overlap.py`
**Type**: Create
**Depends**: T001, T002
**Acceptance**:
- AC1: a `Crate` whose `SM_Crate` mesh is replaced by a grid of at least 100k triangles with every face's UVs on the full unit square (asset class `standard_prop`): timing `uv_findings` (via the enabled add-on's `contract_core.uv`) on that mesh shows it finishes in under 10 s and returns a `uv.overlap` finding, and `validate_asset("Crate", "standard_prop")` reports a `uv.overlap` finding.
- AC2: against a reference copy of the pre-change pure-Python rasterizer kept in the test file, `polygon_overlap_fraction` gives the same `> OVERLAP_LIMIT` outcome on a set of seeded random face sets (overlapping, non-overlapping, out-of-range, degenerate, and multi-corner polygons); for non-early-exit cases the fraction equals the reference value; for 1,000 stacked full-square quads `polygon_overlap` returns `exact=False`, a fraction above `OVERLAP_LIMIT`, and `triangles_rasterized < triangles_total`.
- AC3: the stacked-mesh `uv.overlap` finding message contains `at least` and the limit text `0.5%`.
- AC4: a mesh of at least 200k triangles with a non-overlapping grid UV layout (each quad in its own cell): `uv_findings` finishes in under 30 s and returns no `uv.overlap` finding, and `validate_asset` reports no `uv.overlap` finding.
- Runs under `gate-blender-headless` (`scripts/run-blender-tests.sh`) and fails against the pre-change implementation (timeout or missing `at least`).

### T005: Prove existing overlap fixtures are unchanged

**File(s)**: `tests/blender/test_contract_validate.py`, `tests/blender/test_bake_unique.py`
**Type**: Modify
**Depends**: T001, T002
**Acceptance**:
- AC5: the existing tests `test_ac1_compliant_crate_passes_with_snapshots`, `test_ac2_each_failure_class_fails_with_its_rule` (including `uv_overlap` → `uv.overlap`), `test_validation_leaves_the_scene_unchanged`, `test_ac1_valid_existing_layout_is_kept`, and `test_ac1_overlapping_layout_is_unwrapped` pass unmodified in their assertions under `gate-blender-headless`.
- An added test in `tests/blender/test_contract_validate.py` asserts that the `uv_overlap` defect, whose six faces each cover the full unit square, still yields rule `uv.overlap` and that its message uses the lower-bound form (`at least`) and names the limit `0.5%`.

### T006: Test validate-step progress lines and their relay into the job status

**File(s)**: `tests/blender/test_finalize_core.py`, `tests/unit/pipeline/test_jobs.py`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- AC6 (Blender): running `run_step("validate", …)` on the built `Crate` (Desktop `SM_Crate` plus Mobile LOD0–2 meshes) prints `NMG_PROGRESS` lines, captured with `capfd`, between the `started` and final lines, each with `step == "validate"` and `0 < progress < 1`, progress non-decreasing, at least one line per mesh, and a message naming the object and check (for example `UV overlap check on SM_Crate`). Runs under `gate-blender-headless`.
- AC6 (host): in `tests/unit/pipeline/test_jobs.py`, a fake step runner that emits a validate event `{"state": "running", "step": "validate", "progress": 0.5, "message": "desktop: UV overlap check on SM_Crate"}` mid-step causes `jobs.status(job_id)` read during that step to report `step == "validate"`, `progress == 0.5`, and that message. Runs under `repository.tests`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #133 | 2026-11-11 | Initial defect tasks |
