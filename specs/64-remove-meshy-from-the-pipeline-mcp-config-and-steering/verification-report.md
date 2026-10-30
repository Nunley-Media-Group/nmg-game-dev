# Verification Report: Remove Meshy from the pipeline and MCP config

**Issue**: #64
**Date**: 2026-10-30
**Verification head**: 4e34ded258786ab357bca7ff5d33ffd81455b2e1

## Verification Report

### Implementation Status: Fail

### Executive Summary

The Meshy removal itself is complete: every approved acceptance criterion (AC1–AC5) has code and test evidence. The registered gate still fails. The delivery commit `4e34ded` bumped the project version from `0.5.0` to `0.6.0` in `VERSION`, `.claude-plugin/plugin.json`, `pyproject.toml`, the Blender manifest and the `.uplugin`. It did not update `tests/_scaffold_contract.py` (`EXPECTED_VERSION = "0.5.0"`) or `uv.lock`. As a result, 5 scaffold version-pin tests fail in `repository.tests`, and the required `plugin.session-smoke` provider was deferred, so its result is `incomplete`. This verify step can only write this report, so the fix goes back to implementation.

### Issue Scope

<!-- nmg-sdlc-issue-scope: {"issueNumber":64,"specPath":"specs/64-remove-meshy-from-the-pipeline-mcp-config-and-steering","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5"],"tasks":["T001","T002","T003","T004"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

- Active issue: #64
- Spec: `specs/64-remove-meshy-from-the-pipeline-mcp-config-and-steering`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5]; FR [FR1, FR2, FR3, FR4, FR5]
- Regression: scaffold contract (#1) version invariants — **regressed** (see Remaining Issues)

### Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/64.json` (head `4e34ded2…`, base `main`, run `04ec57bc-0b9e-4db7-a524-29804a801121`)
- Coverage: declared 5, recorded 5, complete `true`
- Ceiling: `Incomplete` (runner); overall is capped lower at **Fail** because a required result failed

| Validation | Provider | Required | Result | Evidence |
|---|---|---|---|---|
| `repository.tests` | builtin.command | yes | **failed** | `uv run pytest tests/unit tests/bdd -q` → 5 failed, 212 passed |
| `repository.lint` | builtin.command | yes | passed | `uv run ruff check .` exit 0 |
| `repository.types` | builtin.command | yes | passed | `uv run mypy src tests` exit 0 |
| `plugin.validate` | builtin.command | yes | passed | `claude plugin validate .` exit 0 |
| `plugin.session-smoke` | project.plugin-session-smoke | yes | **incomplete** | deferred until required local validations pass |

Failing tests (all are `assert '0.6.0' == '0.5.0'`):

- `tests/unit/test_scaffold_guards.py::test_plugin_json_schema`
- `tests/unit/test_scaffold_guards.py::test_version_file`
- `tests/unit/test_scaffold_guards.py::test_plugin_json_version`
- `tests/unit/test_scaffold_guards.py::test_pyproject_version`
- `tests/bdd/steps/test_scaffold.py::test_versioning_seeded`

### Delivery Validation

- Local verification: Not complete
- PR evidence: Not required

### Acceptance Criteria

- [x] AC1: Blender is the only pipeline source. `src/nmg_game_dev/pipeline/__init__.py` routes `source="blender"` through the full stage chain. Covered by `tests/unit/pipeline/test_run.py` and the `pipeline_blender_first.feature` BDD scenario (both pass).
- [x] AC2: The Meshy source is rejected. `pipeline/__init__.py:102` raises `PipelineError("pipeline.unsupported_source")` before any MCP call or cache write. Covered by `test_run.py::test_unsupported_source_rejected[meshy|other]` and `pipeline_unsupported_source.feature` (both pass).
- [x] AC3: The Meshy client types are gone. `Source = Literal["blender"]`, `_mcp.Server = Literal["blender", "unreal"]`, and `MeshyMcp`, `generate_meshy` and `McpClients.meshy` are removed. Covered by `tests/unit/pipeline/test_no_meshy.py`. `ruff check`, `ruff format --check` (71 files already formatted) and `mypy` all pass.
- [x] AC4: The MCP configuration has no Meshy server. The `meshy` entry is removed from `.mcp.json` and the `blender`/`unreal` entries are unchanged in the diff. `REQUIRED_SERVERS = ("blender", "unreal")`. Covered by `test_mcp_json_has_no_meshy` (passes).
- [x] AC5: Steering does not offer Meshy as a source. Covered by `test_steering_snippets_do_not_offer_meshy`, parametrized over the four banned strings (passes). The only remaining mention, `project-product.md:110`, is an explicit out-of-scope exclusion.

### Tasks

The tasks produced the expected changes: Meshy source and types are deleted, `.mcp.json` has no Meshy entry, `pipeline_meshy_supplement.feature` is deleted, the e2e tests have no Meshy references, and the new unsupported-source and no-Meshy guards exist.

### Architecture Review

| Area | Score (1-5) |
|------|-------------|
| SOLID Principles | 5 |
| Security | 5 |
| Performance | 5 |
| Testability | 4 |
| Error Handling | 5 |
| **Average** | **4.8** |

Findings:

- Testability: the scaffold version pin in `tests/_scaffold_contract.py` is not covered by the version-bump file mapping, so any bump breaks it. Reading `VERSION` instead of hardcoding the value would make the tests independent of the bump. This is not required for #64.
- Removing the Meshy source shrinks the attack surface: there is no third-party cloud credential (`MESHY_API_KEY`) left in the bundled MCP config.
- `.claude-plugin/plugin.json` was reformatted (multi-line `author` and `keywords`) as a side effect of the bump. It is cosmetic and `plugin validate` passes.

### Test Results

- Unit + BDD: 212 passed, 5 failed (version pins only; no Meshy-related failures)
- Lint/format/types: pass
- Smoke (`plugin.session-smoke`): not run (deferred)

### Fixes Applied

None. This step may only write `verification-report.md`, so `tests/_scaffold_contract.py` and `uv.lock` are outside what it can change. Each `uv run` call during the gate rewrote `uv.lock` (version `0.5.0` → `0.6.0`); the verifier restored it each time to keep the shared checkout clean.

### Remaining Issues

1. **Fail — version bump incomplete** (`4e34ded`): set `EXPECTED_VERSION = "0.6.0"` in `tests/_scaffold_contract.py`. Also update the BDD step text `` `VERSION` contains exactly `0.5.0` `` in `tests/bdd/steps/test_scaffold.py` and its matching scaffold `.feature` line.
2. **Fail — `uv.lock` stale**: regenerate `uv.lock` (`uv lock`) so the `nmg-game-dev` package version reads `0.6.0` and the tree stays clean after `uv run`.
3. After both fixes, rerun the full registered gate, including `plugin.session-smoke`.

### Recommendations

Route to implementation diagnosis. Fix the two version artifacts above, commit, and rerun `/sdlc-verify-code #64`.
