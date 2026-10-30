# Tasks: Contract validation, re-import check, and review renders

**Issue**: #30
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Contract validation core

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/__init__.py`, `plugins/nmg-game-dev-blender-addon/contract_core/report.py`, `plugins/nmg-game-dev-blender-addon/contract_core/validate.py`, `plugins/nmg-game-dev-blender-addon/contract_core/geometry.py`, `plugins/nmg-game-dev-blender-addon/contract_core/uv.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- `validate_asset` produces the report schema and every rule id in design § Data / Storage Changes, using `utils/budgets.py` for budgets (FR1, AC1, AC2)
- Checks run on copies or evaluated data and never change the scene

### T002: Re-import check

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/reimport.py`, `scripts/blender/contract_entry.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- `reimport_check` implements AC3 with the `reimport.*` rules; `run_isolated` spawns `bpy.app.binary_path --background --factory-startup` running `contract_entry.py` and returns its JSON (FR2)
- `contract_entry.py` supports `validate`, `reimport`, and `render` subcommands and writes `--report` JSON

### T003: Review renders and texture proof

**File(s)**: `plugins/nmg-game-dev-blender-addon/contract_core/render.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- `render_review` and `render_texture_proof` implement AC4 and AC5 with the design rig, file layout, ORM wiring, and labeled proof sheet, leaving user scenes unchanged (FR3)

### T004: Operators

**File(s)**: `plugins/nmg-game-dev-blender-addon/operators/validate_contract.py`, `plugins/nmg-game-dev-blender-addon/operators/reimport_check.py`, `plugins/nmg-game-dev-blender-addon/operators/render_review.py`, `plugins/nmg-game-dev-blender-addon/operators/__init__.py`, `plugins/nmg-game-dev-blender-addon/__init__.py`, `plugins/nmg-game-dev-blender-addon/panels/main_panel.py`
**Type**: Create | Modify
**Depends**: T002, T003
**Acceptance**:
- The three operators are registered with the design properties, call `contract_core`, write `report_path` when set, store `last_result`, and return `CANCELLED` with findings reported on failure (FR4, AC7)
- The panel lists the new operators

### T005: Host-side models, gate, and CLI

**File(s)**: `src/nmg_game_dev/quality/contract.py`, `src/nmg_game_dev/contract/__init__.py`, `src/nmg_game_dev/contract/__main__.py`, `src/nmg_game_dev/contract/blender.py`
**Type**: Create
**Depends**: T002
**Acceptance**:
- `ContractReport` / `Finding` parse the report JSON; `gate` raises `PipelineError` `quality.contract_failed` / `quality.reimport_mismatch` with stage `quality`, the findings in the message, and the report attached (FR5, AC6)
- The CLI resolves Blender per design, runs `contract_entry.py`, and exits 0 / 1 / 2 (AC7)

### T006: Docs and changelog

**File(s)**: `docs/asset-contract.md`, `CHANGELOG.md`
**Type**: Modify
**Depends**: T005
**Acceptance**:
- Contract §8 names the validator, re-import check, review renders, and proof sheet as the standard tools for steps 1–4, with the CLI and operator names
- `CHANGELOG.md` `[Unreleased]` gets a bullet ending with `(#30)`

### T007: Host-side unit tests

**File(s)**: `tests/unit/quality/test_contract_gate.py`, `tests/unit/test_contract_cli.py`
**Type**: Create
**Depends**: T005
**Acceptance**:
- Covers AC6 (each kind raises the right code with findings and report; a passing report returns) and AC7's CLI exits. The CLI tests use a stub Blender executable that writes a fixed report, and a missing-Blender case exits 2 with a remediation
- Passes under the `repository.tests`, `repository.lint`, and `repository.types` validations

### T008: Blender headless tests

**File(s)**: `tests/blender/contract_fixtures.py`, `tests/blender/test_contract_validate.py`, `tests/blender/test_contract_reimport.py`, `tests/blender/test_contract_render.py`
**Type**: Create
**Depends**: T004
**Acceptance**:
- `contract_fixtures.py` builds a compliant `Crate` asset (baked-style material with generated PNGs) and one fixture per AC2 failure class
- `test_contract_validate.py` covers AC1 and AC2 (each rule id, compliant pass, scene unchanged)
- `test_contract_reimport.py` covers AC3 (pass after export, `reimport.texture_missing` after deleting a PNG, run through `run_isolated`)
- `test_contract_render.py` covers AC4 (eight files at a test resolution of 128, scenes unchanged) and AC5 (proof sheet with and without a pre-bake image); also AC7, where an operator and a direct call produce identical reports
- Passes with `BLENDER_APP` set to Blender 5.2 under `scripts/run-blender-tests.sh`

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #30 | 2026-10-29 | Initial feature tasks |
