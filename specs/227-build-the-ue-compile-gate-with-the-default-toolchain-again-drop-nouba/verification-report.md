# Verification Report: gate-ue-compile builds with the default UE 5.8 toolchain (drop -NoUBA)

**Date**: 2026-11-12
**Issue**: #227
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify worker)
**Scope**: Defect-fix verification against the approved spec

**Verification head**: 68934cdba21be74bb37f507415ecf494e895baf8

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
**Total Issues**: 0

Change type: defect fix. Head `68934cd` merges origin/main (#230) and carries the 0.25.3 version bump.

The fix removes `-NoUBA` from the `project.ue-compile` provider and from `_build_headless()` in `scripts/unreal/build_master_material.py`. It reverts the `gate-ue-compile` documentation row and rewrites both unit tests so that they require the default argument list and reject `-NoUBA`. The registered `gate-ue-compile` run at this head called `Build.sh DogfoodEditor Mac Development -Project=<abs>/fixtures/dogfood.uproject -WaitMutex` against UE 5.8 and compiled, which confirms AC1 against the real engine. All 8 applicable registered validations passed. The other 3 do not apply to this change.

---

## Issue Scope

- Active issue: #227
- Spec: `specs/227-build-the-ue-compile-gate-with-the-default-toolchain-again-drop-nouba`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4]; FR [FR1, FR2, FR3, FR4]; tasks [T001, T002, T003]; scenarios [SCN001, SCN002, SCN003, SCN004]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":227,"specPath":"specs/227-build-the-ue-compile-gate-with-the-default-toolchain-again-drop-nouba","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4"],"functionalRequirements":["FR1","FR2","FR3","FR4"],"tasks":["T001","T002","T003"],"scenarios":["SCN001","SCN002","SCN003","SCN004"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Artifact: `.nmg-sdlc/verification/227.json` (`sdlc-verify-steering.mjs --base main --controller-run-id c8c10ae0-0b58-4978-8b00-fe444cbadbfb`)
- Identity: head `68934cdba21be74bb37f507415ecf494e895baf8`, tree clean, steering `sha256:7db2c1fd…b5bc93`, spec `sha256:c1ccf98b…94433c`
- Coverage: declared 11, recorded 11, complete `true`, with nothing missing, duplicated, or unknown
- Ceiling: none (`null`)

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | The gate builds with the default toolchain | Pass | `steering/extensions/ue-compile.mjs` `compile()`: `args = [target, "Mac", "Development", \`-Project=${project}\`, "-WaitMutex"]`, and the `-NoUBA` comment block is gone. In the live registered `gate-ue-compile` run, the command evidence was `Build.sh DogfoodEditor Mac Development -Project=…/fixtures/dogfood.uproject -WaitMutex` and the status was passed |
| AC2 | Docs match | Pass | The `gate-ue-compile` row in `steering/snippets/project-tech.md` reads `Build.sh DogfoodEditor Mac Development -WaitMutex`, with no `-NoUBA`, Unreal Build Accelerator, or parallel worktrees. Its "Applies when" and "Host prerequisite" cells are unchanged. `test_documented_gate_row_shows_default_build` asserts this |
| AC3 | The argument test guards the default build | Pass | `tests/unit/test_ue_compile_gate.py::test_gate_passes_default_arguments_to_build_sh` asserts that the logged argument list exactly equals the 5 default arguments, which excludes `-NoUBA`. It also asserts `"-NoUBA" not in commands[0]["summary"]` and `status == "passed"`. It is still skipped off macOS |
| AC4 | The headless master-material build uses the default toolchain | Pass | `scripts/unreal/build_master_material.py` `_build_headless()` no longer passes `-NoUBA`. `tests/unit/test_build_master_material.py::test_headless_builds_dogfood_then_runs_the_graph_in_a_separate_editor` asserts the exact list and `"-NoUBA" not in fake.build_args()`. Its editor-argument assertions are unchanged |

### Reproduction check

| Step | Before (#202 / #204) | After (this head) |
|------|----------------------|-------------------|
| 1–2: `uv run pytest tests/unit/test_ue_compile_gate.py -q` | Logged arguments ended in `-NoUBA`, and the test required it | Logged arguments are exactly `DogfoodEditor Mac Development -Project=<abs> -WaitMutex`; the test passes |
| 3: `gate-ue-compile` row | Documented `-NoUBA` and the parallel-worktree reason | Documents the default build only |
| 4: `uv run pytest tests/unit/test_build_master_material.py -q` | The headless build passed `-NoUBA` | Default arguments; the test passes |

`uv run pytest tests/unit/test_ue_compile_gate.py tests/unit/test_build_master_material.py -q` gave 24 passed. `grep -rn NoUBA steering scripts tests src skills docs` now matches only the negative assertions and the docstring history note in the tests.

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Build with the default toolchain arguments and document them | Complete | Provider args and the doc row are reverted; `ue-compile.mjs` contains neither `NoUBA` nor `Unreal Build Accelerator` |
| T002 | Guard the default build in the gate unit test | Complete | Both tests are renamed and rewritten as the design specifies; the docstring cites #227 |
| T003 | Build the headless master material with the default toolchain | Complete | The `-NoUBA` entry is removed and an absence assertion is added; the repository gates are green |

---

## Architecture Assessment (defect path: blast radius)

The change is about 10 changed lines across 5 files, so this review uses the defect path's blast-radius questions instead of the full SOLID table. Each score above records that the change introduces no finding in that area.

- **Other callers on the changed path.** Only the `gate-ue-compile` registration in `steering/manifest.json` calls the `project.ue-compile` provider. `--headless` mode alone calls `_build_headless()`. The live-MCP mode, the editor launch arguments, and `plugin-session-smoke.mjs` are untouched.
- **Public contract change.** None. The provider's request and result shapes, the macOS check, `UE_ROOT` resolution, error-line parsing, and the evidence format are unchanged. Only the argument list passed to `Build.sh` differs, which is the intended fix.
- **Silent data changes.** None. Engine builds return to UnrealBuildTool's default executor. Nothing is persisted or reinterpreted.
- **Security.** Arguments are still passed as an argv array without a shell, and the change adds no new inputs, secrets, or paths.
- **Performance.** UBA is the default executor again, so builds can use the accelerator. There is no runtime-module impact.
- **Error handling.** The `finish("incomplete", …)` paths for a missing project or engine, and the failed-build parsing, are unchanged.

### Minimal-change check

`git diff origin/main...HEAD` contains the five fix files, the #227 verification report, and the version bump to 0.25.3 with its CHANGELOG entry (`VERSION`, `.claude-plugin/plugin.json`, `blender_manifest.toml`, `nmg-game-dev.uplugin`). That bump is part of the delivery stage. The diff against local `main` also lists #226 spec and scaffold-test files. Those came in when origin/main (#230) was merged into this branch, and the diff against origin/main does not include them. The branch contains no unrelated refactors.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Test | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | SCN001 (`@regression`) | `test_gate_passes_default_arguments_to_build_sh` | Yes |
| AC2 | SCN002 (`@regression`) | `test_documented_gate_row_shows_default_build` | Yes |
| AC3 | SCN003 (`@regression`) | `test_gate_passes_default_arguments_to_build_sh` | Yes |
| AC4 | SCN004 (`@regression`) | `test_headless_builds_dogfood_then_runs_the_graph_in_a_separate_editor` | Yes |

All four scenarios carry `@regression`. Each would have failed before the fix, because the old code passed `-NoUBA` and the old row documented it, so the scenarios guard against the defect coming back.

---

## Exercise Test Results

Not applicable. The change touches no nmg-sdlc `workflows/` or `agents/` content and no consumer skill. The `plugin.validate` and `plugin.session-smoke` gates ran because the version bump changed `.claude-plugin/plugin.json`, and both passed.

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q` exited 0 |
| `repository.lint` | Pass | `uv run ruff check .` exited 0 |
| `repository.format` | Pass | `uv run ruff format --check .` exited 0 |
| `repository.types` | Pass | `uv run mypy src tests` exited 0 |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh` exited 0; it applies because of the `blender_manifest.toml` version bump |
| `gate-ue-compile` | Pass | `DogfoodEditor compiled against /Users/Shared/Epic Games/UE_5.8`. Command: `Build.sh DogfoodEditor Mac Development -Project=…/fixtures/dogfood.uproject -WaitMutex` (no `-NoUBA`) |
| `gate-mcp-schema` | Not applicable | No `mcp-servers/**` or `scripts/validate-mcp-tools.py` change |
| `gate-shellcheck` | Not applicable | No `scripts/**.sh` change |
| `gate-ship-smoke` | Not applicable | No ship path changed |
| `plugin.validate` | Pass | `claude plugin validate .` exited 0 |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir` in an ephemeral Herdr session; `nmg-game-dev:blender` connected |

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

- AC1 has two sources of evidence: the unit test with a fake `Build.sh`, and the real registered UE 5.8 compile at this head.
- The tests now assert exact argument lists, so any extra flag fails them, not only `-NoUBA`.
- The fix stays within the design's affected-code table.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `steering/extensions/ue-compile.mjs` | 0 | Args reverted, comment removed |
| `steering/snippets/project-tech.md` | 0 | Only the gate row's Runs cell changed |
| `tests/unit/test_ue_compile_gate.py` | 0 | Renamed tests; exact-list and absence assertions |
| `scripts/unreal/build_master_material.py` | 0 | One argument removed |
| `tests/unit/test_build_master_material.py` | 0 | Expected list updated; absence assertion added |

---

## Recommendation

**Ready for PR**

Every AC, FR, task, and `@regression` scenario is satisfied. All applicable registered gates passed at `68934cdba21be74bb37f507415ecf494e895baf8`, and the gate record is complete with no ceiling.
