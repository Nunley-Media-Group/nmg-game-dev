# Verification Report: Upgrade toolchain to UE 5.8 with native MCP plus VibeUE, and Blender 5.2 MCP

**Issue**: #68
**Date**: 2026-10-30
**Verification head**: 125a3ba905a983dda0fe429e285dd2e312ed69da

## Verification Report

### Implementation Status: Fail

### Executive Summary

The feature implementation (commit `e0bb2e9`) satisfies AC1–AC7 on inspection, and lint, types, and
`claude plugin validate` pass. The registered `repository.tests` gate fails: the delivery commit
`125a3ba` bumped the project version from 0.6.0 to 0.7.0 (`VERSION`, `.claude-plugin/plugin.json`,
`pyproject.toml`, `blender_manifest.toml`, `nmg-game-dev.uplugin`) but left
`tests/_scaffold_contract.py` `EXPECTED_VERSION = "0.6.0"` and did not refresh `uv.lock`. Five
version-guard tests fail, and `uv run` rewrites `uv.lock`, which dirties the tree. The required
`plugin.session-smoke` provider was deferred, so it never ran. Overall status is **Fail**, routed back to implementation.

### Issue Scope

- Active issue: #68
- Spec: `specs/68-upgrade-toolchain-to-ue-5-8-with-native-mcp-plus-vibeue-and-blender-5-2-mcp`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC7]; FR [FR1–FR8]; tasks [T001–T008]; scenarios [SCN001–SCN007]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":68,"specPath":"specs/68-upgrade-toolchain-to-ue-5-8-with-native-mcp-plus-vibeue-and-blender-5-2-mcp","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

### Delivery Validation

- Local verification: Not complete (`repository.tests` failed; `plugin.session-smoke` deferred)
- PR evidence: Not required

### Deterministic Steering Artifact

- Runner: `sdlc-verify-steering.mjs --base main --controller-run-id 04ec57bc-0b9e-4db7-a524-29804a801121`
- Artifact: `.nmg-sdlc/verification/68.json`, headSha `125a3ba905a983dda0fe429e285dd2e312ed69da`
- Coverage: declared 5, recorded 5, complete `true`
- Ceiling: **Incomplete**; the failed required `repository.tests` lowers the overall status to **Fail**

| Validation | Required | Status | Evidence |
|------------|----------|--------|----------|
| `repository.tests` | yes | **failed** | `uv run pytest tests/unit tests/bdd -q` exited 1: 5 failed (version guards expect 0.6.0, files say 0.7.0) |
| `repository.lint` | yes | passed | `ruff check .`: All checks passed |
| `repository.types` | yes | passed | `mypy src tests`: no issues in 53 files |
| `plugin.validate` | yes | passed | `claude plugin validate .` exited 0 (warnings only: root CLAUDE.md, LICENSE missing for directory submission) |
| `plugin.session-smoke` | yes | incomplete | deferred until required local validations pass |

### Acceptance Criteria

- [x] AC1: Unreal 5.8 everywhere: `fixtures/dogfood.uproject` `EngineAssociation` 5.8; uplugin `EngineVersion` 5.8.0; `start-unreal-mcp.sh` and `run-ue-tests.sh` default `UE_ROOT` to `/Users/Shared/Epic Games/UE_5.8`. `git grep` finds no `UE_5.7`, `5.7.0`, or `Unreal Engine 5.7` outside `specs/` and `CHANGELOG.md`, apart from the guard's own constant in `tests/unit/test_toolchain_guards.py:45`
- [x] AC2: Native MCP plus VibeUE: the launcher passes `-ModelContextProtocolStartServer -ModelContextProtocolPort=${PORT}` (default 8000) and keeps the idempotent LISTEN exit 0. The uproject enables `ModelContextProtocol`, `EditorToolset`, `VibeUE`, and `nmg-game-dev`. The INI sets `bAutoStartServer=True` and `ServerPortNumber=8000`. `fixtures/Source/**` and `fixtures/Config/**` are tracked, and `fixtures/Plugins/` is ignored. Live editor launch not exercised (smoke deferred)
- [x] AC3: `.mcp.json` `unreal` is `{"type":"http","url":"http://127.0.0.1:${UE_MCP_PORT:-8000}/mcp"}` and its description names Epic's Unreal MCP plus VibeUE. The file has no `mcp-remote`, `8088`, or bridge wording, and guards are in `tests/unit/test_scaffold_guards.py`
- [x] AC4: `scripts/smoke-unreal-mcp.py` implements the init → toolsets → `execute_python_code` → FBX import → delete flow with exit codes 0/1/2. Its stub-server tests are in `tests/unit/test_smoke_unreal_mcp.py`. The live run on the reference machine is not verified here
- [x] AC5: `.mcp.json` `blender` runs `uvx mcp-for-blender@latest` with `BLENDER_MCP_DISABLE_TELEMETRY=1` and no `--with` or `mcp<2`. `start-blender-mcp.sh` lists `blender_mcp` first. `scripts/smoke-blender-mcp.py` has stub tests in `tests/unit/test_smoke_blender_mcp.py`
- [x] AC6: No version constraints in the `blender` or `unreal` entries. `install-vibeue.sh` uses a depth-1 default-branch clone or a `pull --ff-only`. `install-blender-mcp-addon.sh` runs `uvx mcp-for-blender@latest install-addon`. Guards are in `tests/unit/test_toolchain_guards.py`
- [x] AC7: `docs/mcp/unreal.md` and `docs/mcp/blender.md` cover the ports, overrides, install and smoke scripts, and the latest-version policy. The steering tech snippet names UE 5.8, port 8000, and the latest-release trust rule, with no 8088. The README no longer lists Node.js

### Regression Obligations

None declared.

### Tasks

T001–T008: every listed file exists in the diff against `main`. The T007/T008 tests run, but the version guards in `tests/_scaffold_contract.py` and `uv.lock` were not updated for the 0.7.0 bump in the delivery commit `125a3ba`.

### Architecture Review

| Area | Score (1-5) |
|------|-------------|
| SOLID Principles | 4 |
| Security | 4 |
| Performance | 5 |
| Testability | 4 |
| Error Handling | 4 |

**Average**: 4.2

Findings:

- Each script has one job: launch, install, or smoke. The smoke scripts use only the standard library and have typed exit-code constants.
- Third-party components are intentionally unpinned, as the spec requires. The smoke scripts are the trust control, and that control has not run live in this verification.
- The version is duplicated in five manifests plus a hard-coded test constant. Nothing derives `EXPECTED_VERSION` from `VERSION`, and that is the cause of this failure.

### Test Coverage

- BDD scenarios: 7/7 acceptance criteria are mapped (SCN001–SCN007 in `feature.gherkin`, plus guard and unit tests)
- Step definitions: Implemented
- Test execution: **Fail**. Five tests fail: `test_plugin_json_schema`, `test_version_file`, `test_plugin_json_version`, `test_pyproject_version`, and `tests/bdd/steps/test_scaffold.py::test_versioning_seeded`

### Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Fail | 5 version-guard failures (`assert '0.7.0' == '0.6.0'`) |
| `repository.lint` | Pass | ruff clean |
| `repository.types` | Pass | mypy clean |
| `plugin.validate` | Pass | exit 0 |
| `plugin.session-smoke` | Incomplete | deferred until required local validations pass |

**Gate Summary**: 3/5 passed, 1 failed, 1 incomplete

### Fixes Applied

| Severity | Category | Location | Issue | Fix | Routing |
|----------|----------|----------|-------|-----|---------|
| — | — | — | None. Verify publication scope only allows writing this report | — | — |

The verifier restored `uv.lock` after `uv run` rewrote it, so the shared checkout stays clean. No source changes were made.

### Remaining Issues

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| High | correctness | `tests/_scaffold_contract.py:9` | `EXPECTED_VERSION = "0.6.0"` but `VERSION` and the manifests are `0.7.0` after `125a3ba`. Five guard tests fail | Outside verify write scope; route to implementation: set `EXPECTED_VERSION = "0.7.0"` (or derive it from `VERSION`) |
| Medium | correctness | `uv.lock` | Lockfile still records `nmg-game-dev` version `0.6.0`. `uv run` rewrites it to `0.7.0` and dirties the tree | Outside verify write scope; route to implementation: commit the regenerated `uv.lock` |
| Medium | verification | `plugin.session-smoke` | Required smoke never ran (deferred) | Re-run the full gate after the fixes above |

### Recommendation

Needs fixes. Update the version guard constant and `uv.lock` for 0.7.0, then rerun the full registered gate, including `plugin.session-smoke`.
