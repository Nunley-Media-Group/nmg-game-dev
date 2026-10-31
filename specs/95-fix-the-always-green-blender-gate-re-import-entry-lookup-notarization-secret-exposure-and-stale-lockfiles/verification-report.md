# Verification Report: Always-green Blender gate, re-import entry lookup, notarization secret exposure, and stale lockfiles

**Date**: 2026-10-30
**Issue**: #95
**Reviewer**: Claude
**Scope**: Implementation verification against spec
**Verification head**: eb78418ca69459ba593c0309188073078b6046c5

---

## Executive Summary

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

**Total Issues**: 2 (both low, no fix needed for delivery)

All eleven acceptance criteria are implemented and covered by tests. All five registered validations pass at the verification head (`.nmg-sdlc/verification/95.json`, coverage 5/5 complete). Every steering gate that applies passed, including the full headless Blender gate with the host add-on installed. The spec was amended on 2026-10-30 to add AC9/FR7 (coexistence assertion) and AC10/FR8 (removal of the unrunnable `gate-skill-schema` and `gate-markdown-lint`), after the first implement pass showed those gates could not go green within the original scope. It was amended again on 2026-10-31 to add AC11/FR9: the 0.14.1 release bump (`eb2d273`) pushed the #7 changelog entries below the first release section, which broke the onboarding changelog guard.

---

## Issue Scope

- Active issue: #95
- Spec: `specs/95-fix-the-always-green-blender-gate-re-import-entry-lookup-notarization-secret-exposure-and-stale-lockfiles`
- Manifest: implicit single issue
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1–AC11]; FR [FR1–FR9]; tasks [T001–T010]; scenarios [SCN001–SCN009]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":95,"specPath":"specs/95-fix-the-always-green-blender-gate-re-import-entry-lookup-notarization-secret-exposure-and-stale-lockfiles","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4","AC5","AC6","AC7","AC8","AC9","AC10","AC11"],"functionalRequirements":["FR1","FR2","FR3","FR4","FR5","FR6","FR7","FR8","FR9"],"tasks":["T001","T002","T003","T004","T005","T006","T007","T008","T009","T010"],"scenarios":["SCN001","SCN002","SCN003","SCN004","SCN005","SCN006","SCN007","SCN008","SCN009"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Blender gate fails on a failing test | Pass | `scripts/run-blender-tests.sh` passes `--python-exit-code 1`; `tests/blender/_runner.py` flushes and calls `os._exit(int(result))`. `tests/unit/test_run_blender_tests.py` runs real Blender: a failing suite and an erroring suite each exit non-zero, a passing suite exits 0 |
| AC2 | Re-import resolves the entry through `CLAUDE_PLUGIN_ROOT` | Pass | `contract_core/reimport.py` `entry_script()`; `tests/blender/test_reimport_entry.py::test_ac2_*` |
| AC3 | Checkout fallback and a clear error | Pass | `entry_script()` falls back to `CHECKOUT_ENTRY_SCRIPT`, then raises `reimport.entry_missing` naming both paths and `CLAUDE_PLUGIN_ROOT`; `test_reimport_entry.py::test_ac3_*` (5 tests) |
| AC4 | Keychain profile keeps secrets out of argv | Pass | `scripts/notarize-macos.sh` profile branch; `tests/unit/ship/test_scripts.py`; `targets.py` `_required()`; `tests/unit/ship/test_targets.py` |
| AC5 | Password path still works and warns | Pass | stderr warning before submit; masked `RUN:` line kept; `test_scripts.py` asserts the warning and that the password never appears |
| AC6 | Version bump leaves every lockfile in sync | Pass | `pyproject.toml` `dynamic = ["version"]`, `[tool.hatch.version]`, `[tool.uv] cache-keys`; all three locks relocked; `tests/unit/test_lockfiles.py::test_version_bump_keeps_every_lock_in_sync` |
| AC7 | Lock drift is caught by a test | Pass | `test_lockfiles.py::test_committed_lock_matches_its_pyproject` (parametrized), `::test_stale_pyproject_is_reported_with_the_project_to_relock` |
| AC8 | Existing behavior preserved | Pass | Unit 561 passed, BDD 58 passed / 1 pre-existing skip, Blender 125 passed; SCN008 imports both MCP servers through `uv run --project`; `scripts/ship-smoke.sh` exit 0 |
| AC9 | Coexistence suite checks the loaded state | Pass | `tests/blender/test_coexistence.py` asserts the second value of `addon_utils.check()`; both previously failing tests pass with blender-mcp installed in Blender 5.2.3 |
| AC10 | Steering lists only gates that can run | Pass | `gate-skill-schema` and `gate-markdown-lint` rows and the `markdownlint` standards line removed from `steering/snippets/project-tech.md`; `validate-skills.py` line removed from `steering/snippets/project-structure.md`; no other references remain outside `specs/` |
| AC11 | Changelog guard survives later releases | Pass | `tests/unit/onboard/test_docs_and_skill.py::test_changelog_has_both_unreleased_entries_ending_with_issue` searches every section for the `(#7)` entries; passes with the 0.14.1 section above 0.14.0 |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Propagate Blender test failures from the gate | Complete | shellcheck clean |
| T002 | Resolve the re-import entry from `CLAUDE_PLUGIN_ROOT`, then the checkout | Complete | |
| T003 | Keychain-profile notarization and the password-path warning | Complete | `required_env` updated; frontmatter accepted by `claude plugin validate .` and `tests/unit/ship/test_skill.py` |
| T004 | Derive the package version from `VERSION` and relock | Complete | |
| T005 | Lockfile drift test | Complete | |
| T006 | Regression tests | Complete | |
| T007 | BDD scenarios | Complete | `tests/bdd/features/release_tooling_fixes.feature` |
| T008 | Coexistence loaded-state assertion | Complete | |
| T009 | Remove unrunnable gates from steering | Complete | |
| T010 | Changelog guard finds its section after later releases | Complete | |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | `entry_script()` isolates entry resolution from `run_isolated`; `_required()` isolates the profile rule from `preflight_env` |
| Open/Closed | 5 | Notarization adds a branch without changing the password path's argv |
| Liskov Substitution | 5 | N/A to these changes |
| Interface Segregation | 5 | `run-blender-tests.sh` gains an optional target argument; the no-argument call is unchanged |
| Dependency Inversion | 4 | Entry resolution reads `os.environ` directly; acceptable for an add-on entry point and patched in tests |

### Layer Separation

Changes stay within their layers: the Blender add-on (`contract_core`), shell tooling (`scripts/`), the ship package (`src/nmg_game_dev/ship`), and steering. No cross-layer imports were added.

### Dependency Flow

Unchanged. The sub-project locks now resolve against the current root dependencies.

---

## Security Assessment

- [x] Authentication: the keychain-profile path keeps the Apple ID and app-specific password out of process arguments (AC4)
- [x] Authorization: N/A
- [x] Input validation: the profile name is quoted as a single argv element
- [x] Injection prevention: all commands are built as bash arrays; no `eval`
- [x] Data protection: the password path keeps its masked log and now warns about argv visibility (AC5); tests assert the password never reaches stdout or stderr

---

## Performance Assessment

- [x] Async patterns: N/A
- [x] Caching: `[tool.uv] cache-keys` rebuilds the editable install only when `pyproject.toml` or `VERSION` changes
- [x] Resource management: `_runner.py` flushes before `os._exit`, so no output is lost
- [x] Query optimization: N/A. The lock tests shell out to `uv lock --check --offline` per project (a few seconds); acceptable

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | SCN001 | Yes | Yes |
| AC2 | SCN002 (Blender test) | Yes | Yes |
| AC3 | SCN003 (Blender test) | Yes | Yes |
| AC4 | SCN004 | Yes | Yes |
| AC5 | SCN005 | Yes | Yes |
| AC6 | SCN006 | Yes | Yes |
| AC7 | SCN007 | Yes | Yes |
| AC8 | SCN008 | Yes | Yes |
| AC9 | SCN009 (Blender test) | Yes | Yes |
| AC10 | Steering-only change | N/A | Checked by inspection and grep |
| AC11 | Unit test | N/A | Yes |

### Coverage Summary

- Feature files: 6 bound scenarios in `release_tooling_fixes.feature`; SCN002, SCN003 and SCN009 run in headless Blender
- Step definitions: Implemented
- Unit tests: 561 passed (19 new)
- Blender tests: 125 passed

---

## Steering Doc Verification Gates

Registered validations (`.nmg-sdlc/verification/95.json`, head `eb78418ca69459ba593c0309188073078b6046c5`, coverage 5/5 complete):

| Gate | Status | Evidence |
|------|--------|----------|
| `repository.tests` | Pass | `uv run pytest tests/unit tests/bdd -q`: 616 passed, 4 skipped |
| `repository.lint` | Pass | `uv run ruff check .` |
| `repository.types` | Pass | `uv run mypy src tests` |
| `plugin.validate` | Pass | `claude plugin validate .` |
| `plugin.session-smoke` | Pass | blender MCP connected |

Steering gates (`steering/snippets/project-tech.md` § Verification Gates):

| Gate | Status | Evidence |
|------|--------|----------|
| `gate-python-lint` | Pass | `ruff check .` all checks passed; `ruff format --check .` 246 files formatted |
| `gate-python-types` | Pass | `mypy src/ tests/`: no issues in 147 source files |
| `gate-python-unit` | Pass | `pytest tests/unit tests/bdd` (registered): 616 passed, 4 skipped |
| `gate-python-bdd` | Pass | Included in the registered run above |
| `gate-blender-headless` | Pass | `scripts/run-blender-tests.sh` with Blender 5.2.3 at `eb2d273`: 125 passed, exit 0 (`eb78418` changes only a unit test and the spec) |
| `gate-mcp-schema` | Pass | `scripts/validate-mcp-tools.py` exit 0 |
| `gate-shellcheck` | Pass | `shellcheck -S style scripts/*.sh` exit 0 |
| `gate-ship-smoke` | Pass | `scripts/ship-smoke.sh` exit 0 |
| `gate-ue-automation` | N/A | No UE C++ changed |

**Gate Summary**: 8/8 applicable gates passed, 0 failed, 0 incomplete

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| High | Testing | `tests/blender/test_coexistence.py` | Asserted `loaded_default` from `addon_utils.check()`, which is always False under `default_set=False` | Assert `loaded_state` (spec amendment AC9, T008) | `direct` |
| Medium | Steering | `steering/snippets/project-tech.md`, `project-structure.md` | `gate-skill-schema` and `gate-markdown-lint` named a script and a tool that do not exist | Removed (spec amendment AC10, T009) | `direct` |
| High | Testing | `tests/unit/onboard/test_docs_and_skill.py` | Changelog guard looked only in `[Unreleased]` and the first release, so the 0.14.1 bump failed `repository.tests` at `eb2d273` | Search every section (spec amendment AC11, T010) | `direct` |

## Remaining Issues

### Low Priority

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `tests/lock_fakes.py`, `tests/release_fakes.py` |
| **Issue** | Test helper modules not named in the tasks' file lists |
| **Impact** | None; they are shared helpers for the T005–T007 tests |
| **Reason Not Fixed** | Not a defect |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Architecture |
| **Location** | `skills/*/SKILL.md` |
| **Issue** | Frontmatter is not strict YAML (`?` suffixes in flow lists, colons in values), on `main` as well as this branch |
| **Impact** | None today. Claude Code and the project's line-based reader accept it; a future strict-YAML validator would reject it |
| **Reason Not Fixed** | Pre-existing; out of scope |

---

## Positive Observations

- The worker found that Blender 5.2 already returned 1 for failing tests through `SystemExit`. It kept the `os._exit` path anyway, so the exact pytest code reaches the shell on any Blender build, and `--python-exit-code 1` covers runner crashes that previously exited 0.
- Deriving the version dynamically removes lock churn from every release bump instead of relocking on each bump.
- Real-Blender regression tests run the gate itself against failing, erroring and passing suites.

---

## Recommendations Summary

### Before PR (Must)

- None

### Short Term (Should)

- None

### Long Term (Could)

- Revisit a skill-schema check if skill frontmatter gets a strict format.

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `scripts/run-blender-tests.sh` | 0 | |
| `tests/blender/_runner.py` | 0 | |
| `plugins/nmg-game-dev-blender-addon/contract_core/reimport.py` | 0 | |
| `scripts/notarize-macos.sh` | 0 | |
| `src/nmg_game_dev/ship/targets.py` | 0 | |
| `skills/ship/SKILL.md`, `docs/skills/ship.md` | 0 | |
| `pyproject.toml`, `uv.lock`, `mcp-servers/*/uv.lock` | 0 | |
| `steering/snippets/project-tech.md`, `project-structure.md` | 0 | |
| `tests/blender/test_coexistence.py` | 0 | |
| `tests/unit/onboard/test_docs_and_skill.py` | 0 | |
| `VERSION`, `CHANGELOG.md`, `.claude-plugin/plugin.json`, add-on and UE plugin manifests | 0 | 0.14.1 release bump |
| `tests/unit/*`, `tests/bdd/*`, `tests/blender/test_reimport_entry.py`, `tests/*_fakes.py` | 1 | Low: helpers not listed in tasks |

---

## Recommendation

**Ready for PR**

All acceptance criteria pass, all registered validations and applicable steering gates are green at the verification head, and no remaining issue blocks merge.
