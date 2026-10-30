# Verification Report: Upgrade toolchain to UE 5.8 with native MCP plus VibeUE, and Blender 5.2 MCP

**Issue**: #68
**Date**: 2026-10-30
**Verification head**: b545288f16006d740e5ce6cfd8c7364efcdfa009

## Verification Report

### Implementation Status: Pass

### Executive Summary

All seven acceptance criteria are met at `b545288`. The previous verification failed because of stale
version guards. That cause is fixed: `f7696ce` and `b545288` derive the guard version from `VERSION`
and refresh `uv.lock`. All five registered validations passed at the exact head with complete
coverage, including the required `plugin.session-smoke`. The live smoke scripts also passed on the
reference machine. `scripts/smoke-blender-mcp.py` ran against Blender 5.2.3 LTS.
`scripts/smoke-unreal-mcp.py` ran against UE 5.8.4 on the dogfood fixture after
`scripts/start-unreal-mcp.sh` launched it, and it imported and removed `/Game/__NmgSmoke/SM_SmokeCube`
through VibeUE on Epic's native endpoint. One low-severity hygiene finding remains and does not
block delivery.

### Issue Scope

- Active issue: #68
- Spec: `specs/68-upgrade-toolchain-to-ue-5-8-with-native-mcp-plus-vibeue-and-blender-5-2-mcp`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC7]; FR [FR1–FR8]; tasks [T001–T008]; scenarios [SCN001–SCN007]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":68,"specPath":"specs/68-upgrade-toolchain-to-ue-5-8-with-native-mcp-plus-vibeue-and-blender-5-2-mcp","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

### Delivery Validation

- Local verification: Pass
- PR evidence: Not required

### Deterministic Steering Artifact

- Runner: `sdlc-verify-steering.mjs --base main --controller-run-id 04ec57bc-0b9e-4db7-a524-29804a801121`
- Artifact: `.nmg-sdlc/verification/68.json`, headSha `b545288f16006d740e5ce6cfd8c7364efcdfa009`, treeState clean
- Coverage: declared 5, recorded 5, complete `true`
- Ceiling: none

| Validation | Required | Status | Evidence |
|------------|----------|--------|----------|
| `repository.tests` | yes | passed | `uv run pytest tests/unit tests/bdd -q`: 253 passed in 4.06s |
| `repository.lint` | yes | passed | `ruff check .`: All checks passed |
| `repository.types` | yes | passed | `mypy src tests`: no issues found in 53 source files |
| `plugin.validate` | yes | passed | `claude plugin validate .` exited 0. Warnings only: root CLAUDE.md, plus directory-submission LICENSE, icon, and privacy URL notes |
| `plugin.session-smoke` | yes | passed | The plugin loaded via `--plugin-dir` in an ephemeral project. `/mcp` shows `plugin:nmg-game-dev:blender` ✔ with 9 tools |

### Acceptance Criteria

- [x] AC1: Unreal 5.8 everywhere. `fixtures/dogfood.uproject` sets `EngineAssociation` to `5.8`, and the uplugin sets `EngineVersion` to `5.8.0`. `start-unreal-mcp.sh:14` and `run-ue-tests.sh:19` default `UE_ROOT` to `/Users/Shared/Epic Games/UE_5.8`, and `UE_ROOT` still overrides it. `git grep` finds no `UE_5.7`, `5.7.0`, or `Unreal Engine 5.7` outside `specs/` and `CHANGELOG.md`, apart from the guard's own constant at `tests/unit/test_toolchain_guards.py:45`.
- [x] AC2: Native MCP plus VibeUE. `start-unreal-mcp.sh:55-56` passes `-ModelContextProtocolStartServer -ModelContextProtocolPort=${PORT}`, with a default port of 8000, and exits 0 when the port is already LISTEN (line 17). The uproject enables `ModelContextProtocol`, `EditorToolset`, `VibeUE`, and `nmg-game-dev`. The INI sets `bAutoStartServer=True` and `ServerPortNumber=8000`. `fixtures/Source/**` and `fixtures/Config/**` are tracked, and `fixtures/Plugins/` is ignored. Live run: the launcher started UE 5.8, and the endpoint listened on 8000 within 35 s with no manual steps.
- [x] AC3: The `.mcp.json` `unreal` entry is `{"type":"http","url":"http://127.0.0.1:${UE_MCP_PORT:-8000}/mcp"}`, and its description names Epic's Unreal MCP plus VibeUE. The file has no `mcp-remote`, `8088`, or bridge wording. Guards are in `tests/unit/test_scaffold_guards.py`.
- [x] AC4: Unreal smoke passed live with exit 0. It ran initialize, found `execute_python_code`, and checked the engine version (`5.8.4-58902052+++UE5+Release-5.8`). It then imported `/Game/__NmgSmoke/SM_SmokeCube` and deleted `/Game/__NmgSmoke`. The stub-server tests in `tests/unit/test_smoke_unreal_mcp.py` cover exit codes 1 and 2.
- [x] AC5: The `.mcp.json` `blender` entry runs `uvx mcp-for-blender@latest` with `BLENDER_MCP_DISABLE_TELEMETRY=1` and has no `--with` or `mcp<2`. `start-blender-mcp.sh:49` lists `blender_mcp` first. Blender smoke passed live with exit 0 and reported `5.2.3 LTS`. Stub tests in `tests/unit/test_smoke_blender_mcp.py` cover exit codes 1 and 2.
- [x] AC6: The `blender` and `unreal` entries carry no version constraints. `install-vibeue.sh` does a depth-1 clone of the default branch, or `pull --ff-only` on an existing clone, with no tag or commit pin. `install-blender-mcp-addon.sh` runs `uvx mcp-for-blender@latest install-addon`. Guards are in `tests/unit/test_toolchain_guards.py`.
- [x] AC7: `docs/mcp/unreal.md` and `docs/mcp/blender.md` cover the two-layer setup, both ports, the overrides, the install and smoke scripts, and the latest-version policy. The steering tech snippet names UE 5.8 and port 8000, and its trust row says tools track the latest releases, verified by the smoke scripts. It has no 8088 or migration-pending wording. `README.md` no longer lists Node.js.

### Regression Obligations

None declared.

### Tasks

Every file listed for T001–T008 appears in the diff against `main` and behaves as each task's acceptance describes. T008's live-run acceptance was exercised in this verification and both smokes passed.

### Architecture Review

| Area | Score (1-5) |
|------|-------------|
| SOLID Principles | 4 |
| Security | 4 |
| Performance | 5 |
| Testability | 5 |
| Error Handling | 4 |

**Average**: 4.4

Findings:

- Each script has one job: launch, install, or smoke. The smoke scripts use only the standard library and have typed exit-code constants (`EXIT_OK`, `EXIT_FAILED`, `EXIT_UNREACHABLE`).
- The Unreal smoke always attempts cleanup after an import failure and reports the first failure (`scripts/smoke-unreal-mcp.py:398-413`).
- The spec requires third-party components to stay unpinned. The live smoke scripts are the trust control, and both passed.
- The version guard is now derived from `VERSION`, so a release bump cannot strand it again.
- Launching the fixture editor writes an `AndroidFileServer` `SecurityToken` into the tracked `fixtures/Config/DefaultEngine.ini` (see Remaining Issues).

### Test Coverage

- BDD scenarios: SCN001–SCN007 in `feature.gherkin` map all 7 acceptance criteria, backed by the guard and unit tests.
- Step definitions: Implemented
- Test execution: Pass. 253 passed, plus live Blender and Unreal smokes with exit 0.

### Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | 253 passed |
| `repository.lint` | Pass | ruff clean |
| `repository.types` | Pass | mypy clean |
| `plugin.validate` | Pass | exit 0 |
| `plugin.session-smoke` | Pass | `nmg-game-dev:blender` connected |

**Gate Summary**: 5/5 passed, 0 failed, 0 incomplete

### Live Smoke Evidence

| Script | Result | Output |
|--------|--------|--------|
| `scripts/smoke-blender-mcp.py` | exit 0 | `OK execute: … 5.2.3 LTS`, then `PASS blender smoke` |
| `scripts/start-unreal-mcp.sh` + `scripts/smoke-unreal-mcp.py` | exit 0 | `OK engine_version: 5.8.4…`, `OK import_check`, and `OK delete_check`, then `PASS unreal smoke` |

### Fixes Applied

| Severity | Category | Location | Issue | Fix | Routing |
|----------|----------|----------|-------|-----|---------|
| — | — | — | None. The verify publication scope only allows writing this report | — | — |

The editor launch wrote a `SecurityToken` line into `fixtures/Config/DefaultEngine.ini`. The verifier restored that file so the shared checkout stays clean at the verification head.

### Remaining Issues

| Severity | Category | Location | Issue | Reason Not Fixed |
|----------|----------|----------|-------|------------------|
| Low | hygiene | `fixtures/Config/DefaultEngine.ini` | On first launch, UE writes a random `SecurityToken` under `[/Script/AndroidFileServerEditor.AndroidFileServerRuntimeSettings]`, which dirties the tracked fixture config | Outside the verify write scope and outside AC scope. Follow-up: commit a fixed token, or disable the AndroidFileServer plugin in the fixture |

### Recommendation

Ready for PR.
