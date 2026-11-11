# Defect Report: Contract UV overlap validation hangs for hours on stacked UVs

**Issue**: #133
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Reproduction

1. In Blender, create an asset collection whose mesh has at least 100k triangles and a single `UVMap` produced by UV → Reset, so every face covers the full 0–1 UV square. Use an asset class that runs the overlap check (any class except `environment_piece`).
2. Run the finalize `validate` step on the collection through `finalize_asset` or `run_finalize_step`.
3. Poll `get_finalize_job`.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | Validate fails with `uv.overlap` within seconds. While it runs, `get_finalize_job` shows which mesh and check validate is on. Large non-overlapping layouts finish the overlap check quickly with the same pass/fail result as before. |
| **Actual** | Validate runs at 100% CPU for hours with progress stuck at 0 and no message beyond "started", then fails `uv.overlap`. |

## Acceptance Criteria

### AC1: Stacked UVs fail fast

**Given** a mesh with at least 100k triangles whose faces all have reset (full 0–1 square) UVs and whose asset class runs the overlap check
**When** contract validation runs on it
**Then** it reports a `uv.overlap` finding, and the overlap check for that mesh finishes within 10 seconds

### AC2: Early exit never changes the outcome

**Given** any set of UV faces
**When** the overlap fraction is computed
**Then** it exceeds `OVERLAP_LIMIT` exactly when the full rasterization of those faces would exceed `OVERLAP_LIMIT`, and rasterizing stops as soon as the shared-texel count exceeds `OVERLAP_LIMIT × GRID²`

### AC3: Early-exit message is truthful

**Given** a mesh where the overlap check stopped early
**When** the `uv.overlap` finding is reported
**Then** its message states the overlap as a lower bound (for example "at least X% of covered UV texels are shared") and still names the limit

### AC4: Large valid layouts stay fast and correct

**Given** a mesh with at least 200k triangles and a non-overlapping UV layout
**When** contract validation runs on it
**Then** it reports no `uv.overlap` finding, and the overlap check for that mesh finishes within 30 seconds

### AC5: Existing overlap behavior is preserved

**Given** the existing contract-validate and bake-unique fixtures (clean asset, the `uv_overlap` defect, overlapping layouts that bake unwraps, valid layouts that bake keeps)
**When** validation and the bake UV check run on them
**Then** every fixture produces the same pass/fail result and finding codes as before this change

### AC6: Validate reports per-check progress

**Given** a finalize job running the `validate` step on a collection with several meshes
**When** `get_finalize_job` is polled during validation
**Then** the job's step is `validate`, its progress rises between 0 and 1 as meshes and checks finish, and its message names the current object and check (for example the UV overlap check on a named mesh)

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | The UV overlap computation stops rasterizing once the shared-texel count exceeds `OVERLAP_LIMIT × GRID²` and reports a fraction above `OVERLAP_LIMIT` | Must |
| FR2 | UV triangle rasterization is vectorized with numpy (Blender's bundled numpy) instead of per-texel Python loops, with the same texel-center coverage rule, `GRID`, and `OVERLAP_LIMIT` | Must |
| FR3 | `polygon_overlap_fraction` keeps its signature and pass/fail semantics for its callers in `contract_core/uv.py` and `bake_core/uv.py` | Must |
| FR4 | A `uv.overlap` finding produced by an early exit states the overlap as a lower bound | Must |
| FR5 | The `validate` step emits `NMG_PROGRESS` lines (step `validate`, progress strictly between 0 and 1, message naming the object and check) as it moves through meshes and checks, so `get_finalize_job` shows them | Must |
| FR6 | UV overlap is computed from the mesh UV data in bulk (for example `foreach_get`) rather than per-loop Python attribute access | Should |

## Out of Scope

- Changing `GRID`, `OVERLAP_LIMIT`, or which asset classes run the overlap check
- An area-sum heuristic pre-check that could fail meshes the full check would pass
- Progress reporting for finalize steps other than `validate`
- The texel-density check used for `environment_piece` assets

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #133 | 2026-11-11 | Initial defect report |
