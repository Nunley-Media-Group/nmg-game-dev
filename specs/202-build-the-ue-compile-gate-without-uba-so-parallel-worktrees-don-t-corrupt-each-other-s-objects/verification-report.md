# Verification Report: gate-ue-compile builds without UBA

**Date**: 2026-11-11
**Issue**: #202
**Reviewer**: Claude (nmg-sdlc architecture-reviewer)
**Scope**: Implementation verification against spec
**Verification head**: 53b4cc450bc43ef2acc800cf1d9685d4aeb202ad

---

## Executive Summary

The `project.ue-compile` provider now passes `-NoUBA` to `Build.sh`, with a comment explaining the per-user shared UBA cache. The `gate-ue-compile` row in `steering/snippets/project-tech.md` shows the flag and explains it. A new unit test runs the real provider through `node` against a fake `Build.sh` and checks the snippet row. Every applicable registered gate passed at the verification head. That includes a real `gate-ue-compile` build of `DogfoodEditor`, which recorded the command with `-WaitMutex -NoUBA` and ended with `Result: Succeeded`.

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 4 |
| Testability | 5 |
| Error Handling | 5 |
| **Overall** | 4.8 |

### Implementation Status: Pass
**Total Issues**: 0 blocking, 1 informational

---

## Issue Scope

- Active issue: #202
- Spec: `specs/202-build-the-ue-compile-gate-without-uba-so-parallel-worktrees-don-t-corrupt-each-other-s-objects`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2]; FR [FR1, FR2, FR3]; tasks [T001, T002, T003]; scenarios [SCN001, SCN002]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":202,"specPath":"specs/202-build-the-ue-compile-gate-without-uba-so-parallel-worktrees-don-t-corrupt-each-other-s-objects","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2"],"functionalRequirements":["FR1","FR2","FR3"],"tasks":["T001","T002","T003"],"scenarios":["SCN001","SCN002"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | The gate builds without UBA: `Build.sh` arguments include `-NoUBA` alongside target, platform, configuration, `-Project=` and `-WaitMutex` | Pass | `steering/extensions/ue-compile.mjs:58-61` builds `[target, "Mac", "Development", "-Project=<abs>", "-WaitMutex", "-NoUBA"]`. `tests/unit/test_ue_compile_gate.py::test_gate_passes_no_uba_to_build_sh` asserts the exact logged argv. The real `gate-ue-compile` run recorded `Build.sh DogfoodEditor Mac Development -Project=<lane>/fixtures/dogfood.uproject -WaitMutex -NoUBA` and passed |
| AC2 | The documented gate command matches and says why | Pass | `steering/snippets/project-tech.md:355` shows `Build.sh DogfoodEditor Mac Development -WaitMutex -NoUBA` and explains that the Unreal Build Accelerator's per-user shared cache lets parallel worktrees corrupt object files. `test_documented_gate_row_shows_no_uba_and_why` asserts both |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | `-NoUBA` added to the `args` array, with a three-line comment about the shared UBA session and cache |
| FR2 | Pass | `gate-ue-compile` row updated. The "Applies when" paths and host prerequisites are unchanged |
| FR3 | Pass | `tests/unit/test_ue_compile_gate.py` checks the argv logged by a fake `Build.sh` under a temporary `UE_ROOT` |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Build the gate without UBA | Complete | Provider id, frozen `extension` export, status rules and Node-built-in-only imports unchanged. The evidence `summary` records `-NoUBA` with no extra code |
| T002 | Document the flag in the gate row | Complete | Matches the design's exact cell text |
| T003 | Cover the build arguments and the documented row | Complete | Provider test is skipped off darwin and starts no real engine, editor or Blender process. Both tests fail without T001/T002: the argv equality and the row-substring assertions depend on the new text |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | One-argument change inside `compile()`. No new responsibilities |
| Open/Closed | 5 | Provider contract and manifest registration unchanged |
| Liskov Substitution | 5 | N/A. The provider return shape is unchanged |
| Interface Segregation | 5 | Request/result contract untouched |
| Dependency Inversion | 5 | The module still imports only `node:child_process`, `node:fs` and `node:path` |

### Layer Separation

The change stays in the steering extension layer and its documentation. No pipeline, skill or UE plugin code is touched.

### Dependency Flow

Unchanged. The test calls the provider through its public `extension.providers["project.ue-compile"]` export rather than internals.

---

## Security Assessment

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: unchanged. `config.project`/`config.target` type checks remain
- [x] Injection prevention: `spawn(..., { shell: false })` with an argv array. The new argument is a constant
- [x] Data protection: no secrets involved. The test passes `os.environ` through only to the local fake

---

## Performance Assessment

- [x] Async patterns: unchanged
- [x] Caching: deliberately loses UBA's cache and distribution, so cold builds may be slower (accepted in the design's Blast Radius). UBT's local incremental build in each checkout's `Intermediate/` still applies
- [x] Resource management: unchanged. The abort signal still kills the child
- [x] Query optimization: N/A

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (`test_gate_passes_no_uba_to_build_sh`) | Yes |
| AC2 | Yes (SCN002) | Yes (`test_documented_gate_row_shows_no_uba_and_why`) | Yes |

### Coverage Summary

- Feature files: 2 scenarios in `feature.gherkin`. Per the spec header, they are implemented as pytest unit tests in `tests/unit/test_ue_compile_gate.py`
- Step definitions: Implemented (as the two unit tests)
- Unit tests: 2 new. Targeted run: `2 passed in 0.65s`
- Full suite: `repository.tests` gave 1133 passed, 9 skipped

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable. The change touches no nmg-sdlc `workflows/` or `agents/` files and no shipped Claude Code plugin surface (skills, `.mcp.json`, hooks). The project's own plugin smoke, `plugin.session-smoke`, ran and passed |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

Source: `.nmg-sdlc/verification/202.json`, written by `sdlc-verify-steering.mjs` at head `53b4cc450bc43ef2acc800cf1d9685d4aeb202ad`. Coverage: declared 11, recorded 11, complete. Ceiling: none.

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 1133 passed, 9 skipped |
| `repository.lint` | Pass | `uv run ruff check .`: All checks passed |
| `repository.format` | Pass | `uv run ruff format --check .`: 335 files already formatted |
| `repository.types` | Pass | `uv run mypy src tests`: no issues in 212 source files |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh`: 273 passed |
| `gate-ue-compile` | Pass | Real build: `Build.sh DogfoodEditor Mac Development -Project=…/fixtures/dogfood.uproject -WaitMutex -NoUBA`, `Result: Succeeded` |
| `gate-mcp-schema` | Pass | `uv run python scripts/validate-mcp-tools.py` exited 0 |
| `gate-shellcheck` | Pass | `shellcheck -S style` over `scripts/**.sh` exited 0 |
| `gate-ship-smoke` | Not applicable | No ship paths changed |
| `plugin.validate` | Pass | `claude plugin validate .`: Validation passed (with warnings) |
| `plugin.session-smoke` | Pass | Plugin loaded via `--plugin-dir`. `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable)

---

## Fixes Applied

None. No findings needed a fix.

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
| **Severity** | Low (informational) |
| **Category** | Performance |
| **Location** | `steering/extensions/ue-compile.mjs:61` |
| **Issue** | With UBA off, cold `gate-ue-compile` builds compile everything locally with no shared cache |
| **Impact** | Slower first builds in each worktree. Incremental builds are unaffected |
| **Reason Not Fixed** | Intended trade-off, recorded in design.md Blast Radius and Alternatives |

---

## Positive Observations

- Minimal, well-scoped fix. The evidence summary picks up the flag automatically, so the recorded command proves it.
- The test runs the real provider module end to end against a fake engine script, rather than re-implementing the argv, so it guards the actual behavior.
- The real gate run in this lane confirmed that UE 5.8's `Build.sh` accepts `-NoUBA` and builds the dogfood target successfully.

---

## Recommendations Summary

### Before PR (Must)
- None

### Short Term (Should)
- None

### Long Term (Could)
- Consider the same `-NoUBA` flag for the UBT call in `scripts/run-ue-tests.sh` when `gate-ue-automation` is registered (out of scope here).

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `steering/extensions/ue-compile.mjs` | 0 | `-NoUBA` plus explanatory comment |
| `steering/snippets/project-tech.md` | 0 | `gate-ue-compile` row updated |
| `tests/unit/test_ue_compile_gate.py` | 0 | New AC1/AC2 coverage |
| `CHANGELOG.md`, `VERSION`, plugin manifests | 0 | Prepared release 0.21.6 entry |

---

## Recommendation

**Ready for PR**

Both acceptance criteria, all three functional requirements and all three tasks are met. Coverage of the registered gates is complete, and every applicable required gate passed at the verification head, including a real UE build with `-NoUBA`.
