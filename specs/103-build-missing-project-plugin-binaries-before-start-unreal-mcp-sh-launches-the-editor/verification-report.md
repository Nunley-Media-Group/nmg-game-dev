# Verification Report: Build missing project plugin binaries before start-unreal-mcp.sh launches the editor

**Issue**: #103
**Spec**: `specs/103-build-missing-project-plugin-binaries-before-start-unreal-mcp-sh-launches-the-editor`
**Date**: 2026-10-31
**Verification head**: 36423f579f8db3e5717f8f3abf8d5f363cea4669

## Implementation Status: Pass

## Executive Summary

`scripts/start-unreal-mcp.sh` now finds the project's enabled source-only plugins (in `Plugins/` and in `AdditionalPluginDirectories`) and checks each one's Mac editor dylibs. If any are missing or stale, it runs the engine's `Build.sh` editor build in the foreground before it launches the editor. A failed build, or a missing `Build.sh`, stops the launch with an actionable message. The consumer SessionStart hook now has a 900-second timeout. The onboarding merge raises a lower or missing timeout and reports the change as `refreshed`. All 5 acceptance criteria and all 4 tasks are met. All 5 registered validations passed at the verification head, and no fixes were needed.

**Architecture average**: 4.6 / 5

## Deterministic Steering Artifact

- Runner: `sdlc-verify-steering.mjs --base main --controller-run-id 1d8c53d8-6b3c-4e22-a1d5-e8a4c8a68d96`, which returned `ok: true` with `ceiling: null`
- Artifact: `.nmg-sdlc/verification/103.json` (head `36423f5…`, steering `sha256:19b4c539…`, spec `sha256:8f1aabf3…`)
- Coverage: declared 5, recorded 5, complete `true`, with nothing missing, duplicated or unknown
- Ceiling: none

| Validation | Provider | Required | Status | Summary |
|------------|----------|----------|--------|---------|
| repository.tests | builtin.command | yes | passed | `uv run pytest tests/unit tests/bdd -q` exited 0 |
| repository.lint | builtin.command | yes | passed | `uv run ruff check .` exited 0 |
| repository.types | builtin.command | yes | passed | `uv run mypy src tests` exited 0 |
| plugin.validate | builtin.command | yes | passed | `claude plugin validate .` exited 0 (`templates/consumer/**` changed) |
| plugin.session-smoke | project.plugin-session-smoke | yes | passed | plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

## Issue Scope

- Active issue: #103
- Spec: `specs/103-build-missing-project-plugin-binaries-before-start-unreal-mcp-sh-launches-the-editor`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4, AC5]; FR [FR1, FR2, FR3, FR4, FR5]; tasks [T001, T002, T003, T004]; scenarios [SCN001, SCN002, SCN003, SCN004, SCN005]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":103,"specPath":"specs/103-build-missing-project-plugin-binaries-before-start-unreal-mcp-sh-launches-the-editor","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5"],"tasks":["T001","T002","T003","T004"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

### Delivery Validation

- Local verification: Pass
- PR evidence: Not required

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Missing binaries are built before launch | Pass | `scripts/start-unreal-mcp.sh:122` (discovers `Plugins/` and `AdditionalPluginDirectories`), `:81` (missing dylib means a build), `:164` (log line), `:166` (exact `Build.sh` argv), `:180` (launch only after the build succeeds); `tests/unit/test_start_unreal_mcp.py:23`, `:86`; SCN001 |
| AC2 | Present binaries skip the build | Pass | `scripts/start-unreal-mcp.sh:100` (`find Source uplugin -newer <oldest dylib>`); `tests/unit/test_start_unreal_mcp.py:35`; SCN002 |
| AC3 | Build failure is reported | Pass | `scripts/start-unreal-mcp.sh:167-173` (non-zero exit with Build.sh's status, log path, first `error:` line or `no compiler error found`); `tests/unit/test_start_unreal_mcp.py:46`; SCN003 |
| AC4 | Missing build tool is reported | Pass | `scripts/start-unreal-mcp.sh:160-162` (names the `Build.sh` path and `UE_ROOT`, exits 1); `tests/unit/test_start_unreal_mcp.py:62`; SCN004 |
| AC5 | The SessionStart hook allows the build to finish | Pass | `templates/consumer/.claude/settings.json` (`"timeout": 900` on the unreal hook only); `src/nmg_game_dev/onboard/settings.py:66-86` (raises an absent or lower timeout and returns `refreshed`); `tests/unit/onboard/test_settings.py`; SCN005 |

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `editor_modules`, `plugin_needs_build`, `plugin_disabled`, `project_source_plugins` |
| FR2 | Pass | foreground `Build.sh` run, output to `/tmp/unreal-mcp-build.log` |
| FR3 | Pass | AC3 and AC4 paths |
| FR4 | Pass | template + `merge_session_hooks` |
| FR5 | Pass | `docs/mcp/unreal.md` "Start the editor" step |

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Pre-launch plugin binary check and build | Complete | Port check, editor check, resolution order, and launch flags are unchanged. `shellcheck -S style scripts/*.sh` exits 0 |
| T002 | 900-second hook timeout | Complete | The Blender hook is unchanged. Other hooks and keys keep their values and order |
| T003 | Document the pre-launch build | Complete | `docs/mcp/unreal.md` and the CHANGELOG Added bullet ending `(#103)` (released as `[0.16.0]`) |
| T004 | Launcher and onboarding tests | Complete | 6 launcher unit tests, SCN001–SCN005 bound, and the scaffold launcher scenario updated. The targeted run passed 34 tests |

## Architecture Assessment

| Area | Score (1-5) | Notes |
|------|-------------|-------|
| SOLID Principles | 5 | Each small shell function has one job (module listing, staleness, enablement, discovery). The merge keeps its add path and adds a separate raise pass |
| Security | 5 | No secrets. All paths are quoted, which matters for install paths with spaces such as `/Volumes/Fast Brick`. No `eval`. The build log goes to a fixed `/tmp` path, as the existing `LOG` already does |
| Performance | 4 | When binaries are current, the cost is one `plutil` call per module and one `find -quit`. `plutil -extract` runs once per field per index, which is fine at project-plugin scale |
| Testability | 5 | Fake `UE_ROOT` with argv-recording `UnrealEditor` and `Build.sh`. Tests cover the disabled-plugin and `AdditionalPluginDirectories` paths beyond the ACs |
| Error Handling | 4 | Actionable one-line failures. An unparseable `.uplugin` counts as needing a build, so UBT reports the real error. `set -e` behaves correctly with `\|\| build_status=$?` |

**Average**: 4.6

### Layer Separation / Dependency Flow

The change stays in the session-start launcher and the onboarding settings merge, and it adds no new cross-layer dependencies. The launcher still only launches. The nmg-game-dev UE plugin still binds no port.

## Security Assessment

- [x] Authentication: not applicable
- [x] Authorization: not applicable
- [x] Input validation: the `.uproject` and `.uplugin` are read through `plutil`. A file it cannot parse leads to a build, not a crash
- [x] Injection prevention: values from the `.uproject` and `.uplugin` are quoted and never evaluated
- [x] Data protection: no credentials are touched or logged

## Performance Assessment

- [x] Async patterns: the build runs in the foreground by design, so failures surface in the session. The editor launch stays detached
- [x] Caching: the mtime check skips the build when binaries are current
- [x] Resource management: no leaked processes. `nohup … & disown` is unchanged
- [x] Query optimization: not applicable

## Test Coverage

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes | Yes |
| AC2 | Yes (SCN002) | Yes | Yes |
| AC3 | Yes (SCN003) | Yes | Yes |
| AC4 | Yes (SCN004) | Yes | Yes |
| AC5 | Yes (SCN005) | Yes | Yes |

- BDD scenarios: 5/5 acceptance criteria covered
- Step definitions: Implemented (`tests/bdd/test_start_unreal_plugin_build_bdd.py`)
- Test execution: Pass. The full `pytest tests/unit tests/bdd` passed through `repository.tests`. The targeted run passed 34 tests

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. The diff touches no nmg-sdlc `workflows/` or `agents/`. The plugin load was checked through `plugin.validate` and `plugin.session-smoke` |
| **Recommendation** | None |

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | command exited 0 |
| repository.lint | Pass | command exited 0 |
| repository.types | Pass | command exited 0 |
| plugin.validate | Pass | command exited 0 |
| plugin.session-smoke | Pass | plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |
| gate-shellcheck (prose steering, T001 acceptance) | Pass | `shellcheck -S style scripts/*.sh` exit 0 |

**Gate Summary**: 5/5 registered validations passed, 0 failed, 0 incomplete

No `repository.nmg-sdlc-smoke` or `project.nmg-sdlc-smoke` validation is declared in `steering/manifest.json`. The declared `plugin.session-smoke` passed for real.

## Fixes Applied

None. No findings needed a fix.

## Remaining Issues

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `tests/unit/test_start_unreal_mcp.py` |
| **Issue** | No test runs the "dylib present but older than a `Source/` file" case. The tests cover only a missing dylib and a current one |
| **Impact** | A regression in the `-newer` comparison (`scripts/start-unreal-mcp.sh:100`) would not be caught. The behaviour is implemented and was checked by code review |
| **Reason Not Fixed** | This case is not named in the AC or task acceptance criteria. It is an optional hardening test |

## Positive Observations

- `-NoEngineChanges` and the plugin-scoped discovery keep the build away from the engine, as Out of Scope requires.
- The merge reuses the template's hook dict for newly added hooks, so a fresh add is not miscounted as a raise.
- The documentation update ships in the same PR as the capability, per the structure steering anti-pattern rule.

## Recommendations Summary

### Before PR (Must)
- None

### Short Term (Should)
- [ ] Add a stale-dylib unit test (a source touched after the dylib, so Build.sh runs)

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| scripts/start-unreal-mcp.sh | 0 | |
| src/nmg_game_dev/onboard/settings.py | 0 | |
| templates/consumer/.claude/settings.json | 0 | |
| docs/mcp/unreal.md | 0 | |
| CHANGELOG.md | 0 | |
| tests/unit/test_start_unreal_mcp.py | 1 (low) | stale case untested |
| tests/start_unreal_fakes.py | 0 | |
| tests/bdd/features/start_unreal_plugin_build.feature | 0 | |
| tests/bdd/test_start_unreal_plugin_build_bdd.py | 0 | |
| tests/bdd/steps/test_scaffold.py | 0 | |
| tests/unit/onboard/test_settings.py | 0 | |

## Recommendation

**Ready for PR**

All acceptance criteria, functional requirements and tasks are met. Every registered validation passed at `36423f579f8db3e5717f8f3abf8d5f363cea4669`, and the remaining finding is a low-priority test-hardening suggestion.
