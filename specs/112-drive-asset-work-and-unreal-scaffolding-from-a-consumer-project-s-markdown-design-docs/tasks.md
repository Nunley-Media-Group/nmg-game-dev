# Tasks: Drive asset work and Unreal scaffolding from a consumer project's markdown design docs

**Issue**: #112
**Date**: 2026-10-31
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt/

## Implementation Tasks

### T001: Design contract document

**File(s)**: `docs/design-contract.md`
**Type**: Create
**Depends**: none
**Acceptance**:
- It documents `docs/design/` with one file per entity, the frontmatter table, asset-name derivation, statuses, the backlog shape, the `sync` and `scaffold` commands, report-line format, and every `design.*` code (FR1).

### T002: Design parser, backlog, and sync command

**File(s)**: `src/nmg_game_dev/design/__init__.py`, `src/nmg_game_dev/design/paths.py`, `src/nmg_game_dev/design/model.py`, `src/nmg_game_dev/design/parse.py`, `src/nmg_game_dev/design/backlog.py`, `src/nmg_game_dev/design/__main__.py`, `pyproject.toml`, `uv.lock`, `mcp-servers/finalize/uv.lock`, `mcp-servers/texture-gen/uv.lock`
**Type**: Create
**Depends**: T001
**Acceptance**:
- `sync` implements AC1–AC3 as designed: sorted, atomic, byte-stable output, status preservation, `orphaned` handling, and every `design.*` error reported with the backlog untouched (FR2–FR4).
- `pyyaml==6.0.3` is a runtime dependency, and every committed lockfile passes `uv lock --check`.

### T003: Finalize falls back to the backlog

**File(s)**: `src/nmg_game_dev/finalize/mcp_tools.py`, `src/nmg_game_dev/finalize/service.py`, `src/nmg_game_dev/finalize/__main__.py`, `src/nmg_game_dev/pipeline/request.py`, `src/nmg_game_dev/pipeline/jobs.py`, `mcp-servers/finalize/src/finalize_mcp/server.py`, `mcp-servers/finalize/tools.json`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- With `category` and/or `asset_class` omitted, an asset entry matching the collection supplies them, and explicit values win (AC4, FR5).
- An unresolved argument returns `finalize.invalid_request` naming the argument and the backlog path checked.
- A succeeded `finalize_asset` job marks the entry `finalized`. A backlog write failure adds a `design.backlog_update_failed` warning without failing the job. `run_finalize_step` never marks.
- Cache settings hashes are unchanged for identical inputs. `scripts/validate-mcp-tools.py` passes.

### T004: Mission data asset class

**File(s)**: `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/Public/NmgMissionDefinition.h`, `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/Private/NmgMissionDefinition.cpp`
**Type**: Create
**Depends**: none
**Acceptance**:
- `UNmgMissionDefinition` is a `UPrimaryDataAsset` with `MissionName`, `Act`, `Region`, `DependsOn`, and `DesignDocPath`, and returns primary asset type `NmgMission` (FR6).
- The runtime module's dependency list is unchanged.

### T005: Scaffold command

**File(s)**: `src/nmg_game_dev/design/scaffold.py`, `src/nmg_game_dev/design/__main__.py`
**Type**: Create
**Depends**: T002, T004
**Acceptance**:
- `scaffold` generates per-type UE Python as designed, runs it through `UnrealMcpClient`, prints `created`/`unchanged`/`skipped`/`error` lines, marks `scaffolded`, writes the backlog once, and exits 0, 1, or 2 as specified (AC5, AC6, FR6, FR7).

### T006: Onboarding installs the design contract

**File(s)**: `src/nmg_game_dev/onboard/runner.py`, `src/nmg_game_dev/onboard/instructions.py`, `skills/onboard-consumer/references/install-steps.md`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- Onboarding copies the design contract with drift reporting, creates `docs/design/` without touching its contents, and the agent-instructions block links the design contract (AC7, FR8).
- `install-steps.md` lists the two new steps.

### T007: Skills and docs

**File(s)**: `skills/design/SKILL.md`, `skills/finalize-asset/SKILL.md`, `docs/skills/design.md`, `docs/mcp/finalize.md`, `docs/onboarding/index.md`, `CHANGELOG.md`
**Type**: Create
**Depends**: T002, T003, T005, T006
**Acceptance**:
- `skills/design/SKILL.md` follows the skill template (frontmatter `name: design`, `required_mcp: [unreal]` for scaffold, failure modes per `design.*` code) and tells the agent to run sync, then scaffold, and to relay the report lines (FR9).
- `finalize-asset` step 1 says that `category` and `asset_class` come from the design backlog when omitted. `docs/mcp/finalize.md` marks both optional. Onboarding docs introduce `docs/design/`.
- `CHANGELOG.md` `[Unreleased]` has an Added bullet that ends with `(#112)`.

### T008: Tests

**File(s)**: `tests/unit/design/test_parse.py`, `tests/unit/design/test_backlog.py`, `tests/unit/design/test_scaffold.py`, `tests/unit/design/test_cli.py`, `tests/unit/test_finalize_backlog.py`, `tests/unit/onboard/test_runner.py`, `tests/unit/onboard/test_instructions.py`, `tests/bdd/features/design.feature`, `tests/bdd/test_design_bdd.py`, `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/Tests/NmgMissionDefinition.spec.cpp`
**Type**: Create
**Depends**: T002, T003, T004, T005, T006
**Acceptance**:
- Unit tests prove AC1 (backlog shape, order, report lines), AC2 (status kept, fields updated, `planned` added, `orphaned` marked and restored to `planned`, byte-identical re-sync), and AC3 (each `design.*` code with file and field, backlog unchanged, `design.dir_missing`).
- They prove AC4 through `finalize/mcp_tools.py` and the CLI with a temp project: fallback, precedence, the unresolved error, `finalized` after a succeeded job using `tests/finalize_fakes.py`, the warning on write failure, and unchanged settings hashes.
- They prove AC5 and AC6 on the generated UE code and a fake `UnrealPythonClient`: paths, actor and class names, the existence check before any create, line statuses, exit codes, and a single backlog write.
- They prove AC7 in the onboarding tests: contract installed, unchanged, drift, and refreshed; `docs/design/` created and existing files untouched; block text.
- `NmgMissionDefinition.spec.cpp` asserts that the fields hold values and that `GetPrimaryAssetId()` has type `NmgMission`. It runs under `scripts/run-ue-tests.sh`.
- `tests/bdd/features/design.feature` (SCN001–SCN007) is bound in `tests/bdd/test_design_bdd.py`. `pytest tests/unit tests/bdd` passes.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #112 | 2026-10-31 | Initial feature tasks |
