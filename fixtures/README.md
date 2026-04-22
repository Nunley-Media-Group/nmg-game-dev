# THIS-REPO-ONLY — fixtures MUST NOT ship to consumers

This directory contains test fixtures used by `nmg-game-dev` contributors for local
smoke-testing of the launcher scripts and pipeline tooling.

**These files are NOT consumer-facing and MUST NOT be copied to a consumer game project
by `onboard-consumer` or any other distribution mechanism.**

See `specs/feature-scaffold-plugin-repo-session-start-hooks/requirements.md` § AC10
(no-leak requirement) for the full rationale.

## Contents

| File | Purpose |
|------|---------|
| `dogfood.uproject` | Minimal UE 5.7 project stub — gives `scripts/start-unreal-mcp.sh` a valid target when invoked from this repo without a consumer project present. The `NmgGameDevMCP` port-bind (issue #3) is not yet enabled in this fixture. |

## Adding new fixtures

New fixtures belong here when they are:

- Used only inside `nmg-game-dev` development/testing workflows.
- Not part of a consumer game project's expected directory structure.

Consumer-facing templates belong in `templates/consumer/` instead.
