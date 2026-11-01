# Design: Register the project verification gates and a UE compile extension in steering

**Issue**: #123
**Date**: 2026-11-01
**Status**: Approved
**Author**: Rich Nunley

## Overview

All changes live under `steering/`. The manifest gains six `validations` entries and one `extensions` entry. Five validations use `builtin.command`; `gate-ue-compile` uses the new `project.ue-compile` provider, following the shape of the existing `steering/extensions/plugin-session-smoke.mjs`.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| `steering/manifest.json` `validations[]` | — | `repository.format`, `gate-blender-headless`, `gate-ue-compile`, `gate-mcp-schema`, `gate-shellcheck`, `gate-ship-smoke` | Required; `changed_paths` includes as in the tech table (`always` for `repository.format`); `gate-blender-headless` forwards only `BLENDER_APP` and `BLENDER_BIN` |
| `steering/manifest.json` `extensions[]` | — | `{ id: "project.ue-compile", path: "steering/extensions/ue-compile.mjs", providers: ["project.ue-compile"] }` | Registers the provider |
| `project.ue-compile` provider | `{ projectRoot, config: { project, target }, identity, signal }` | `{ schemaVersion: 1, status, summary, identity, evidence }` | `incomplete` off macOS, without `$UE_ROOT`/default `Build.sh`, or without the project; otherwise runs `Build.sh <target> Mac Development -Project=<abs> -WaitMutex`; exit 0 → `passed`, else `failed` with up to 60 error/fatal lines; honors cancellation |

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Register `gate-ue-automation` running `scripts/run-ue-tests.sh` | Rejected | It writes reports into tracked `tests/ue-automation/` files and dirties the tree mid-verification |
| `builtin.command` running `Build.sh` directly | Rejected | `Build.sh` changes directory, needs an absolute project path, and the UE root is host-specific |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #123 | 2026-11-01 | Initial feature design |
