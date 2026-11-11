# Root Cause Analysis: Contract UV overlap validation hangs for hours on stacked UVs

**Issue**: #133
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley

## Root Cause

`plugins/nmg-game-dev-blender-addon/contract_core/uv.py` computes the overlap fraction in `polygon_overlap_fraction` by fanning each face into triangles and rasterizing each triangle with `_rasterize`. `_rasterize` loops in pure Python over every texel center in the triangle's clamped bounding box on the `GRID × GRID` (512×512) grid and evaluates three edge functions per texel. When every face spans the full UV square, each triangle costs about 262k Python-level texel tests, so the total is triangles × 262k. The loop never stops early. Yet the covered-texel count can never exceed `GRID²`, so once the shared-texel count passes `OVERLAP_LIMIT × GRID²` (about 1,311 texels) the fraction must exceed `OVERLAP_LIMIT`. `overlap_fraction` also reads every loop's UV through per-index `uv_data[index].uv.x/.y` attribute access. `bake_core/uv.py` `layout_is_valid` calls the same `polygon_overlap_fraction`, so the bake UV check has the same cost.

Progress: `finalize_core/steps.py` `run_step` calls `_progress(step, 0.0, "started")` and `_progress(step, 1.0, …)` only. `contract_core/validate.py` `validate_asset` → `_mesh_findings` iterates meshes and checks without reporting anything, so the job's `status.json` that `get_finalize_job` reads stays at `progress=0`, `message="started"` for the whole step. The host side already relays every `NMG_PROGRESS` line: `pipeline/blender_proc.py` `_progress_event` → `pipeline/engine.py` `_progress_callback` → `pipeline/jobs.py` `on_progress` writes `step`, `progress`, and `message` into `status.json`.

## Affected Code

| File | Symbol / Area | Role |
|------|---------------|------|
| `plugins/nmg-game-dev-blender-addon/contract_core/uv.py` | `polygon_overlap_fraction`, `_rasterize`, `_fan`, `overlap_fraction`, `uv_findings` | Per-texel Python rasterization with no early exit; per-loop UV reads; finding message |
| `plugins/nmg-game-dev-blender-addon/bake_core/uv.py` | `layout_is_valid` | Calls `polygon_overlap_fraction`; inherits the cost (no source change needed) |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | `validate_asset`, `_mesh_findings` | Mesh/check loop with no progress reporting |
| `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py` | `_validate`, `_progress` | Emits `NMG_PROGRESS` only at 0.0 and 1.0 |

## Fix Strategy

### 1. Vectorized, early-exiting overlap core (`contract_core/uv.py`)

Add an internal core that takes triangles as numpy arrays — corner coordinates already scaled to texel units, shape `(T, 3, 2)` float64, and the owning face id per triangle, shape `(T,)` int — and returns an `OverlapResult` (a small frozen dataclass or NamedTuple: `fraction: float`, `exact: bool`, `triangles_rasterized: int`, `triangles_total: int`).

Coverage rule, identical to the current `_rasterize` and evaluated in float64:

- skip a triangle when `abs(twice_area) < 1e-12`; `sign` is the sign of `twice_area`;
- clamp the bounding box: `x0 = max(0, floor(min x))`, `x1 = min(GRID - 1, ceil(max x))`, same for y; an empty box (`x0 > x1` or `y0 > y1`) covers nothing;
- the texel center is `(col + 0.5, row + 0.5)`; it is covered when all three signed edge functions `w0`, `w1`, `w2` (same formulas and operand order as `_rasterize`) are `>= 0`.

Ownership rule, identical to the current owner/shared arrays: a texel is covered when any face covers it, and shared when two or more distinct face ids cover it. Two fan triangles of the same face never make a texel shared.

Vectorization: process triangles in input order in batches. A batch holds whole triangles and at most `_BATCH_TEXELS = 1 << 20` candidate texels, summed over the triangles' clamped bounding boxes. A single triangle whose box exceeds that bound is its own batch. For a batch, expand every triangle's bounding-box texels into flat arrays (for example `np.repeat` of per-triangle box sizes plus offsets), evaluate the edge functions vectorized, and keep the `(texel index, face id)` hits. Merge the hits into a persistent `owner` int array (`-1` = uncovered) and a `shared` bool array of size `GRID²`. Per texel in the batch, take the min and max face id among its hits (for example via `np.minimum.at`/`np.maximum.at`, or a sort plus `np.unique`). A texel becomes shared when its batch min ≠ batch max, or when its existing owner is neither `-1` nor equal to the batch face ids. Uncovered texels take the batch min as owner. The result equals sequential per-triangle processing because "shared" depends only on the set of distinct faces covering a texel.

Early exit (FR1): after each batch, if `shared.sum() > OVERLAP_LIMIT * GRID * GRID`, stop and return `OverlapResult(fraction=shared_count / (GRID * GRID), exact=False, …)`. Covered ≤ `GRID²`, and the shared count only grows, so the full-rasterization fraction is ≥ `shared_count / covered_final` ≥ `shared_count / GRID²` > `OVERLAP_LIMIT`. The pass/fail outcome is therefore identical (AC2), and `shared_count / GRID²` is a true lower bound of the full fraction (AC3). When no early exit fires, every triangle is rasterized and the result is `shared / covered` exactly as today (`0.0` when nothing is covered), with `exact=True`.

Public surface:

- `polygon_overlap(faces: Iterable[tuple[int, Sequence[Point]]]) -> OverlapResult` builds the fan triangles (`points[0], points[i], points[i+1]`, in UV × `GRID`) into arrays and calls the core.
- `polygon_overlap_fraction(faces)` keeps its exact signature and returns `polygon_overlap(faces).fraction`. On early exit the returned value is the lower bound, which is above `OVERLAP_LIMIT`, so `bake_core/uv.py`'s `> OVERLAP_LIMIT` test is unchanged (FR3).
- `mesh_overlap(mesh, uv_data) -> OverlapResult` reads in bulk (FR6): `uv_data.foreach_get("uv", …)` into a flat float array reshaped `(loops, 2)`, `mesh.polygons.foreach_get("loop_start", …)` and `("loop_total", …)`, and builds the fan triangle index arrays with numpy (corner 0 = `loop_start`, corners `loop_start + k`, `loop_start + k + 1` for `k = 1 .. loop_total - 2`), with face id = polygon index. `overlap_fraction(mesh, uv_data)` keeps its signature and returns `mesh_overlap(...).fraction`.
- Remove `_rasterize` and the `array`/`math` per-texel path. `_fan` may stay only if still used.

`import numpy as np` comes from Blender's bundled numpy; the add-on gains no new dependency.

### 2. Lower-bound finding message (`uv_findings`)

`uv_findings` calls `mesh_overlap`. When `fraction > OVERLAP_LIMIT`:

- `exact=True`: the message is unchanged — `"{name}: {fraction:.1%} of covered UV texels are shared by two or more faces; the limit is {OVERLAP_LIMIT:.1%}."`
- `exact=False`: `"{name}: at least {fraction:.1%} of covered UV texels are shared by two or more faces; the limit is {OVERLAP_LIMIT:.1%}."`

The rule code stays `uv.overlap`; target and remediation come from `finding()` as today.

### 3. Validate progress (`validate.py`, `steps.py`)

`validate_asset` gains a keyword-only `progress: Callable[[float, str], None] | None = None`, threaded into `_mesh_findings`. Before the loop, compute the total work units: for every variant, every mesh object, one unit per check that runs on it — `geometry`, then `UV overlap` when `check_overlap` (otherwise `UV map`), then `texel density` when the class is `environment_piece`. Before each unit, call `progress(done_units / total_units, f"{variant}: {check} check on {obj.name}")` (for example `desktop: UV overlap check on SM_Crate`). With `progress=None`, behavior and report are unchanged.

`finalize_core/steps.py` `_validate` passes a callback that emits `_progress("validate", p, message)` with `p` mapped strictly inside (0, 1): `0.01 + 0.98 * fraction`, so the value stays strictly between 0 and 1 after `_progress` rounds to 3 decimals. The 0.0 `started` and 1.0 final lines in `run_step` are unchanged. No host-side change is needed: the existing relay writes these events into `status.json`, which `get_finalize_job` returns.

## Changes

| File | Change | Behavioral reason |
|------|--------|-------------------|
| `plugins/nmg-game-dev-blender-addon/contract_core/uv.py` | numpy batched rasterizer core, `OverlapResult`, `polygon_overlap`, `mesh_overlap` (bulk `foreach_get`), early exit, lower-bound message; `polygon_overlap_fraction`/`overlap_fraction` keep their signatures | AC1–AC5, FR1–FR4, FR6 |
| `plugins/nmg-game-dev-blender-addon/contract_core/validate.py` | optional `progress` callback through `validate_asset` → `_mesh_findings`, one call per mesh/check unit | AC6, FR5 |
| `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py` | `_validate` passes a callback that emits `NMG_PROGRESS` for step `validate` with progress strictly in (0, 1) | AC6, FR5 |
| `tests/blender/test_contract_uv_overlap.py` | new Blender-headless tests for AC1–AC4 | AC1–AC4 |
| `tests/blender/test_finalize_core.py` | validate-step progress-line test | AC6 |
| `tests/unit/pipeline/test_jobs.py` | mid-step validate progress event reaches the job status | AC6 |

## Blast Radius

- `bake_core/uv.py` `layout_is_valid` → `polygon_overlap_fraction`: same signature and pass/fail result; faster. Its other per-loop reads (`faces_of`, the 0–1 bounds loop) are unchanged.
- `validate_asset` is also called by the contract CLI/operator (`contract_entry.py`, operator in the add-on) without `progress`; its report is unchanged.
- The `uv.overlap` message text changes only for early-exit results, which previously took hours to produce.
- The `NMG_PROGRESS` line format is unchanged; only more lines are emitted for validate.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| numpy batched rasterization + shared-count early exit | Selected | Same coverage rule and outcome; fast on both stacked and large valid layouts |
| Early exit only, keep pure-Python rasterizer | Rejected | Fixes stacked UVs, but a 200k-tri valid layout still runs Python per texel and misses AC4 |
| UV-area-sum pre-check | Rejected | Could fail meshes the full check passes; out of scope in the issue |
| Lower `GRID` or raise `OVERLAP_LIMIT` | Rejected | Changes the contract; out of scope |
| Per-triangle numpy calls with no batching | Rejected | Per-call overhead × 200k+ small triangles risks the AC4 bound |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #133 | 2026-11-11 | Initial defect design |
