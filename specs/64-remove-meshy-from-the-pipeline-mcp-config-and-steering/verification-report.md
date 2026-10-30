# Verification Report: Remove Meshy from the pipeline and MCP config

**Date**: 2026-10-30
**Issue**: #64
**Reviewer**: Claude (nmg-sdlc verify worker)
**Scope**: Implementation verification against spec

**Verification head**: b2d78e5c9289a14592701780e81cee7283d0f3a0

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 5 |
| Testability | 5 |
| Error Handling | 5 |
| **Overall** | 5.0 |

### Implementation Status: Pass

**Total Issues**: 0 blocking, 1 low-priority observation

The earlier Fail at `4e34ded` was caused by a version-pin mismatch: `tests/_scaffold_contract.py` and `uv.lock` still said `0.5.0` after the bump to `0.6.0`. Commit `b2d78e5` fixed it. At `b2d78e5`, all five manifest-registered validations pass with complete coverage (`declared: 5`, `recorded: 5`, `complete: true`, no ceiling). That includes the real `plugin.session-smoke` run, in which the plugin loaded through `--plugin-dir` and `nmg-game-dev:blender` connected. All five approved acceptance criteria have code and test evidence.

---

## Issue Scope

- Active issue: #64
- Spec: `specs/64-remove-meshy-from-the-pipeline-mcp-config-and-steering`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5]; FR [FR1, FR2, FR3, FR4, FR5]; tasks [T001, T002, T003, T004]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":64,"specPath":"specs/64-remove-meshy-from-the-pipeline-mcp-config-and-steering","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5"],"tasks":["T001","T002","T003","T004"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 64 --spec specs/64-… --base main --controller-run-id 04ec57bc-0b9e-4db7-a524-29804a801121`, which returned `ok: true` and `ceiling: null`
- Artifact: `.nmg-sdlc/verification/64.json`
  - Identity: head `b2d78e5c9289a14592701780e81cee7283d0f3a0`, clean tree
  - Steering hash: `sha256:613e000a…e1e1`
  - Spec hash: `sha256:19fc13b2…3c2c`
- Coverage: declared 5, recorded 5, complete, with no missing, duplicate or unknown results

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Blender is the only pipeline source | Pass | `src/nmg_game_dev/pipeline/__init__.py`: the `generate` stage defaults to `generate_blender`. `pipeline_blender_first.feature` and the unit `test_run.py` Blender run pass. |
| AC2 | Meshy and every other non-Blender source is rejected | Pass | `run()` raises `PipelineError("pipeline.unsupported_source", stage="pipeline")` first, before the `mcp_clients` check, any MCP call or any cache write. The remediation names `source="blender"`. Covered by `tests/unit/pipeline/test_run.py::TestRunUnsupportedSource` (meshy, other) and `pipeline_unsupported_source.feature` (meshy, other). Both assert zero fake calls and an empty cache. |
| AC3 | Meshy client types are gone | Pass | `MeshyMcp`, `McpClients.meshy` and `generate_meshy` are deleted. `Server` is now `Literal["blender","unreal"]` and `Source` is now `Literal["blender"]`. `tests/unit/pipeline/test_no_meshy.py` covers this. `ruff check .`, `ruff format --check .` and `mypy src tests` pass. |
| AC4 | The MCP configuration has no Meshy server | Pass | The `meshy` entry is removed from `.mcp.json`; the `blender` and `unreal` entries have no diff. `REQUIRED_SERVERS == ("blender", "unreal")`. `test_mcp_json_has_no_meshy` covers this, and the AC8 scaffold step names two servers. |
| AC5 | Steering does not offer Meshy as a source | Pass | `test_steering_snippets_do_not_offer_meshy` scans each `steering/snippets/*.md` for the four banned strings. `test_steering_snippets_found` guards against scanning zero files. The only remaining mention, `project-product.md:110`, is an out-of-scope statement ("including Meshy") and contains no banned string. |

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Remove the Meshy route and client types | Complete | 4 source files modified, with docstrings updated |
| T002 | Remove the Meshy MCP server and update the scaffold contract | Complete | `.mcp.json`, the contract, guards, the scaffold feature and steps |
| T003 | Remove Meshy fakes and tests; add unsupported-source and type coverage | Complete | The Meshy feature and e2e test are deleted. A case-insensitive scan of `src/`, `tests/` and `.mcp.json` finds `meshy` only in the guard literals and the unsupported-source inputs. |
| T004 | Changelog | Complete | The bullet ends with `(#64)`. It sits under `## [0.6.0] - 2026-10-30` because the version bump promoted `[Unreleased]`. |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Source validation stays in the orchestrator, and the `generate` stage keeps a single responsibility |
| Open/Closed | 5 | `_SUPPORTED_SOURCES` is the single extension point, and `stage_overrides` is preserved |
| Liskov Substitution | 5 | `generate_blender` still satisfies the `Stage` Protocol |
| Interface Segregation | 5 | `McpClients` shrinks to the two clients that are actually used |
| Dependency Inversion | 5 | Stages still depend on the `BlenderMcp`/`UnrealMcp` Protocols |

### Layer Separation

The changes stay inside the pipeline layer (`src/nmg_game_dev/pipeline/`) and its tests. No skill, MCP server or UE code was touched.

### Dependency Flow

`generate.py` no longer imports `PipelineError`. No new dependencies were added.

---

## Security Assessment

- [x] Authentication: the credential surface shrinks because `MESHY_API_KEY` is gone from `.mcp.json` and the remediation text
- [x] Authorization: N/A
- [x] Input validation: `source` is checked against an allowlist before any side effect
- [x] Injection prevention: N/A; the error message uses `!r` formatting only
- [x] Data protection: one fewer third-party MCP server (`npx meshy-mcp-server`) in the supply chain

## Performance Assessment

- [x] Async patterns: N/A
- [x] Caching: a rejected source never touches the cache (asserted)
- [x] Resource management: the run fails fast before any MCP or cache work
- [x] Query optimization: N/A

## Testability and Error Handling

Unsupported-source rejection uses the structured `PipelineError` contract (`code`, `message`, `remediation`, `stage`). The tests assert the no-side-effect guarantee directly through fake call counts and the cache directory contents.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (`pipeline_blender_first.feature`) | Yes | Yes |
| AC2 | Yes (`pipeline_unsupported_source.feature`) | Yes | Yes |
| AC3 | Yes (`test_no_meshy.py` and typing gates) | Yes | Yes |
| AC4 | Yes (scaffold AC8 scenario and `test_mcp_json_has_no_meshy`) | Yes | Yes |
| AC5 | Yes (`test_steering_snippets_do_not_offer_meshy`) | Yes | Yes |

### Coverage Summary

- `uv run pytest tests/unit tests/bdd -q`: 217 passed
- `uv run mypy src tests`: no issues in 50 source files
- `uv run ruff check .`: all checks passed
- `ruff format --check .`: 71 files already formatted

---

## Exercise Test Results

Not applicable as an nmg-sdlc exercise: the diff touches no `workflows/` or `agents/` paths. The registered real-session smoke (`plugin.session-smoke`) covers the consumer-facing plugin change instead (see below).

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q` exited 0: 217 passed |
| `repository.lint` | Pass | `uv run ruff check .` exited 0: "All checks passed!" |
| `repository.types` | Pass | `uv run mypy src tests` exited 0: "Success: no issues found in 50 source files" |
| `plugin.validate` | Pass | `claude plugin validate .` exited 0 |
| `plugin.session-smoke` | Pass | Real session in an ephemeral git project through herdr. The plugin loaded via `--plugin-dir`, and the `/mcp` screen showed `nmg-game-dev:blender` connected. The tab closed afterwards. |

**Gate Summary**: 5/5 gates passed, 0 failed, 0 incomplete

### Real Smoke Lifecycle Evidence

1. `git init` an ephemeral test project
2. `herdr tab create`, then trust the project
3. `herdr agent start … -- --plugin-dir <repo>`
4. `herdr agent prompt /mcp`, then capture the `/mcp` screen showing `nmg-game-dev:blender` connected
5. `herdr tab close`

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| High | Testing | `tests/_scaffold_contract.py`, `uv.lock` | The version pins still said `0.5.0` after the `0.6.0` bump, so 5 scaffold tests failed at `4e34ded` | Implementation commit `b2d78e5` aligned the pins. Verified here with fresh, complete results. | `direct` (implementation stage) |

This verification pass made no further fixes.

## Remaining Issues

### Critical Issues

None.

### High Priority

None.

### Medium Priority

None.

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Architecture |
| **Location** | `.claude-plugin/plugin.json` |
| **Issue** | The `author` and `keywords` fields were reflowed to multi-line JSON as part of the version bump. This changes formatting only. |
| **Impact** | None functionally. `plugin.validate` and the smoke run pass. |
| **Reason Not Fixed** | Outside #64's scope, and harmless |

---

## Positive Observations

- The rejection runs first in `run()`, so a bad source cannot cause partial work.
- The guard tests protect against an empty glob (`test_steering_snippets_found`).
- The `.mcp.json` diff is a pure deletion: the `blender` and `unreal` entries are unchanged byte for byte.

## Recommendations Summary

### Before PR (Must)

- None

### Short Term (Should)

- None

### Long Term (Could)

- Remove the `generate` stage as part of #69, as already planned

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `src/nmg_game_dev/pipeline/__init__.py` | 0 | Source allowlist and rejection |
| `src/nmg_game_dev/pipeline/stages/_base.py` | 0 | `MeshyMcp` and `McpClients.meshy` removed |
| `src/nmg_game_dev/pipeline/stages/_mcp.py` | 0 | `Server` literal narrowed |
| `src/nmg_game_dev/pipeline/stages/generate.py` | 0 | `generate_meshy` removed |
| `.mcp.json` | 0 | `meshy` entry removed |
| `tests/unit/test_scaffold_guards.py` | 0 | AC4 and AC5 guards |
| `tests/unit/pipeline/test_no_meshy.py` | 0 | AC3 |
| `tests/unit/pipeline/test_run.py` | 0 | AC2 |
| `tests/bdd/features/pipeline_unsupported_source.feature`, `tests/bdd/test_pipeline_bdd.py` | 0 | AC2 BDD |
| `.claude-plugin/plugin.json` | 1 (low) | Formatting reflow |

---

## Recommendation

**Ready for PR**

Every delivery AC, FR, task and scenario has passing evidence at `b2d78e5`, and every registered validation, including the real session smoke, passed with complete coverage.
