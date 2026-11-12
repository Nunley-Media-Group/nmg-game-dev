# Defect Report: The launcher detach scenarios no longer enforce the two-second return bound

**Issue**: #226
**Date**: 2026-11-12
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/215-judge-launcher-detach-in-the-scaffold-scenarios-by-process-state-not-a-2-second-wall-clock/

## Reproduction

1. Write a launcher that sleeps 2.5 s, then starts a long-lived child with `nohup … &` and `disown`, then exits 0.
2. Run it through `_run_launcher` and `assert_detached` in `tests/bdd/steps/test_scaffold.py`. The scenario "A slow launcher that detaches still passes the detach check (AC3)" does exactly this.
3. `assert_detached` passes, so a launcher that takes 2.5 s to return control to the shell satisfies the detach scenarios for `scripts/start-blender-mcp.sh` and `scripts/start-unreal-mcp.sh`.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | A launcher detach check passes only when the launcher exits 0 in under two seconds and the fake child it started is still alive. A launcher that needs 2.5 s fails. |
| **Actual** | The check has no time bound. It passes any launcher that exits 0 within the 30 s run bound while its child is alive, and a scenario asserts that a 2.5 s launcher passes. |

## Acceptance Criteria

### AC1: The two-second bound is restored

**Given** the Blender and Unreal launcher detach scenarios, each running its launcher against the long-lived fake child
**When** the launcher runs
**Then** the scenario passes only if the script exits 0 in under two seconds and the fake child it started is still alive

### AC2: Slow launchers fail

**Given** a synthetic launcher that sleeps 2.5 s before it detaches its fake child
**When** the detach check runs on it
**Then** the check fails because the launcher took longer than two seconds to return, although its child is still alive

### AC3: Blocking launchers still fail

**Given** the synthetic launcher that starts its fake child and waits for it
**When** it runs with a child that exits after 1 second, and again with a child that keeps running under a 3 second bound
**Then** the detach check fails the first run because the child is gone, and the second because the launcher did not return

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `assert_detached` fails unless the launcher's elapsed run time is under 2.0 s and its fake child is alive. Both detach scenarios carry the step "the script returns control to the shell in under two seconds" next to the child-alive step. | Must |
| FR2 | The scenario "A slow launcher that detaches still passes the detach check" is replaced by one that shows a 2.5 s launcher fails the detach check | Must |
| FR3 | The fake child's PID recording and its teardown from #215 stay as they are | Must |

## Out of Scope

- Changing `scripts/start-blender-mcp.sh` or `scripts/start-unreal-mcp.sh`.
- Any allowance in the tests for an overloaded host.
- The idempotency, remediation, and other scaffold scenarios beyond the shared run helper.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #226 | 2026-11-12 | Initial defect report |
