# Defect Report: The scaffold launcher detach scenarios fail on a loaded host because they time the launcher instead of checking that it detached

**Issue**: #215
**Date**: 2026-11-12
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/1-scaffold-plugin-repo-session-start-hooks/

## Reproduction

1. Load the host until `scripts/start-blender-mcp.sh` or `scripts/start-unreal-mcp.sh` takes more than 2 s to return, for example with a load average far above the core count.
2. Run `uv run pytest tests/bdd -q -k "launcher_detaches"`.
3. `test_blender_launcher_detaches` or `test_unreal_launcher_detaches` fails with `Script took 2.1s (> 2s)`, although the launcher detached its child and exited 0.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | The detach scenarios pass whenever the launcher exits 0 while the process it started is still running, however long the host takes, and they fail for a launcher that waits on its child. |
| **Actual** | The scenarios assert that the whole launcher run took under 2.0 s of wall-clock time, so host load fails them and blocks unrelated gate runs. |

## Acceptance Criteria

### AC1: Detach is judged structurally

**Given** the fake Blender / fake UE editor used by the scenarios, which keeps running until told to stop
**When** the launcher script exits
**Then** the scenario passes only if the script exited with status 0 while the fake child it started is still alive (and the child's recorded argv matches as today)

### AC2: A blocking launcher still fails

**Given** a launcher variant that waits for its child to exit before returning
**When** the scenario runs it
**Then** the scenario fails (the script does not exit while the child is alive, within a generous bound such as 30 s)

### AC3: Host load does not fail the scenarios

**Given** a host where the launcher takes longer than 2 s to return because of CPU load
**When** the detach scenarios run
**Then** they pass as long as AC1 holds

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Replace the `< 2.0 s` wall-clock assertions with a check that the script exited 0 while its fake child process is still running; keep a generous overall timeout (≥ 30 s) only to stop a hung run | Must |
| FR2 | The fake Blender / UE editors record their PID so the test can confirm the child is alive after the script exits, and the test stops the child afterwards | Must |
| FR3 | A unit/BDD test proves a blocking launcher variant fails the detach check | Must |

## Out of Scope

- Changing `scripts/start-blender-mcp.sh` or `scripts/start-unreal-mcp.sh`.
- The idempotency, remediation, and other scaffold scenarios beyond the shared run helper.
- Running real Blender or a real Unreal Editor in tests.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #215 | 2026-11-12 | Initial defect report |
