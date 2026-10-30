# Verification Report: Reshape the pipeline to finalize an authored asset instead of generating from a prompt

**Date**: 2026-10-30
**Issue**: #69
**Reviewer**: Claude Code (nmg-sdlc verify worker)
**Scope**: Implementation verification against spec

**Verification head**: 66c379b28bb31fe2a90256b2e73dec1b46cb8ba9

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 4 |
| Security | 4 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.3 |

### Implementation Status: Pass

**Total Issues**: 2 (both outside this issue's scope, see Remaining Issues)

All five registered steering validations passed at the verification head, and coverage is complete (5 declared, 5 recorded). All seven acceptance criteria and nine tasks have code and test evidence.

---

## Issue Scope

- Active issue: #69
- Spec: `specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC7]; FR [FR1–FR8]; tasks [T001–T009]; scenarios [SCN001–SCN007]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":69,"specPath":"specs/69-reshape-the-pipeline-to-finalize-an-authored-asset-instead-of-generating-from-a-prompt","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008","T009"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact

- Runner: `sdlc-verify-steering.mjs --issue 69 --base main --controller-run-id 40468ffe-0554-4b4f-b7a9-4cdbd44bd3ba`
- Artifact: `.nmg-sdlc/verification/69.json`
- Identity: head `66c379b28bb31fe2a90256b2e73dec1b46cb8ba9`, tree clean, steering `sha256:c53014e6…`, spec `sha256:9f70889a…`
- Ceiling: none
- Coverage: declared 5, recorded 5, complete `true`, no missing, duplicate, or unknown results

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Finalize starts from an authored asset; six steps in order; no Prompt/generate/source/Meshy | Pass | `src/nmg_game_dev/pipeline/steps.py:27` (`STEP_ORDER`), `pipeline/__init__.py:60` (`finalize`); `pipeline/prompt.py` and `pipeline/stages/` removed; `tests/unit/pipeline/test_no_meshy.py`, `tests/unit/pipeline/test_engine.py` |
| AC2 | Background Blender against a checkpoint; progress polling; load-back with the session-changed guard; `finalize.job_crashed` | Pass | `pipeline/engine.py` (`_checkpoint`, `_load_back`, `FinalizeSessionChangedError`), `pipeline/jobs.py:89-105` (crash detection), `pipeline/blender_proc.py`, `finalize_core/load_back.py`; `tests/unit/pipeline/test_jobs.py`, `tests/blender/test_finalize_core.py` (passes in headless Blender 5.2) |
| AC3 | Each step is an agent tool with the same implementation; job id or result within `wait_seconds` ≤ 150 | Pass | `pipeline/__init__.py:113` (`run_step`), `finalize/service.py:20,116` (`MAX_WAIT_SECONDS`, `clamp_wait`), `finalize/mcp_tools.py`, `mcp-servers/finalize/src/finalize_mcp/server.py`; a stdio MCP `initialize` + `tools/list` from this checkout lists all three tools; `tests/unit/test_finalize_cli.py`, `tests/unit/test_finalize_mcp.py` |
| AC4 | Content-addressed cache; changes miss from the first affected step; `--force` reruns everything | Pass | `pipeline/cache.py` (per-step keys + alias index), `pipeline/engine.py` (`chain_input`, alias mode, `force`), `finalize_core/hashing.py`; `tests/unit/pipeline/test_cache.py`, `test_engine.py` |
| AC5 | UE import lands Desktop/Mobile, sets texture flags, creates `MI_<Name>_<Part>` of `M_NmgORM`, keeps part pivots within 0.01 cm | Pass | `src/nmg_game_dev/unreal/import_asset.py:59-61,124-134,203-228,304`; `plugins/nmg-game-dev-ue-plugin/Content/Materials/M_NmgORM.uasset`; `scripts/unreal/build_master_material.py`; `tests/unit/test_unreal_import.py`, `tests/unit/test_unreal_mcp_client.py` |
| AC6 | Failures stop the run with a `PipelineError` (code, message, remediation, stage); no UE import unless earlier steps passed | Pass | `pipeline/errors.py`, `pipeline/steps.py:150-215`, `pipeline/engine.py:273`; BDD scenario SCN006 in `tests/bdd/features/finalize.feature` |
| AC7 | Steering describes freeform authoring plus finalize; no superseded terms; tech snippet names the job runner, MCP tools, and CLI | Pass | `steering/snippets/project-{product,tech,structure}.md`; `tests/unit/test_steering_guards.py:16` |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Request, results, cache keys, and alias index | Complete | `request.py`, `result.py`, `cache.py` |
| T002 | Blender-side finalize core and entry script | Complete | `finalize_core/{hashing,steps,load_back}.py`, `scripts/blender/finalize_entry.py` |
| T003 | Clients, Blender process runner, and job runner | Complete | `clients/blender_session.py`, `clients/unreal_mcp.py`, `blender_proc.py`, `jobs.py` |
| T004 | Steps and finalize orchestration | Complete | `steps.py`, `engine.py`, `errors.py`; `prompt.py` and `stages/` removed |
| T005 | UE import and master material | Complete | `unreal/import_asset.py`, `build_master_material.py`, `M_NmgORM.uasset` |
| T006 | CLI, MCP server, skill, and `.mcp.json` | Complete | `finalize/__main__.py`, `mcp-servers/finalize/`, `skills/finalize-asset/SKILL.md`, `.mcp.json` entry |
| T007 | Steering, docs, and changelog | Complete | steering snippets, `docs/mcp/finalize.md`, `CHANGELOG.md` |
| T008 | Host-side unit and BDD tests | Complete | 368 unit + BDD tests pass |
| T009 | Blender headless and live end-to-end tests | Complete | `tests/blender/test_finalize_core.py` and `test_finalize_fixes.py` pass; `tests/e2e/test_finalize_e2e.py` present (live, `--runslow`; not run here) |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 4 | Clean split: request, cache, steps, engine, jobs, clients, and UE import. `engine.py` (410 lines) and `unreal/import_asset.py` (501 lines) are the largest units but stay cohesive. |
| Open/Closed | 4 | Steps are registered in the `STEPS` table, so a new step needs no change to the orchestrator loop. |
| Liskov Substitution | 5 | Fake clients and runners (`tests/finalize_fakes.py`) substitute for the real ones throughout the tests. |
| Interface Segregation | 4 | Narrow client protocols for the Blender session and the Unreal MCP. |
| Dependency Inversion | 4 | The engine takes `FinalizeClients` and a `StepRunner` by injection; the CLI and MCP server wrap the same `nmg_game_dev.finalize` service. |

### Layer Separation

Matches `project-structure.md`. The skill calls the finalize MCP tools or the CLI and never opens sockets. The finalize MCP server adds no logic over `nmg_game_dev.finalize`. Blender-side code lives in `finalize_core/` and runs only in headless Blender or through the session client.

### Dependency Flow

Skill → finalize service → pipeline engine → step runner and clients → Blender and Unreal. Nothing in the pipeline imports from the MCP server or the skill.

---

## Security Assessment

- [x] Authentication: no new credentials. The MCP endpoints are localhost (Blender socket, `127.0.0.1` Unreal MCP).
- [x] Authorization: not applicable (local tooling).
- [x] Input validation: `FinalizeRequest` is a pydantic model; unknown step names are rejected with a `PipelineError`.
- [x] Injection prevention: Python sent to Unreal through `execute_python_code` is built from a fixed template with JSON-encoded parameters.
- [x] Data protection: job and cache files stay under the cache root (`NMG_GAME_DEV_CACHE_DIR`).

## Performance Assessment

- [x] Async patterns: long Blender work runs in a detached job with `blender --background`, never inside a single MCP call (the MCP call limit is 180 s; tool waits are capped at 150 s).
- [x] Caching: per-step content-addressed keys plus an alias index for results that were already finalized and loaded back.
- [x] Resource management: a job lock stops two finalize jobs from running at once; a crashed job releases the lock when its status is read.
- [ ] Query optimization: not applicable.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes | Yes |
| AC5 | Yes (SCN005) | Yes | Yes |
| AC6 | Yes (SCN006) | Yes | Yes |
| AC7 | Yes (SCN007) | Yes | Yes |

### Coverage Summary

- Feature files: `tests/bdd/features/finalize.feature` (7 scenarios); `specs/69-…/feature.gherkin`
- Step definitions: implemented (`tests/bdd/test_finalize_bdd.py`)
- Unit + BDD: 368 passed (`uv run pytest tests/unit tests/bdd -q`)
- Blender headless: 95 passed, 2 failed. Both failures are in `test_coexistence.py` and fail the same way on `main` (see Remaining Issues). All finalize tests pass.
- Live e2e: `tests/e2e/test_finalize_e2e.py` requires a running Blender and UE 5.8 with `--runslow`. It was not run.

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Skill Exercised** | `finalize` MCP server (bundled through `.mcp.json`) |
| **Exercise Method** | stdio `initialize` + `tools/list` against `uv run --project mcp-servers/finalize finalize-mcp` from this checkout; registered `plugin.session-smoke` loads the plugin with `--plugin-dir` |
| **Result** | Server initializes and lists `finalize_asset`, `run_finalize_step`, and `get_finalize_job` with the documented schemas; session smoke: "plugin loaded via --plugin-dir; nmg-game-dev:blender connected" |

### Notes

In this Claude Code session the `finalize` server reported "Connection closed". This session loads the installed marketplace plugin (0.10.0) from the cache, and that version has no `mcp-servers/finalize`. The server starts from this checkout, so this is not a defect in the branch. It will resolve once the release containing #69 is installed.

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` (registered) | Pass | `uv run pytest tests/unit tests/bdd -q`: command exited 0 |
| `repository.lint` (registered) | Pass | `uv run ruff check .`: command exited 0 |
| `repository.types` (registered) | Pass | `uv run mypy src tests`: command exited 0 |
| `plugin.validate` (registered) | Pass | `claude plugin validate .`: command exited 0 |
| `plugin.session-smoke` (registered) | Pass | plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |
| `gate-python-lint` (format half) | Pass | `ruff format --check .`: 146 files already formatted |
| `gate-blender-headless` (advisory, unregistered) | Pass for this change | 95 passed; the 2 `test_coexistence.py` failures reproduce on `main` |
| `gate-skill-schema` / `gate-mcp-schema` (advisory, unregistered) | Not runnable | `scripts/validate-skills.py` and `scripts/validate-mcp-tools.py` don't exist in the repository (pre-existing) |
| `gate-markdown-lint` (advisory, unregistered) | Not runnable | `markdownlint` is not installed on this host |

**Gate Summary**: 5/5 registered validations passed, 0 failed, 0 incomplete.

---

## Fixes Applied

None. No defects attributable to #69 were found.

## Remaining Issues

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `tests/blender/test_coexistence.py:52,106` |
| **Issue** | `test_both_addons_load` and `test_disabling_nmg_leaves_host_functional` fail. On this host the Blender MCP host add-on is installed both as the `blender_mcp` module and as the single-file `blender-mcp-addon.py` (log: "has been registered before"), so `addon_utils.check("blender_mcp")` reports it unloaded. |
| **Impact** | The unregistered advisory Blender suite isn't fully green on this machine. |
| **Reason Not Fixed** | Pre-existing: the same two tests fail on `main`; #69 doesn't touch these files; it's out of scope. |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `steering/snippets/project-tech.md` (Verification Gates) |
| **Issue** | `gate-skill-schema` and `gate-mcp-schema` name scripts that don't exist in the repository. |
| **Impact** | Advisory only; the registered manifest validations don't depend on them. |
| **Reason Not Fixed** | Pre-existing; out of scope for #69. |

---

## Positive Observations

- The design handles a load-back refusal explicitly: export, reimport, and `import_ue` still run from the job's files, and the run reports `finalize.session_changed` with the result `.blend` (design § load-back, "Ordering").
- The CLI and the MCP server share one service, and the MCP server holds no logic of its own.
- Fakes in `tests/finalize_fakes.py` let the whole orchestrator, including crash and session-changed paths, run without Blender or Unreal.

## Recommendations Summary

### Before PR (Must)

- None.

### Short Term (Should)

- Run `tests/e2e/test_finalize_e2e.py --runslow` against live Blender 5.2 and UE 5.8 before the first consumer uses finalize.

### Long Term (Could)

- Make `test_coexistence.py` handle a host add-on installed under more than one module name.
- Add the `validate-skills.py` / `validate-mcp-tools.py` scripts or remove those gates from tech steering.

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `src/nmg_game_dev/pipeline/engine.py` | 0 | Orchestration, load-back, alias cache |
| `src/nmg_game_dev/pipeline/jobs.py` | 0 | Detached job runner, lock, crash detection |
| `src/nmg_game_dev/pipeline/steps.py` | 0 | Step table and gates |
| `src/nmg_game_dev/finalize/{service,mcp_tools,__main__}.py` | 0 | Shared CLI/MCP implementation |
| `mcp-servers/finalize/` | 0 | FastMCP wrapper, verified over stdio |
| `src/nmg_game_dev/unreal/import_asset.py` | 0 | Texture settings, MI creation, pivot check |
| `steering/snippets/*.md` | 0 | AC7 guard test passes |

---

## Recommendation

**Ready for PR**

Every acceptance criterion and task has implementation and test evidence, and all registered validations passed at `66c379b28bb31fe2a90256b2e73dec1b46cb8ba9`. The remaining items predate this branch and fall outside #69's scope.
