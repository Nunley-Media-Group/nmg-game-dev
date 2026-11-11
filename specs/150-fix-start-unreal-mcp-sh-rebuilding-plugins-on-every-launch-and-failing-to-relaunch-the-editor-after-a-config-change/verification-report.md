# Verification Report: start-unreal-mcp.sh rebuilds plugins on every launch and fails to relaunch the editor after a config change

**Date**: 2026-11-11
**Issue**: #150
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify worker)
**Scope**: Implementation verification against spec
**Verification head**: 79fcaebe9332018a0209fab4bc1c1114803afba0

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 5 |
| Testability | 4 |
| Error Handling | 5 |
| **Overall** | 4.8 |

### Implementation Status: Pass
**Total Issues**: 2 (both Low, non-blocking, test-harness and environment observations)

The launcher now looks for the UE 5.8 `libUnrealEditor-<Module>.dylib` name, with the legacy name as a fallback. It judges staleness per module against that module's own source directory and runs `Build.sh` with the single `-TargetType=Editor` selector. When a build fails and every module binary exists, it still launches the editor with a warning. It stops when a binary is missing, and it reports UnrealBuildTool's `Result: Failed` line instead of a placeholder. All seven ACs pass, with unit and BDD evidence. The full registered gate passed at the verification head: 11 declared, 11 recorded, coverage complete, 9 passed, and 2 not applicable to this change.

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 150 --spec specs/150-… --base main --controller-run-id 105d5000-3fb7-4ee3-a431-183f4768f3d9`, exit 0, `ok: true`
- Artifact: `.nmg-sdlc/verification/150.json`, generated 2026-11-11T22:38:11Z
- Identity: head `79fcaebe9332018a0209fab4bc1c1114803afba0`, tree clean, steering `sha256:119992c8…5096a9`, spec `sha256:b442ad94…6450b`
- Ceiling: `null` (no Incomplete or Fail cap)
- Coverage: declared 11, recorded 11, complete `true`, none missing, duplicated or unknown

---

## Issue Scope

- Active issue: #150
- Spec: `specs/150-fix-start-unreal-mcp-sh-rebuilding-plugins-on-every-launch-and-failing-to-relaunch-the-editor-after-a-config-change`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5, AC6, AC7]; FR [FR1, FR2, FR3, FR4, FR5, FR6, FR7]; tasks [T001, T002, T003, T004, T005]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005, SCN006, SCN007]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":150,"specPath":"specs/150-fix-start-unreal-mcp-sh-rebuilding-plugins-on-every-launch-and-failing-to-relaunch-the-editor-after-a-config-change","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7"],"tasks":["T001","T002","T003","T004","T005"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | A config change does not trigger a build or block the launch | Pass | `scripts/start-unreal-mcp.sh:109` (`plugin_needs_build` compares only module source dirs to binaries); `test_config_change_newer_than_binaries_does_not_trigger_a_build`, BDD SCN001 |
| AC2 | The build selects a single editor target | Pass | `scripts/start-unreal-mcp.sh:231` (`Build.sh Mac Development -Project=… -TargetType=Editor -NoEngineChanges`); `test_plugin_build_selects_a_single_editor_target[blueprint-only,code]`, BDD SCN002 (both examples) |
| AC3 | Current UE 5.8 binaries skip the build | Pass | `scripts/start-unreal-mcp.sh:83` (`module_binary`, lib prefix first); `test_current_unreal_editor_lib_binaries_skip_the_build`, `test_legacy_unreal_editor_binary_name_is_accepted_without_the_lib_prefixed_file`, BDD SCN003 |
| AC4 | A change to one module does not mark the plugin stale | Pass | `scripts/start-unreal-mcp.sh:96` (`module_source_dir` resolves the `<Module>.Build.cs` directory); `test_change_to_one_module_does_not_mark_the_plugin_stale`, BDD SCN004 |
| AC5 | A failed rebuild with usable binaries still launches | Pass | `scripts/start-unreal-mcp.sh:128-150,236` (`all_plugin_binaries_present` then the warning and fall-through to launch); `test_failed_rebuild_with_usable_binaries_warns_and_launches` passed in the registered gate and in a separate verbose rerun; BDD SCN005 |
| AC6 | A failed build with a missing binary still stops | Pass | `scripts/start-unreal-mcp.sh:238-241` (exit with Build.sh's status, log path on stderr); `test_failed_build_with_a_missing_binary_stops_without_launching` (exit 9, events `["build"]` only), BDD SCN006 |
| AC7 | The failure report shows UnrealBuildTool's reason | Pass | `scripts/start-unreal-mcp.sh:154` (`build_failure_reason`: `error:` line, else `Result: Failed`, else the last non-empty line, else `build log is empty`); `test_failure_report_shows_the_unreal_build_tool_reason`, BDD SCN007 |

Functional requirements FR1 through FR7 are covered by the same evidence: FR1 maps to AC2, FR2 to AC3 and the legacy-name test, and FR3 to AC1, AC4 and `test_uplugin_newer_than_binaries_does_not_trigger_a_build`. FR4 maps to AC5, FR5 to AC6, FR6 to AC7, and FR7 to the unit and BDD suites listed above.

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Correct the plugin build step in the launcher | Complete | `scripts/start-unreal-mcp.sh`. `gate-shellcheck` passed |
| T002 | Update the launcher fakes | Complete | `tests/start_unreal_fakes.py`: lib-prefixed `Sandbox.dylib`, single-target `expected_build_argv`, plus `stale`, `second_module`, `engine_ini_newer` and `code_project` options |
| T003 | Add unit regression tests | Complete | 10 new tests in `tests/unit/test_start_unreal_mcp.py` (AC2 parametrized for both project kinds). The #103 tests still pass |
| T004 | Add BDD scenarios and update the #103 feature | Complete | `start_unreal_plugin_relaunch.feature` holds SCN001–SCN007 with bound steps. The #103 feature now names `libUnrealEditor-FakeEditor.dylib` and the single-target argv |
| T005 | Update the Unreal MCP setup doc | Complete | `docs/mcp/unreal.md` setup step 2 describes per-module staleness, the single-target build, the warn-and-launch and stop paths, and the failure-reason order |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | Each new helper does one thing: binary lookup, source-dir lookup, staleness, presence, and failure reason |
| Open/Closed | 5 | Binary-name candidates are a list in `module_binary`, so a future naming change is a one-line addition |
| Liskov Substitution | 5 | Not applicable beyond the fake engine, which honors the same `Build.sh` and `UnrealEditor` contract |
| Interface Segregation | 5 | Helpers take only the plugin dir and module name they need |
| Dependency Inversion | 5 | Engine paths come from `UE_ROOT` and `UE_PROJECT`, which lets the tests inject a fake engine |

### Layer Separation

The change stays within the session-start launcher (`scripts/`), its doc, and its tests. It does not cross into skills, the pipeline or the UE plugin. The session-start contract invariants still hold: idempotent port check, detached launch, actionable failure, env-var path resolution, logs under `/tmp/`.

### Dependency Flow

`source_plugins` is computed once. The pre-build staleness loop and the post-failure presence check both read it, so the two decisions always cover the same plugin set.

---

## Security Assessment

- [x] Authentication: N/A (local launcher)
- [x] Authorization: N/A
- [x] Input validation: `.uplugin` files are parsed with `plutil`. A plugin whose `.uplugin` does not parse is treated as needing a build and as not having usable binaries, so the script fails closed
- [x] Injection prevention: every path and module name is quoted. The module name only reaches `find -name` as a literal pattern, and nothing is `eval`ed
- [x] Data protection: no secrets are touched. Logs go to the documented `/tmp` paths

## Performance Assessment

- [x] Async patterns: the build stays in the foreground by design (900 s hook timeout), and the editor launch stays detached
- [x] Caching: the fix removes the needless rebuild on every launch, which was the defect's main cost
- [x] Resource management: each staleness check is a single `find -newer -print -quit` over one module's directory, which stops at the first hit
- [x] Query optimization: N/A

## Testability Assessment

The fakes record argv and order through a shared event log, and every AC has a unit test and a BDD scenario that run the real launcher. The score is 4 rather than 5 because the suites still share the global `/tmp/unreal-mcp-build.log`, and the editor wait is bounded at 15 s. See the remaining issues.

## Error Handling Assessment

Failure is now classified: missing binaries stop the launch with Build.sh's own exit status, and present binaries produce a warning and a launch. Both paths print the log path and a concrete reason, and the uninformative `no compiler error found` placeholder is gone.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes | Yes |
| AC2 | Yes (SCN002, Blueprint-only + code) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes | Yes |
| AC5 | Yes (SCN005) | Yes | Yes |
| AC6 | Yes (SCN006) | Yes | Yes |
| AC7 | Yes (SCN007) | Yes | Yes |

### Coverage Summary

- Feature files: `start_unreal_plugin_relaunch.feature` (7 scenarios, 8 cases) and the updated `start_unreal_plugin_build.feature` (5 scenarios)
- Step definitions: Implemented
- Unit tests: 16 in `tests/unit/test_start_unreal_mcp.py` (10 new for #150)
- Full suite in the gate: `uv run pytest tests/unit tests/bdd -q`: 987 passed, 9 skipped, 0 failed
- Supplementary verbose rerun of the three launcher suites: 29 passed, 0 failed
- Flake watch: `test_failed_rebuild_with_usable_binaries_warns_and_launches` passed in the registered gate run and again in the verbose rerun. It did not flake during this verification.

---

## Exercise Test Results

Not applicable. The change does not touch `workflows/`, `agents/` or any skill. The registered `plugin.validate` and `plugin.session-smoke` gates ran because the version bump touched `.claude-plugin/plugin.json`, and both passed.

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 987 passed, 9 skipped in 94.87 s |
| `repository.lint` | Pass | `uv run ruff check .`: All checks passed |
| `repository.format` | Pass | `uv run ruff format --check .`: 310 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: no issues in 198 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 179 passed in 138.91 s (applies because of the `blender_manifest.toml` version bump). No cross-lane symlink failure this run |
| `gate-ue-compile` | Pass | `Build.sh DogfoodEditor Mac Development -Project=…/lane-6/fixtures/dogfood.uproject`: `Result: Succeeded`, 299.24 s, using this lane's own copy of `fixtures/Plugins` |
| `gate-mcp-schema` | N/A | Not applicable: no `mcp-servers/**` or schema-script change |
| `gate-shellcheck` | Pass | `find scripts -name *.sh -exec shellcheck -S style {} +` exited 0 |
| `gate-ship-smoke` | N/A | Not applicable: no ship-path change |
| `plugin.validate` | Pass | `claude plugin validate .`: Validation passed (with warnings that do not change the result) |
| `plugin.session-smoke` | Pass | Plugin loaded through `--plugin-dir` in an ephemeral Herdr project, and `nmg-game-dev:blender` connected |

**Gate Summary**: 9/9 applicable gates passed, 0 failed, 0 incomplete (2 not applicable; coverage 11/11 recorded)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | No fixes were needed during verification | — | — |

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
| **Category** | Testing |
| **Location** | `tests/start_unreal_fakes.py` (`BUILD_LOG`, `wait_for_editor`) |
| **Issue** | The launcher writes the fixed `/tmp/unreal-mcp-build.log` and `/tmp/unreal-mcp.log`, so lanes that run these suites at the same time share those files. The AC7 assertion reads the failure reason back from that shared log, and `wait_for_editor` waits at most 15 s for the detached fake editor. On a heavily loaded host this is the likely source of the single AC5 flake seen during implementation |
| **Impact** | Possible rare cross-lane test flake. No product impact |
| **Reason Not Fixed** | Making the log paths overridable is a launcher interface change outside this defect's spec. The test passed in this verification |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Architecture |
| **Location** | `scripts/start-unreal-mcp.sh:215` |
| **Issue** | `mapfile` (and iterating a possibly empty array under `set -u`) needs bash 4.4 or later. macOS `/bin/bash` is 3.2 |
| **Impact** | None new: the launcher already used `mapfile` on its default project-resolution path (line 36), so it already required a modern bash |
| **Reason Not Fixed** | The requirement already existed and is out of scope here |

---

## Positive Observations

- The per-module staleness model mirrors how UBT actually relinks, which removes both the false-positive rebuild and the "stale forever" trap.
- The warn-and-launch path uses the same plugin set as the staleness check, so the two decisions cannot disagree.
- The tests reproduce the exact field failure (`Result: Failed (ActionGraphInvalid)`, exit 9, no `error:` line).

---

## Recommendations Summary

### Before PR (Must)
- None.

### Short Term (Should)
- Consider env overrides for the two `/tmp` log paths so that parallel test runs can isolate them.

### Long Term (Could)
- Document the bash 4.4+ requirement for the launchers in the onboarding docs.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `scripts/start-unreal-mcp.sh` | 1 (Low, pre-existing) | Core fix |
| `tests/start_unreal_fakes.py` | 1 (Low) | Fakes extended |
| `tests/unit/test_start_unreal_mcp.py` | 0 | |
| `tests/bdd/features/start_unreal_plugin_relaunch.feature` | 0 | |
| `tests/bdd/test_start_unreal_plugin_relaunch_bdd.py` | 0 | |
| `tests/bdd/features/start_unreal_plugin_build.feature` | 0 | |
| `tests/bdd/test_start_unreal_plugin_build_bdd.py` | 0 | |
| `docs/mcp/unreal.md` | 0 | |
| `VERSION`, `CHANGELOG.md`, `.claude-plugin/plugin.json`, `blender_manifest.toml`, `nmg-game-dev.uplugin` | 0 | Version prep from commit 79fcaeb |

---

## Recommendation

**Ready for PR**

All seven ACs and five tasks are complete, and the evidence is traceable. Every applicable registered gate passed at the verification head with complete coverage. The remaining items are Low and outside this defect's scope.
