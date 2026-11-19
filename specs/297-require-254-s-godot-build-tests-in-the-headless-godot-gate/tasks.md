# Tasks: Require #254's Godot build tests in the headless Godot gate

**Issue**: #297
**Date**: 2026-11-19
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/254-version-each-game-build-in-ship-show-the-version-in-game-and-require-a-player-changelog-entry/

## Implementation Tasks

### T001: Require the build tests in the gate

**File(s)**: `scripts/run-godot-tests.sh`
**Type**: Modify
**Depends**: none
**Acceptance**:
- FR1, AC1: `required_tests` lists `test_nmg_build.gd::` plus each of the six `func test_*` names in `test_nmg_build.gd`.
- The header comment's list of required tests includes the NmgBuild tests.
- The script stays shellcheck-clean (`gate-shellcheck`).

### T002: Teach the fake godot the build tests and add the guards

**File(s)**: `tests/unit/test_run_godot_tests.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- FR3: the fake `godot`'s `required` list prints PASS lines for the six build tests, so the existing pass-path tests still pass.
- AC2: a `tests_missing_build` mode drops one build test; it joins the `test_addon_test_failure_exits_5` cases, and a test asserts that stderr names the dropped `test_nmg_build.gd::<name>`.
- FR2, AC1: a test parses `required_tests=( … )` from the script and `^func (test_\w+)` from `test_nmg_build.gd`, and fails when any build test is not listed.
- Evidence: `uv run pytest tests/unit tests/bdd -q` (`repository.tests`).

### T003: BDD scenarios for the required build tests

**File(s)**: `tests/bdd/features/godot_gate_required_tests.feature`, `tests/bdd/test_godot_gate_required_tests_bdd.py`
**Type**: Create
**Depends**: T002
**Acceptance**:
- One pytest-bdd scenario per AC1 and AC2, matching this spec's `feature.gherkin`. AC2 runs `scripts/run-godot-tests.sh` against the fake `godot` harness from `tests/unit/test_run_godot_tests.py`.
- Evidence: `uv run pytest tests/unit tests/bdd -q` (`repository.tests`).

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #297 | 2026-11-19 | Initial feature tasks |
