# Verification Report: gate-ue-compile builds with the default UE 5.8 toolchain (drop -NoUBA)

**Date**: 2026-11-12
**Issue**: #227
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify worker)
**Scope**: Defect-fix verification against the approved spec

**Verification head**: f7d88836b161e06a55f94ff59e76651cc91d097d

---

## Executive Summary

The fix removes `-NoUBA` from both `Build.sh` callers: the `project.ue-compile` gate provider and `scripts/unreal/build_master_material.py --headless`. It also reverts the `gate-ue-compile` documentation row. The unit tests for both callers now assert the exact default argument list and that `-NoUBA` is absent. All four ACs pass. All 11 registered validations are recorded: the 8 that apply passed, and `gate-mcp-schema`, `gate-shellcheck` and `gate-ship-smoke` do not apply to this change.

The implement stage did not run the real UE 5.8 `Build.sh`. It proved the change only against the fake `Build.sh` used by the unit tests. This verify stage did run the real build. Because the change touches `plugins/nmg-game-dev-ue-plugin/nmg-game-dev.uplugin` (the version bump), the registered `gate-ue-compile` gate applied. It ran `/Users/Shared/Epic Games/UE_5.8/Engine/Build/BatchFiles/Mac/Build.sh DogfoodEditor Mac Development -Project=<checkout>/fixtures/dogfood.uproject -WaitMutex` with no `-NoUBA`. The result was `Result: Succeeded` in 12.93 s. The build was incremental: the plugin's C++ sources did not change, so it did not recompile the whole plugin. UBT wrote a `Trace.uba` file, which confirms the build used the default toolchain with the Unreal Build Accelerator on. No live Blender or Unreal Editor session was opened or driven.

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
**Verification type**: defect fix
**Total Issues**: 0

---

## Issue Scope

- Active issue: #227
- Spec: `specs/227-build-the-ue-compile-gate-with-the-default-toolchain-again-drop-nouba`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4]; FR [FR1, FR2, FR3, FR4]; tasks [T001, T002, T003]; scenarios [SCN001, SCN002, SCN003, SCN004]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":227,"specPath":"specs/227-build-the-ue-compile-gate-with-the-default-toolchain-again-drop-nouba","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4"],"functionalRequirements":["FR1","FR2","FR3","FR4"],"tasks":["T001","T002","T003"],"scenarios":["SCN001","SCN002","SCN003","SCN004"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --issue 227 --base main --controller-run-id 0a81c5bd-e091-499a-bab9-e2a7f6a59569`
- Artifact: `.nmg-sdlc/verification/227.json`, generated 2026-11-12T15:12:44Z
- Identity: head `f7d88836b161e06a55f94ff59e76651cc91d097d`, clean tree, spec hash `sha256:c1ccf98b…`, steering hash `sha256:7db2c1fd…`
- Coverage: declared 11, recorded 11, complete `true`; missing, duplicate and unknown are all empty
- Ceiling: `null`. No required validation failed or was incomplete.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | The gate builds with the default toolchain | Pass | `steering/extensions/ue-compile.mjs:58` sets `args` to `[target, "Mac", "Development", `-Project=${project}`, "-WaitMutex"]`. The `-NoUBA` comment block is removed. `test_gate_passes_default_arguments_to_build_sh` (`tests/unit/test_ue_compile_gate.py:40`) runs the real provider against a fake `Build.sh` and passed. The real `gate-ue-compile` command evidence for this head shows the same five arguments. |
| AC2 | Docs match | Pass | `steering/snippets/project-tech.md:355`: the row reads `Build.sh DogfoodEditor Mac Development -WaitMutex`. It no longer mentions `-NoUBA`, the Unreal Build Accelerator, or parallel worktrees, and its "Applies when" and "Host prerequisite" cells are unchanged. `test_documented_gate_row_shows_default_build` (`tests/unit/test_ue_compile_gate.py:87-94`) guards it. |
| AC3 | The argument test guards the default build | Pass | `tests/unit/test_ue_compile_gate.py:75-84`: an exact list-equality check on the logged arguments, which also rules out `-NoUBA`; `status == "passed"`; and `"-NoUBA" not in commands[0]["summary"]`. |
| AC4 | The headless master-material build uses the default toolchain | Pass | `scripts/unreal/build_master_material.py:228-237`: `_build_headless()` passes `DogfoodEditor, Mac, Development, -Project=<DOGFOOD_PROJECT>, -WaitMutex`. `tests/unit/test_build_master_material.py:519-527` asserts that exact list and `"-NoUBA" not in fake.build_args()`. The editor-argument assertions are unchanged. |

### Reproduction Check (defect path)

| Step | Before (#202/#204) | After (this head) |
|------|--------------------|-------------------|
| 1-2: provider `Build.sh` args with a fake engine | ended with `-NoUBA` | exactly `DogfoodEditor Mac Development -Project=<abs> -WaitMutex` |
| 3: `gate-ue-compile` documentation row | documented `-NoUBA` and the UBA/parallel-worktree reason | documents the default build only |
| 4: `build_master_material.py --headless` `Build.sh` args | ended with `-NoUBA` | exactly the default five arguments |

`grep -rn NoUBA steering scripts src plugins docs` returns no matches. The only remaining mentions are the negative assertions and the docstring in the two unit tests.

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Build with the default toolchain arguments and document them | Complete | `ue-compile.mjs` and the `project-tech.md` row |
| T002 | Guard the default build in the gate unit test | Complete | The tests were renamed as the design specifies and pass. The provider test still skips off macOS. |
| T003 | Build the headless master material with the default toolchain | Complete | `_build_headless()` and its test changed; the full repository gates passed |

---

## Architecture Assessment (defect path: blast radius)

The fix is small: about 10 changed source and test lines. Following `defect-path.md`, the review focused on blast radius instead of running the full checklist suite.

- **Other callers on the changed path**: `compile()` in `ue-compile.mjs` is reached only through the `project.ue-compile` provider registered in `steering/manifest.json`. `_build_headless()` is reached only through `build_master_material.py --headless`. No other code builds `Build.sh` argument lists.
- **Public contract change**: none. The provider's evidence shape, status values, macOS check, `UE_ROOT` resolution and error parsing are unchanged. The script's exit codes, editor arguments and live-MCP mode are unchanged.
- **Silent data changes**: none. The only change is to build-tool flags: UBT now uses its default executor (UBA). The build output location is still the checkout's own `Intermediate/` and `Binaries/` folders.
- **Minimal-change check**: compared with `origin/main`, the branch changes 14 files: 5 fix files, 4 version files, `CHANGELOG.md` and the 4 #227 spec files. The 4 #226 spec files appear only in `git diff main...HEAD` because the local `main` ref is behind `origin/main`, which already contains commit `0d4cc8b` (`docs: approve spec for #226 (#228)`). They are not part of this change. The version bump to 0.25.2 (patch, `bug` label) and its CHANGELOG entry are the controller's delivery preparation. No unrelated refactors.

| Area | Score | Notes |
|------|-------|-------|
| SOLID | 5 | The change stays inside each function; no responsibilities move |
| Security | 5 | `spawn(..., shell: false)` and `subprocess.run` with an argument list are unchanged; no new inputs |
| Performance | 5 | Returns to UBT's default, faster executor |
| Testability | 5 | Both callers are covered by fake-engine unit tests with exact argument assertions |
| Error Handling | 5 | Failure paths (`build_failed`, `incomplete` off macOS or with no engine) are untouched |

---

## Security Assessment

- [x] Authentication: not applicable
- [x] Authorization: not applicable
- [x] Input validation: unchanged (`target` still falls back to `DogfoodEditor` when config is not a string)
- [x] Injection prevention: no shell; argument arrays only
- [x] Data protection: no credentials involved

## Performance Assessment

- [x] Async patterns: unchanged
- [x] Caching: UBA's default cache is used again
- [x] Resource management: unchanged
- [x] Query optimization: not applicable

---

## Test Coverage

### BDD Scenarios

The spec's `feature.gherkin` maps each `@regression` scenario to an executable unit test, as its header records (`# File: tests/unit/test_ue_compile_gate.py`).

| Scenario | AC | Executable test | Passes |
|----------|----|-----------------|--------|
| SCN001 | AC1 | `test_gate_passes_default_arguments_to_build_sh` | Yes |
| SCN002 | AC2 | `test_documented_gate_row_shows_default_build` | Yes |
| SCN003 | AC3 | `test_gate_passes_default_arguments_to_build_sh` (exact-list and negative evidence assertions) | Yes |
| SCN004 | AC4 | `test_headless_builds_dogfood_then_runs_the_graph_in_a_separate_editor` | Yes |

### Coverage Summary

- Feature scenarios: 4, all tagged `@regression`
- `repository.tests`: 1722 passed, 14 skipped
- `gate-blender-headless`: 382 passed, 4 skipped

---

## Exercise Test Results

Not applicable. The change touches no nmg-sdlc `workflows/` or `agents/` files. The plugin load path was still checked by `plugin.validate` and `plugin.session-smoke`.

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q` exited 0: 1722 passed, 14 skipped |
| `repository.lint` | Pass | `uv run ruff check .`: All checks passed! |
| `repository.format` | Pass | `uv run ruff format --check .`: 417 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: no issues found in 265 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh` exited 0: 382 passed, 4 skipped (headless background Blender; no live session) |
| `gate-ue-compile` | Pass | Real UE 5.8 `Build.sh DogfoodEditor Mac Development -Project=…/fixtures/dogfood.uproject -WaitMutex` (no `-NoUBA`): `Result: Succeeded`, 12.93 s, incremental. It applied because `nmg-game-dev.uplugin` changed (version bump). No editor was launched. |
| `gate-mcp-schema` | Not applicable | No `mcp-servers/**` or validator changes |
| `gate-shellcheck` | Not applicable | No `scripts/**.sh` changes |
| `gate-ship-smoke` | Not applicable | No ship-path changes |
| `plugin.validate` | Pass | `claude plugin validate .` exited 0. Its one warning (CLAUDE.md at the plugin root is not loaded as context) was already present and is unrelated. |
| `plugin.session-smoke` | Pass | Ephemeral project, `herdr agent start … --plugin-dir <checkout>`, then `/mcp` rows read and the tab closed |

**Gate Summary**: 8/8 applicable gates passed, 0 failed, 0 incomplete (3 not applicable)

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | — | — | None needed during verification | — | — |

## Remaining Issues

None.

---

## Positive Observations

- The provider test runs the real `.mjs` provider through node against a fake engine, so the argument contract is proven without starting a build.
- The gate checks the `-NoUBA` regression in three places: the logged arguments, the gate's command evidence, and the documentation row.

---

## Recommendations Summary

### Before PR (Must)
- None

### Short Term (Should)
- None

### Long Term (Could)
- Note: `gate-ue-compile` is incremental, so a run with no Source changes, like this one, mostly checks the toolchain arguments. A version-only `.uplugin` change does not force a full rebuild.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `steering/extensions/ue-compile.mjs` | 0 | `-NoUBA` and its comment removed |
| `steering/snippets/project-tech.md` | 0 | Row reverted |
| `scripts/unreal/build_master_material.py` | 0 | `-NoUBA` removed |
| `tests/unit/test_ue_compile_gate.py` | 0 | Renamed tests, exact and negative assertions |
| `tests/unit/test_build_master_material.py` | 0 | Exact list and negative assertion |
| `VERSION`, `.claude-plugin/plugin.json`, `blender_manifest.toml`, `nmg-game-dev.uplugin`, `CHANGELOG.md` | 0 | 0.25.2 patch bump and Fixed entry |

---

## Recommendation

**Ready for PR**

All four acceptance criteria and their `@regression` scenarios pass. All 8 applicable registered gates passed at head `f7d88836b161e06a55f94ff59e76651cc91d097d`. That includes a real UE 5.8 default-toolchain build of `DogfoodEditor`, which the implement stage had not run.
