# Verification Report: Drive asset work and Unreal scaffolding from a consumer project's markdown design docs

**Date**: 2026-10-31
**Issue**: #112
**Reviewer**: Claude (nmg-sdlc verify worker)
**Scope**: Implementation verification against spec
**Verification head**: d8bd87f2813475bffa5c4a708faff60c8a81647e

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 5 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.8 |

### Implementation Status: Pass
**Total Issues**: 2 (both low severity, informational; none blocking)

All 7 acceptance criteria, 9 functional requirements, and 8 tasks are implemented. All 5 registered validations passed at the verification head, with complete coverage (declared 5, recorded 5).

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --issue 112 --base main --controller-run-id 1d8c53d8-6b3c-4e22-a1d5-e8a4c8a68d96`
- Artifact: `.nmg-sdlc/verification/112.json`. Head `d8bd87f2813475bffa5c4a708faff60c8a81647e`, tree clean
- Steering hash: `sha256:19b4c539f114f8bfc47feeb96b89b43e2aef05df7c7333b81a2f9c9b5972324b`
- Spec hash: `sha256:b752e6633bb1f965104df9ebe72b62931ee36645fa6b0825eed2175dc4a6ad0a`
- Ceiling: none
- Coverage: declared 5, recorded 5, complete true. Nothing missing, duplicated, or unknown

---

## Issue Scope

- Active issue: #112
- Spec: `specs/112-drive-asset-work-and-unreal-scaffolding-from-a-consumer-project-s-markdown-design-docs`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC7]; FR [FR1–FR9]; tasks [T001–T008]; scenarios [SCN001–SCN007]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":112,"specPath":"specs/112-drive-asset-work-and-unreal-scaffolding-from-a-consumer-project-s-markdown-design-docs","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Design docs parse into a sorted backlog | Pass | `src/nmg_game_dev/design/parse.py` `parse_tree`/`parse_file`. `backlog.py` `dump` (version 1, sorted by type then asset name, sorted keys). `__main__.py` `_sync` prints `<status> <type> <asset_name>: <source>`. Tests: `tests/unit/design/test_backlog.py`, `test_cli.py`, SCN001 |
| AC2 | Re-sync keeps status, updates fields, marks removed entries orphaned, restores returning ones | Pass | `backlog.merge` (keeps status, orphaned → planned on return, removed → orphaned). `dump` is byte-stable and `write_atomic` replaces via `os.replace`. Tests: `test_backlog.py`, SCN002 |
| AC3 | Invalid design files are reported and the backlog is kept | Pass | `parse.py` emits all 8 per-file and cross-file `design.*` codes. `DesignError.line()` prints the `error <code> <source>: <field> — <message>` format. `_sync` returns 1 before any write. `design.dir_missing` comes from `parse_tree`. Tests: `test_parse.py`, `test_cli.py`, SCN003 |
| AC4 | finalize resolves category and class from the backlog | Pass | `finalize/service.py` `resolve_backlog` (explicit values win) and `MissingArgumentError` (a `finalize.invalid_request` naming the argument and the backlog path). `pipeline/jobs.py` `_mark_backlog` marks only full `STEP_ORDER` runs, and a failed write returns a `design.backlog_update_failed` warning. `backlog_path` stays out of `settings_hash`. MCP server, `mcp_tools.py`, and CLI arguments are optional. Tests: `tests/unit/test_finalize_backlog.py`, SCN004 |
| AC5 | Regions, missions, and systems are scaffolded in Unreal | Pass | `design/scaffold.py`: level `/Game/Levels/<N>/L_<N>` with plane, PlayerStart, DirectionalLight, and SkyLight; `DA_<N>` of `NmgMissionDefinition` with all 5 fields; `BPC_<N>` with an ActorComponent parent. `created` lines and the `scaffolded` status. UE class in `NmgMissionDefinition.h/.cpp`. Tests: `test_scaffold.py`, SCN005 |
| AC6 | Scaffolding never overwrites existing work | Pass | Every generated body calls `does_asset_exist` before any create (an existing asset reports `unchanged` and is marked `scaffolded`). Orphaned entries report `skipped`. A per-item failure reports `error design.scaffold_failed` and the run continues with exit 1. `mcp.unreal.unreachable` is re-raised, then the command exits 2. The backlog is written once in `finally`. Tests: `test_scaffold.py`, `test_cli.py`, SCN006 |
| AC7 | Onboarding installs the design-doc contract | Pass | `onboard/runner.py`: `design_contract` through `sync_file` (installed, unchanged, drift, or refreshed) and `_design_dir` (creates the directory and never touches its contents). `instructions.py` block links the design contract. Tests: `tests/unit/onboard/test_runner.py`, `test_instructions.py`, SCN007 |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Design contract document | Complete | `docs/design-contract.md` lists all 10 `design.*` codes and the report formats |
| T002 | Parser, backlog, sync | Complete | `pyyaml` added. All four lockfiles updated |
| T003 | Finalize backlog fallback | Complete | `scripts/validate-mcp-tools.py` exits 0 |
| T004 | `UNmgMissionDefinition` | Complete | `UPrimaryDataAsset` with primary type `NmgMission`. Runtime `Build.cs` unchanged |
| T005 | Scaffold command | Complete | |
| T006 | Onboarding | Complete | `install-steps.md` lists `design_contract` and `design_dir` |
| T007 | Skills and docs | Complete | `skills/design/SKILL.md` follows the template. The finalize-asset, MCP, and onboarding docs are updated. The CHANGELOG bullet ends in `(#112)`. The version bump moved it from `[Unreleased]` to `[0.19.0]` |
| T008 | Tests | Complete | Unit, BDD (SCN001–SCN007), and `NmgMissionDefinition.spec.cpp` are present |

---

## Architecture Assessment

| Area | Score | Notes |
|------|-------|-------|
| SOLID | 5 | The `design` package keeps paths, model, parse, backlog, scaffold, and CLI in separate modules. Finalize depends only on `backlog.find_asset`/`mark`. Scaffold takes an injected `UnrealPythonClient` |
| Security | 5 | Frontmatter is read with `yaml.safe_load`. Values go into the generated UE Python only as `repr()` literals, and asset names are restricted to `^[A-Z][A-Za-z0-9]*$`, so design text cannot inject code. No secrets are involved |
| Performance | 5 | Parsing is linear in the file count. Each run makes one atomic backlog write. Scaffold makes one MCP call per item |
| Testability | 5 | The client, stdout, and stderr are injectable. The project root can be overridden. All tests run under pytest without UE or Blender |
| Error Handling | 4 | Structured codes and remediation text throughout. A partial write leaves the old backlog. Minor: an unreadable backlog during finalize counts as "no entry" (by design), so a corrupt backlog produces a missing-argument error instead of a parse error |

---

## Test Results

### Registered validations (`.nmg-sdlc/verification/112.json`)

| Validation | Provider | Required | Status | Evidence |
|------------|----------|----------|--------|----------|
| `repository.tests` | builtin.command | yes | passed | `uv run pytest tests/unit tests/bdd -q`, exit 0 |
| `repository.lint` | builtin.command | yes | passed | `uv run ruff check .`, exit 0 |
| `repository.types` | builtin.command | yes | passed | `uv run mypy src tests`, exit 0 |
| `plugin.validate` | builtin.command | yes | passed | `claude plugin validate .`, exit 0 |
| `plugin.session-smoke` | project.plugin-session-smoke | yes | passed | "plugin loaded via --plugin-dir; nmg-game-dev:blender connected" |

**Gate Summary**: 5/5 passed, 0 failed, 0 incomplete

### Supplementary checks (not registered)

- `scripts/validate-mcp-tools.py`: "MCP tools match tools.json for every server under mcp-servers/", exit 0.
- Feature subset (`tests/unit/design`, `tests/unit/test_finalize_backlog.py`, `tests/bdd/test_design_bdd.py`, `tests/unit/onboard`): 141 passed.

### Test coverage

- BDD scenarios: 7/7 ACs covered (SCN001–SCN007 in `tests/bdd/features/design.feature`, bound in `tests/bdd/test_design_bdd.py`).
- Step definitions: Implemented.
- Test execution: Pass.

### Exercise testing

No nmg-sdlc plugin files (`workflows/`, `agents/`) changed, so no exercise run is required. The nmg-game-dev plugin load was covered by the `plugin.session-smoke` validation.

---

## Fixes Applied

None. No findings needed a code change.

## Remaining Issues

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Low | test-evidence | `plugins/nmg-game-dev-ue-plugin/Source/NmgGameDevRuntime/Tests/NmgMissionDefinition.spec.cpp` | The UE Automation spec was not run in this verification. `scripts/run-ue-tests.sh` is not a registered validation in `steering/manifest.json` | Outside the registered gate. A live run of the UE editor and build is needed. Not blocking |
| Low | error-handling | `src/nmg_game_dev/finalize/service.py` `resolve_backlog` | A malformed `backlog.json` is treated as no match, so the caller sees `finalize.invalid_request` (missing argument) and not a backlog parse error | Matches the documented behavior ("An unreadable backlog counts as no match"). The message names the backlog path |

## Recommendation

Ready for PR.
