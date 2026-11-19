# Design: Require #254's Godot build tests in the headless Godot gate

**Issue**: #297
**Date**: 2026-11-19
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/254-version-each-game-build-in-ship-show-the-version-in-game-and-require-a-player-changelog-entry/

## Overview

Append the six `test_nmg_build.gd::<name>` entries to the `required_tests` array in `scripts/run-godot-tests.sh`. The existing loop (`grep -qxF "PASS $test"`, `die 5 … "add-on tests failed: no PASS line for $test"`) already gives AC2's behaviour, so the script's logic does not change. Tests prove both ACs: a static check that parses the array and the GDScript file, and a fake-`godot` mode that omits one build test.

## Architecture

```
scripts/run-godot-tests.sh
  required_tests=( …existing 18… + 6 × "test_nmg_build.gd::test_version_*" )
  step 2: run_tests.gd output ─► for test in required_tests: grep "PASS $test" || die 5

tests/unit/test_run_godot_tests.py
  fake godot ─► prints PASS for its `required` list (+ 6 build tests)
              ─► mode "tests_missing_build" drops one build test
  test_required_tests_list_every_build_test ─► parse `required_tests=( … )` from the script
                                             ─► parse `^func (test_\w+)` from test_nmg_build.gd
                                             ─► assert every build test is listed
```

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `scripts/run-godot-tests.sh` `required_tests` | — | exit 5, `add-on tests failed: no PASS line for test_nmg_build.gd::<name>` | Six new entries; loop unchanged |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| List the six tests by name | Selected | Matches how every other required test is listed; a rename then fails the gate as the issue asks |
| Derive `required_tests` from the `test_*` files at run time | Rejected | A deleted test would vanish from both the file and the derived list, so deletions would pass |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #297 | 2026-11-19 | Initial feature design |
