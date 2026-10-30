# Tasks: Remove Meshy from the pipeline and MCP config

**Issue**: #64
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Remove the Meshy route and client types

**File(s)**: `src/nmg_game_dev/pipeline/__init__.py`, `src/nmg_game_dev/pipeline/stages/_base.py`, `src/nmg_game_dev/pipeline/stages/_mcp.py`, `src/nmg_game_dev/pipeline/stages/generate.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `run` raises `pipeline.unsupported_source` for any source other than `"blender"`, before the `mcp_clients` check, any MCP call, or any cache write (FR1, AC2)
- `MeshyMcp`, `McpClients.meshy`, `generate_meshy`, and the `meshy` server literal and remediation are gone; docstrings mention Blender only (FR2, AC3)
- The Blender run is unchanged (AC1)

### T002: Remove the Meshy MCP server and update the scaffold contract

**File(s)**: `.mcp.json`, `tests/_scaffold_contract.py`, `tests/unit/test_scaffold_guards.py`, `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature`, `tests/bdd/steps/test_scaffold.py`
**Type**: Modify
**Depends**: none
**Acceptance**:
- `.mcp.json` has only the `blender` and `unreal` entries, unchanged; `REQUIRED_SERVERS == ("blender", "unreal")`; `test_mcp_json_has_no_meshy` replaces the Meshy env guard; the AC8 scaffold step names two servers (FR3, AC4)
- `test_steering_snippets_do_not_offer_meshy` scans `steering/snippets/*.md` for the AC5 strings (FR5, AC5)

### T003: Remove Meshy fakes and tests; add unsupported-source and type coverage

**File(s)**: `tests/conftest.py`, `tests/unit/pipeline/test_run.py`, `tests/unit/pipeline/test_no_meshy.py`, `tests/unit/pipeline/stages/test_generate.py`, `tests/unit/pipeline/stages/test_cleanup.py`, `tests/unit/pipeline/stages/test_quality.py`, `tests/bdd/features/pipeline_meshy_supplement.feature`, `tests/bdd/features/pipeline_unsupported_source.feature`, `tests/bdd/features/pipeline_blender_first.feature`, `tests/bdd/features/pipeline_idempotency.feature`, `tests/bdd/features/pipeline_quality_halt.feature`, `tests/bdd/test_pipeline_bdd.py`, `tests/bdd/conftest.py`, `tests/e2e/test_pipeline_e2e.py`, `tests/e2e/conftest.py`
**Type**: Create | Modify | Delete
**Depends**: T001
**Acceptance**:
- No file under `src/`, `tests/`, or `.mcp.json` contains `meshy` (case-insensitive), except the guard tests' banned-string literals and the unsupported-source tests' `"meshy"` input (FR4)
- `test_unsupported_source_rejected` and the `pipeline_unsupported_source.feature` scenario cover AC2; `test_no_meshy.py` covers AC3; the Blender-first BDD scenario still passes (AC1)
- `pytest tests/unit/` and `pytest tests/bdd/` pass, along with the `repository.tests`, `repository.lint`, and `repository.types` validations (`ruff check .`, `ruff format --check .`, `mypy src/ tests/`)

### T004: Changelog

**File(s)**: `CHANGELOG.md`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- `[Unreleased]` gets a bullet saying the Meshy pipeline source, client types, and MCP server are removed and that `pipeline.run` rejects non-Blender sources with `pipeline.unsupported_source`, ending with `(#64)`

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #64 | 2026-10-29 | Initial feature tasks |
