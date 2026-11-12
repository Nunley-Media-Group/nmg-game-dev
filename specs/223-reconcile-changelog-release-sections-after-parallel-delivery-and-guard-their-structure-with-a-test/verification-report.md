# Verification Report: CHANGELOG release sections are duplicated, empty and out of order after parallel delivery

**Date**: 2026-11-12
**Issue**: #223
**Reviewer**: Claude (nmg-sdlc architecture-reviewer, verify stage)
**Scope**: Implementation verification against spec

**Verification head**: 6f3d4f1acb02b03975f72efab653fb430b61b4f9

---

## Executive Summary

| Category | Score (1-5) |
|----------|-------------|
| Spec Compliance | 5 |
| Architecture (SOLID) | 5 |
| Security | 5 |
| Performance | 5 |
| Testability | 5 |
| Error Handling | 4 |
| **Overall** | 4.8 |

### Implementation Status: Pass
**Total Issues**: 0 blocking (2 low-priority observations)

The damaged `0.21.2`–`0.25.0` region of `CHANGELOG.md` matches the design's Fix Strategy content byte-for-byte. Every bullet from commit `353e275` is kept, and the header, `## [Unreleased]`, and `[0.21.1]` and older are unchanged. The new `tests/unit/test_changelog_structure.py` guards the release structure. All 11 registered validations recorded a terminal result at the verification head, and every applicable one passed.

---

## Issue Scope

- Active issue: #223
- Spec: `specs/223-reconcile-changelog-release-sections-after-parallel-delivery-and-guard-their-structure-with-a-test`
- Manifest: `implicit single issue`
- Resolver status: `implicit_single_issue`
- Delivery: AC [AC1, AC2, AC3, AC4]; FR [FR1, FR2, FR3]; tasks [T001, T002]; scenarios [SCN001, SCN002, SCN003, SCN004]
- Regression: AC []; FR []; scenarios []

<!-- nmg-sdlc-issue-scope: {"issueNumber":223,"specPath":"specs/223-reconcile-changelog-release-sections-after-parallel-delivery-and-guard-their-structure-with-a-test","status":"implicit_single_issue","delivery":{"acceptanceCriteria":["AC1","AC2","AC3","AC4"],"functionalRequirements":["FR1","FR2","FR3"],"tasks":["T001","T002"],"scenarios":["SCN001","SCN002","SCN003","SCN004"]},"regression":{"acceptanceCriteria":[],"functionalRequirements":[],"scenarios":[]}} -->

## Delivery Validation

- Local verification: Pass
- PR evidence: Not required

---

## Deterministic Steering Artifact and Ceiling

- Runner: `sdlc-verify-steering.mjs --project . --issue 223 --spec specs/223-… --base main --controller-run-id adeab1b6-8c7a-47f4-9d5c-92111ba707cd`
- Artifact: `.nmg-sdlc/verification/223.json`, identity head `6f3d4f1acb02b03975f72efab653fb430b61b4f9`, tree clean
- Coverage: declared 11, recorded 11, complete `true`; missing, duplicate and unknown are all empty
- Ceiling: none (`ok: true`)

The local `main` ref is behind `origin/main` (`41c5b31` against `1cb5717`), and the runner diffs against `main`. As a result it saw 444 changed paths, and the Blender, UE compile, MCP schema, shellcheck and plugin gates applied, although the change itself touches only `CHANGELOG.md`, version files, the spec and one test. Every one of those gates ran and passed, so the wider scope only made verification stricter.

---

## Acceptance Criteria Verification

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC1 | Each released version appears once, newest first, after `## [Unreleased]`; the first release equals `VERSION` | Pass | `CHANGELOG.md` headings at HEAD: `[Unreleased]`, `0.25.1`, `0.25.0`, `0.24.0`, `0.23.0`, `0.22.0`, `0.21.5`, `0.21.4`, `0.21.3`, `0.21.2`, `0.21.1`, … `VERSION` = `0.25.1` (the version-prep commit `6f3d4f1` added the `0.25.1` section and bumped `VERSION` together). `test_checked_in_changelog_passes_the_structure_rules` passes at HEAD |
| AC2 | No empty release sections | Pass | `changelog_problems` returns `[]` for the checked-in file; every release section has a `- ` bullet |
| AC3 | No entry is lost; 30 references each in exactly one bullet | Pass | `diff <(git show 353e275:CHANGELOG.md \| grep '^- ' \| sort) <(git show 15701ba:CHANGELOG.md \| grep '^- ' \| sort)` is empty at the reconciliation commit. At HEAD the only extra bullet is the `0.25.1` version-prep entry for #223, which the reconciliation did not add. `test_each_reconciled_reference_appears_in_exactly_one_bullet` passes (133–155, 189, 193, 202, 203, 204, 211, 215 = 30 references) |
| AC4 | The structure is enforced by a test | Pass | `tests/unit/test_changelog_structure.py::test_checker_rejects_a_broken_changelog`, parametrized over `duplicate-version`, `ascending-pair`, `empty-section` and `newest-differs-from-version`, all pass. Run against the damaged `353e275` changelog, the checker reports 5 problems (two ordering breaks, a duplicate `0.22.0`, and two empty sections) |

### Functional Requirements

| FR | Status | Evidence |
|----|--------|----------|
| FR1 | Pass | The region from `## [0.25.0]` down to `## [0.21.1]` at `15701ba` is byte-identical to the design's Fix Strategy block (`diff` empty). Placement was checked independently against `git log --first-parent 353e275` with `VERSION` at each merge. Every bullet sits under the version main carried right after its PR merged (for example, #154 went to 0.25.0 via PR #222; #138, #139, #149, #204 and #215 went to 0.24.0; #140, #135, #145, #134 and #150 went to 0.21.2) |
| FR2 | Pass | The header plus `[Unreleased]` and everything from `[0.21.1]` down are identical between `353e275` and `15701ba`. The version-prep commit `6f3d4f1` adds only the new `0.25.1` section above `0.25.0` and changes nothing below it |
| FR3 | Pass | `changelog_problems(text, version)` checks that `[Unreleased]` comes first, that headings match the regex, and that releases are unique, strictly descending (integer tuples), non-empty, and that the newest equals `VERSION` |

---

## Task Completion

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| T001 | Reconcile the 0.21.2–0.25.0 CHANGELOG region | Complete | Exact match with design; bullet-set diff empty at `15701ba` |
| T002 | Add the CHANGELOG structure test | Complete | 6 tests pass; part of `repository.tests` (1722 passed, 14 skipped) |

---

## Architecture Assessment

### SOLID Compliance

| Principle | Score (1-5) | Notes |
|-----------|-------------|-------|
| Single Responsibility | 5 | `_sections` splits the file into sections, `changelog_problems` applies the rules, and the tests feed it input |
| Open/Closed | 5 | Each rule is a separate check that adds a message, so new rules append without changing existing ones |
| Liskov Substitution | 5 | N/A (no type hierarchy) |
| Interface Segregation | 5 | One pure function taking `(text, version)` and returning a list of problems |
| Dependency Inversion | 5 | The checker is pure and does no I/O; only the test functions read files |

### Layer Separation

Test-only change plus documentation data. No production module, skill, MCP server, or Blender/UE code changes.

### Dependency Flow

Standard library plus `pytest` only. The test resolves the repository root from `__file__`, so it does not depend on the working directory.

---

## Security Assessment

- [x] Authentication: N/A
- [x] Authorization: N/A
- [x] Input validation: the regex is anchored, and headings that do not match are reported, not ignored
- [x] Injection prevention: no subprocess or shell use
- [x] Data protection: no secrets touched

## Performance Assessment

- [x] Async patterns: N/A
- [x] Caching: N/A
- [x] Resource management: one file read per test; the module runs in about 0.04 s
- [x] Query optimization: single linear pass

## Testability

Pure checker with synthetic negative fixtures and a real-file positive check. The checker also rejects the actual damaged changelog from `353e275`, which shows the guard catches the original defect.

## Error Handling

The checker never raises on malformed input. It returns a readable message for each broken rule, and the assertion shows the full list. Score 4 because of the two low-priority observations below, neither of which can occur in the current file.

---

## Test Coverage

### BDD Scenarios

| Acceptance Criterion | Has Scenario | Has Steps | Passes |
|---------------------|-------------|-----------|--------|
| AC1 | Yes (SCN001) | Yes (`test_checked_in_changelog_passes_the_structure_rules`) | Yes |
| AC2 | Yes (SCN002) | Yes (`test_checked_in_changelog_passes_the_structure_rules`) | Yes |
| AC3 | Yes (SCN003) | Yes (`test_each_reconciled_reference_appears_in_exactly_one_bullet`; sorted-bullet diff checked by this verification) | Yes |
| AC4 | Yes (SCN004) | Yes (`test_checker_rejects_a_broken_changelog` ×4) | Yes |

### Coverage Summary

- Feature files: 4 scenarios (`feature.gherkin` declares `tests/unit/test_changelog_structure.py` as its implementation)
- Step definitions: Implemented as unit tests, per the design
- Unit tests: 6 new tests; full suite 1722 passed, 14 skipped
- Integration tests: N/A

---

## Exercise Test Results

| Field | Value |
|-------|-------|
| **Reason** | Not applicable: the change touches no nmg-sdlc `workflows/` or `agents/` files and no skill in this repository |
| **Recommendation** | None |

---

## Steering Doc Verification Gates

| Gate | Status | Evidence |
|------|--------|----------|
| repository.tests | Pass | `uv run pytest tests/unit tests/bdd -q`: 1722 passed, 14 skipped |
| repository.lint | Pass | `uv run ruff check .` exited 0 |
| repository.format | Pass | `uv run ruff format --check .` exited 0 |
| repository.types | Pass | `uv run mypy src tests` exited 0 |
| gate-blender-headless | Pass | `scripts/run-blender-tests.sh`: 382 passed, 4 skipped |
| gate-ue-compile | Pass | DogfoodEditor compiled against UE 5.8 (`-NoUBA`) |
| gate-mcp-schema | Pass | `scripts/validate-mcp-tools.py` exited 0 |
| gate-shellcheck | Pass | exited 0 |
| gate-ship-smoke | Not applicable | No path in the changed-path set matches |
| plugin.validate | Pass | `claude plugin validate .` exited 0 |
| plugin.session-smoke | Pass | Plugin loaded via `--plugin-dir`; `nmg-game-dev:blender` connected |

**Gate Summary**: 10/10 applicable gates passed, 0 failed, 0 incomplete (1 not applicable). No `nmg-sdlc-smoke` validation is declared in `steering/manifest.json`.

The first run of the gate recorded `gate-ue-compile` as failed: `Unable to find plugin 'VibeUE' (referenced via dogfood.uproject)`. The cause was a missing host prerequisite in this worktree. The tech steering requires VibeUE in `fixtures/Plugins/` from `scripts/install-vibeue.sh`, and that directory is gitignored. Running `scripts/install-vibeue.sh` installed it without touching any tracked file. The full registered gate was then rerun at the same head, and every applicable gate passed (results above).

---

## Fixes Applied

| Severity | Category | Location | Original Issue | Fix Applied | Routing |
|----------|----------|----------|----------------|-------------|---------|
| — | Environment | `fixtures/Plugins/VibeUE` (gitignored) | `gate-ue-compile` prerequisite missing in this worktree | Ran `scripts/install-vibeue.sh`; no source change | direct |

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
| **Category** | Error Handling |
| **Location** | `tests/unit/test_changelog_structure.py` (`_sections`) |
| **Issue** | A line starting with `## ` inside a fenced code block, or CRLF line endings, would be read as a heading or fail the regex |
| **Impact** | None today: `CHANGELOG.md` has no fenced `## ` lines and uses LF |
| **Reason Not Fixed** | Outside the approved design; it would also be outside the verify publication scope |

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Testing |
| **Location** | `tests/unit/test_changelog_structure.py` (`_RECONCILED_REFERENCES`) |
| **Issue** | The 30-reference uniqueness check is a fixed historical list, so a later edit could duplicate a newer reference without failing this test |
| **Impact** | Minimal: the spec scopes AC3 to those 30 references |
| **Reason Not Fixed** | Matches the approved design |

---

## Positive Observations

- The reconciliation content is copied exactly from the design, which keeps the T001 bullet diff mechanical.
- The checker is pure and returns all problems at once, so a failure explains every broken rule together.
- The guard rejects the real damaged changelog, not only synthetic cases.

---

## Recommendations Summary

### Before PR (Must)
- [x] None

### Short Term (Should)
- [ ] Refresh the local `main` ref in the primary checkout so verification diffs against the current default branch

### Long Term (Could)
- [ ] Have version preparation run the structure checker before it writes a CHANGELOG section

---

## Files Reviewed

| File | Issues | Notes |
|------|--------|-------|
| `CHANGELOG.md` | 0 | Region exact; header and tail unchanged |
| `tests/unit/test_changelog_structure.py` | 0 blocking | Two low observations |
| `VERSION`, `.claude-plugin/plugin.json`, `blender_manifest.toml`, `nmg-game-dev.uplugin` | 0 | Version prep bumped all four to 0.25.1 consistently |

---

## Recommendation

**Ready for PR**

Every delivery AC, FR, task and scenario has local evidence at the verification head. All 11 registered validations recorded a terminal result, and every applicable one passed.
