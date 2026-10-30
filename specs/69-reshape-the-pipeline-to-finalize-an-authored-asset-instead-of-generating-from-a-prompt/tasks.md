# Tasks: Reshape the pipeline to finalize an authored asset instead of generating from a prompt

**Issue**: #69
**Date**: 2026-10-30
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/30-add-contract-validation-re-import-check-and-review-renders/

## Implementation Tasks

### T001: Request, results, cache keys, and alias index

**File(s)**: `src/nmg_game_dev/pipeline/request.py`, `src/nmg_game_dev/pipeline/result.py`, `src/nmg_game_dev/pipeline/cache.py`
**Type**: Create | Modify
**Depends**: none
**Acceptance**:
- `FinalizeRequest`, `StepResult`, and `FinalizeResult` match design § Modules (AC1, AC3)
- `ArtifactCache.key(step, input_hash, settings_hash)`, directory blobs, and `runs/` aliases match design § Cache, keeping atomic writes and corrupt-entry-as-miss (AC4)

### T002: Blender-side finalize core and entry script

**File(s)**: `plugins/nmg-game-dev-blender-addon/finalize_core/__init__.py`, `plugins/nmg-game-dev-blender-addon/finalize_core/hashing.py`, `plugins/nmg-game-dev-blender-addon/finalize_core/steps.py`, `plugins/nmg-game-dev-blender-addon/finalize_core/load_back.py`, `scripts/blender/finalize_entry.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- `content_hash`, `run_step` for the five Blender steps (design § Steps), and `load_back` (design § Load-back) are implemented; `run_step` emits `NMG_PROGRESS` lines and returns core results or structured errors (AC1, AC2, AC4)
- `finalize_entry.py` writes `<step>.json`, saves `<step>.blend` for mutating steps, and exits 0/1 (AC2)

### T003: Clients, Blender process runner, and job runner

**File(s)**: `src/nmg_game_dev/pipeline/clients/__init__.py`, `src/nmg_game_dev/pipeline/clients/blender_session.py`, `src/nmg_game_dev/pipeline/clients/unreal_mcp.py`, `src/nmg_game_dev/pipeline/blender_proc.py`, `src/nmg_game_dev/pipeline/jobs.py`
**Type**: Create
**Depends**: T001, T002
**Acceptance**:
- The clients, Blender resolution, headless step execution, progress streaming, lock, and crash detection match design § Modules and § Data / Storage Changes (AC2, AC6)

### T004: Steps and finalize orchestration

**File(s)**: `src/nmg_game_dev/pipeline/__init__.py`, `src/nmg_game_dev/pipeline/steps.py`, `src/nmg_game_dev/pipeline/errors.py`, `src/nmg_game_dev/pipeline/prompt.py`, `src/nmg_game_dev/pipeline/stages/`
**Type**: Create | Modify | Delete
**Depends**: T003
**Acceptance**:
- `finalize` and `run_step` run the step table in `STEP_ORDER` with checkpoint, cache lookups, gates, load-back ordering, and `PipelineError` mapping per design (AC1, AC2, AC3, AC4, AC6)
- `prompt.py` and every module under `pipeline/stages/` are deleted; no `Prompt`, `source`, `generate`, or Meshy symbol remains in `src/` (AC1)

### T005: UE import and master material

**File(s)**: `src/nmg_game_dev/unreal/__init__.py`, `src/nmg_game_dev/unreal/import_asset.py`, `scripts/unreal/build_master_material.py`, `plugins/nmg-game-dev-ue-plugin/Content/Materials/M_NmgORM.uasset`
**Type**: Create
**Depends**: T003
**Acceptance**:
- `build_import_code` and the host-side pivot comparison implement design § UE import (AC5)
- `build_master_material.py` creates `M_NmgORM` with the three parameters and wiring; the generated `.uasset` is committed (AC5)

### T006: CLI, MCP server, skill, and `.mcp.json`

**File(s)**: `src/nmg_game_dev/finalize/__init__.py`, `src/nmg_game_dev/finalize/__main__.py`, `mcp-servers/finalize/pyproject.toml`, `mcp-servers/finalize/src/finalize_mcp/__init__.py`, `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json`, `skills/finalize-asset/SKILL.md`, `.mcp.json`
**Type**: Create | Modify
**Depends**: T004, T005
**Acceptance**:
- The CLI subcommands, flags, and exit codes and the three MCP tools with `wait_seconds` behavior match design § API / Interface Changes (AC3)
- `.mcp.json` gains the `finalize` entry with other entries unchanged; `SKILL.md` follows the steering skill template (AC3)

### T007: Steering, docs, and changelog

**File(s)**: `steering/snippets/project-tech.md`, `steering/snippets/project-structure.md`, `docs/mcp/finalize.md`, `CHANGELOG.md`
**Type**: Modify | Create
**Depends**: T006
**Acceptance**:
- Steering meets AC7; the tech snippet's long-running Blender work section describes the job runner, MCP tools, CLI, and load-back rule; the structure snippet lists `finalize_core/`, `mcp-servers/finalize/`, and `src/nmg_game_dev/finalize/` (AC7)
- `docs/mcp/finalize.md` documents the flow, tools, CLI, steps, cache behavior, load-back refusal, and error codes with remediations
- `CHANGELOG.md` `[Unreleased]` gets a `**BREAKING CHANGE:**` bullet ending with `(#69)` and a `### Migration Notes` sub-section describing `pipeline.run(prompt, source)` → `pipeline.finalize(request)`

### T008: Host-side unit and BDD tests

**File(s)**: `tests/unit/pipeline/**`, `tests/unit/test_finalize_cli.py`, `tests/unit/test_finalize_mcp.py`, `tests/unit/test_unreal_import.py`, `tests/unit/test_steering_guards.py`, `tests/bdd/features/finalize.feature`, `tests/bdd/test_finalize_bdd.py`, `tests/bdd/test_pipeline_bdd.py`, `tests/bdd/features/pipeline_*.feature`, `tests/bdd/conftest.py`, `tests/conftest.py`
**Type**: Create | Modify | Delete
**Depends**: T006, T007
**Acceptance**:
- The old prompt/stage tests and the four `pipeline_*.feature` files with `test_pipeline_bdd.py` are removed or rewritten for finalize; fakes cover a fake Blender session client, a fake Unreal client, and a fake runner that executes steps in-process
- Tests cover: step order and result shape (AC1); progress and status polling, load-back replace vs `finalize.session_changed`, and crash → `finalize.job_crashed` with the session untouched (AC2); each single step through `run_step`, the CLI, and the MCP tools including `wait_seconds` (AC3); full cache hits on rerun before and after load-back, a partial miss after a material change, and `--force` (AC4); generated import code containing the texture settings, MI parenting, and parameter names, plus pivot comparison pass and fail, with `UnrealMcpClient` against a stub HTTP server (AC5); each failure class stopping later steps with no import call (AC6); steering guard terms (AC7)
- `finalize.feature` scenarios for AC1, AC3, AC4, and AC6 run under pytest-bdd
- Passes under `repository.tests`, `repository.lint`, and `repository.types`

### T009: Blender headless and live end-to-end tests

**File(s)**: `tests/blender/test_finalize_core.py`, `tests/e2e/test_finalize_e2e.py`, `tests/e2e/test_pipeline_e2e.py`, `tests/e2e/fixtures/`, `tests/e2e/conftest.py`
**Type**: Create | Modify | Delete
**Depends**: T008
**Acceptance**:
- `test_finalize_core.py` covers `content_hash` stability and change detection, `run_step` for validate/bake/variants/export/reimport on a small compliant fixture, and `load_back` replace and refusal (AC1, AC2, AC4); passes under `scripts/run-blender-tests.sh` with `BLENDER_APP` set
- `test_finalize_e2e.py` (`--runslow`) finalizes a fixture crate from a `.blend` through Blender 5.2 and UE 5.8 and asserts the UE folders, identical names, texture settings, `MI_*` parameters, and part pivots (AC5); `test_pipeline_e2e.py` and `fixture_prompt.json` are removed

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #69 | 2026-10-30 | Initial feature tasks |
