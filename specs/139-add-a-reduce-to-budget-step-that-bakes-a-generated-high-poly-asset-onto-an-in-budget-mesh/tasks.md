# Tasks: Reduce a generated high-poly asset to its Desktop budget and bake its look onto the reduced mesh

**Issue**: #139
**Date**: 2026-11-11
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/67-bake-authored-materials-to-contract-compliant-uv-texture-sets/

## Implementation Tasks

### T001: Pure-Python reduce plan

**File(s)**: `plugins/nmg-game-dev-blender-addon/reduce_core/__init__.py`, `plugins/nmg-game-dev-blender-addon/reduce_core/plan.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- `DEFAULTS`, `ReduceError`, `split_budget`, `bake_settings`, `unbaked_share`, and `check_misses` behave as the design states.
- `split_budget` covers the area split, the 12-triangle minimum, never targeting above the source triangles, and the three override errors (AC3, AC4, AC7, AC8, AC9).
- The module loads by path with no `bpy` import.

### T002: Reduce core in Blender

**File(s)**: `plugins/nmg-game-dev-blender-addon/reduce_core/core.py`, `plugins/nmg-game-dev-blender-addon/reduce_core/decimate.py`, `plugins/nmg-game-dev-blender-addon/reduce_core/transfer.py`, `plugins/nmg-game-dev-blender-addon/reduce_core/commit.py`, `plugins/nmg-game-dev-blender-addon/bake_core/bake.py`, `plugins/nmg-game-dev-blender-addon/bake_core/state.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- `reduce_asset` runs the guard, sources, plan, build copies, atlas, bake, coverage, pack, and commit steps from the design. It returns the result shape (FR11).
- It reduces to the budget, keeping names, transforms, origins, and parents (AC1, FR1). It keeps the originals in the hidden `<Name>_High` (AC2, FR2). It builds one atlas (AC5, FR4) and bakes per part into `T_<Name>_Body_{BC,N,ORM}` with `M_<Name>_Body` and packed images (AC6, FR5, FR8).
- It honors cage and ray settings (AC7, FR6), reports `unbaked_share` (AC8), and fails `reduce.bake_misses` with the scene unchanged (AC9, FR7).
- It rebuilds from `<Name>_High` (AC11). It leaves an in-budget asset unchanged (AC12). It refuses an armature and `terrain` (AC13, FR9).
- `run_for_mcp` returns the result or `{"error": ...}` (AC14).

### T003: Finalize integration for reduced assets

**File(s)**: `plugins/nmg-game-dev-blender-addon/bake_core/core.py`, `plugins/nmg-game-dev-blender-addon/contract_core/validate.py`, `plugins/nmg-game-dev-blender-addon/finalize_core/load_back.py`, `scripts/blender/finalize_session.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- A tagged `environment_piece` bakes in unique mode and is validated with the UV overlap check (AC10).
- `load_back` accepts `suffixes`, keeps the `_High` hidden flags, and defaults to `("", "_Mobile")` (AC14).
- `<Name>_High` stays outside validation, hashing, and export (AC2).

### T004: Background reduce job, CLI, and MCP tool

**File(s)**: `plugins/nmg-game-dev-blender-addon/finalize_core/reduce_job.py`, `scripts/blender/finalize_entry.py`, `src/nmg_game_dev/pipeline/reduce.py`, `src/nmg_game_dev/pipeline/engine.py`, `src/nmg_game_dev/pipeline/jobs.py`, `src/nmg_game_dev/pipeline/blender_proc.py`, `src/nmg_game_dev/finalize/__main__.py`, `src/nmg_game_dev/finalize/mcp_tools.py`, `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json`
**Type**: Create
**Depends**: T002, T003
**Acceptance**:
- `finalize_entry.py reduce` writes the `reduce.json` envelope and `reduce.blend`.
- `ReduceRequest` validates its inputs.
- `jobs.start_reduce` creates a `kind: "reduce"` job that shares the lock and status. `get_finalize_job` reports it.
- `execute_reduce` checkpoints, runs, and loads back `<Name>` and `<Name>_High` only on a hash match. Otherwise it fails with `reduce.session_changed` (AC14, FR10).
- The CLI `reduce` and the MCP `reduce_asset` (with `wait_seconds` clamped to 150) return the same result shape. `gate-mcp-schema` passes.

### T005: Panel operator

**File(s)**: `plugins/nmg-game-dev-blender-addon/operators/reduce_to_budget.py`, `plugins/nmg-game-dev-blender-addon/operators/__init__.py`, `plugins/nmg-game-dev-blender-addon/panels/main_panel.py`
**Type**: Create
**Depends**: T002
**Acceptance**:
- `nmggamedev.reduce_to_budget` calls `reduce_asset` with its properties and reports the summary or the error code (AC14, FR10).

### T006: Documentation

**File(s)**: `docs/asset-contract.md`, `docs/mcp/finalize.md`, `docs/skills/reduce-to-budget.md`, `docs/skills/bake-materials.md`, `skills/finalize-asset/SKILL.md`
**Type**: Modify
**Depends**: T004, T005
**Acceptance**:
- The contract documents `<Name>_High`, `nmg_reduced`, and the changed §5 Desktop rule: a reduce run may decimate Desktop before finalize.
- The finalize MCP doc documents `reduce_asset`.
- The tool doc covers inputs, defaults, errors, and the result.
- The bake doc covers unique mode for a tagged `environment_piece`.
- The skill tells the agent to run `reduce_asset` when validate reports `budget.tris` on a generated asset (FR12).

### T007: Tests

**File(s)**: `tests/unit/test_reduce_plan.py`, `tests/unit/pipeline/test_reduce_job.py`, `tests/unit/test_finalize_mcp.py`, `tests/unit/test_finalize_cli.py`, `tests/blender/reduce_fixtures.py`, `tests/blender/test_reduce.py`, `tests/blender/test_reduce_finalize.py`, `tests/bdd/features/reduce_to_budget.feature`, `tests/bdd/test_reduce_to_budget_bdd.py`
**Type**: Create
**Depends**: T001, T002, T003, T004, T005
**Acceptance**:
- CPython unit tests load `plan.py` by path. They cover the area split, the minimum and source caps, each override error, settings resolution, and `unbaked_share` and `check_misses` (AC3, AC4, AC7, AC8, AC9).
- Host tests with the fake step runner and a fake session client cover these paths. No live Blender is involved (AC14):
  - the job kind and status;
  - a session load-back with `suffixes=("", "_High")`;
  - a hash mismatch, which gives `reduce.session_changed`;
  - a `within_budget` result, which loads nothing;
  - the CLI and MCP result shapes;
  - the `wait_seconds` clamp.
- Headless Blender tests (`gate-blender-headless`) use small fixtures built in code. One is a three-part asset of about 20k triangles with vertex-color, procedural, and image materials. The Desktop budget is overridden to 3,000 triangles and the texture size to 256 px. The tests cover:
  - the budget, names, and parents (AC1);
  - `_High` contents, flags, and exclusion from the hash, validation, and export (AC2);
  - per-part targets (AC3);
  - overrides (AC4);
  - the atlas, through `contract_core.uv.uv_findings` (AC5);
  - the BC color of each part, matching its source within tolerance, and the packing and color spaces (AC6);
  - cage and ray values in the result (AC7);
  - `unbaked_share` (AC8);
  - a 0.0001 m ray distance, which forces `reduce.bake_misses` and leaves an unchanged scene snapshot (AC9);
  - a rerun with different settings that rebuilds without touching `_High` (AC11);
  - an in-budget asset that is unchanged (AC12);
  - an armature and `terrain`, which are refused unchanged (AC13);
  - the operator and `run_for_mcp` giving the same result shape (AC14).
- `test_reduce_finalize.py` runs `finalize_core.run_step` validate, bake, variants, export, and reimport on a reduced `standard_prop` and on a reduced `environment_piece`. Both pass with the atlas kept (AC10).
- BDD scenarios SCN001–SCN012 bind to the plan module and the host fakes.
- Evidence:
  - `uv run pytest tests/unit tests/bdd -q` (`repository.tests`);
  - `repository.lint`, `repository.format`, `repository.types`;
  - `gate-blender-headless`;
  - `gate-mcp-schema`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #139 | 2026-11-11 | Initial feature tasks |
