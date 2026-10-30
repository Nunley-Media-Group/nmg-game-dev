# Tasks: Upgrade toolchain to UE 5.8 with native MCP plus VibeUE, and Blender 5.2 MCP

**Issue**: #68
**Date**: 2026-10-30
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs/

## Implementation Tasks

### T001: Dogfood fixture on UE 5.8 with the MCP plugins

**File(s)**: `fixtures/dogfood.uproject`, `fixtures/Config/DefaultEditorPerProjectUserSettings.ini`, `fixtures/Config/DefaultEngine.ini`, `fixtures/Config/DefaultInput.ini`, `fixtures/Source/**`, `.gitignore`, `plugins/nmg-game-dev-ue-plugin/nmg-game-dev.uplugin`, `fixtures/README.md`
**Type**: Modify | Create
**Depends**: none
**Acceptance**:
- The uproject, INI, uplugin, and `.gitignore` match design § Data / Storage Changes; fixture `Source/` and `Config/` are tracked and `fixtures/Plugins/` is ignored (AC1, AC2)
- `fixtures/README.md` describes the 5.8 fixture, its plugins, and `scripts/install-vibeue.sh`

### T002: Unreal launcher, test runner, and VibeUE installer

**File(s)**: `scripts/start-unreal-mcp.sh`, `scripts/run-ue-tests.sh`, `scripts/install-vibeue.sh`
**Type**: Modify | Create
**Depends**: T001
**Acceptance**:
- `start-unreal-mcp.sh` defaults `UE_ROOT` to `/Users/Shared/Epic Games/UE_5.8` and `UE_MCP_PORT` to 8000, and launches with `-ModelContextProtocolStartServer -ModelContextProtocolPort=$PORT`, keeping the idempotent, detached, and actionable-failure behavior (AC1, AC2)
- `run-ue-tests.sh` defaults and messages name UE 5.8 (AC1)
- `install-vibeue.sh` clones VibeUE's default branch with `--depth 1` or fast-forwards an existing clone, with no tag or commit pin, and prints the commit (AC2, AC6)
- All three are shellcheck-clean with `set -euo pipefail`

### T003: Blender MCP on the latest release

**File(s)**: `.mcp.json`, `scripts/start-blender-mcp.sh`, `scripts/install-blender-mcp-addon.sh`
**Type**: Modify | Create
**Depends**: none
**Acceptance**:
- `.mcp.json` `blender` and `unreal` entries match design § Data / Storage Changes, and `meshy` is byte-for-byte unchanged (AC3, AC5, AC6)
- `start-blender-mcp.sh` uses the design candidate order (AC5)
- `install-blender-mcp-addon.sh` runs `uvx mcp-for-blender@latest install-addon`, forwarding `BLENDER_USER_ADDONS`, and exits 2 with a remediation when `uvx` is missing (AC5, AC6)

### T004: Smoke scripts and fixture FBX

**File(s)**: `scripts/smoke-unreal-mcp.py`, `scripts/smoke-blender-mcp.py`, `fixtures/smoke/SM_SmokeCube.fbx`
**Type**: Create
**Depends**: T002, T003
**Acceptance**:
- `smoke-unreal-mcp.py` performs design § Unreal smoke steps with the documented exit codes, messages, and cleanup (AC4)
- `smoke-blender-mcp.py` performs design § Blender smoke steps with the documented exit codes (AC5)
- Both are stdlib-only, typed, and ruff-clean; `SM_SmokeCube.fbx` is a 1 m cube exported from headless Blender

### T005: Remaining 5.8 / native-endpoint references

**File(s)**: `src/nmg_game_dev/pipeline/stages/_mcp.py`, `src/nmg_game_dev/pipeline/stages/_base.py`, `src/nmg_game_dev/pipeline/stages/import_ue.py`, `tests/e2e/test_pipeline_e2e.py`
**Type**: Modify
**Depends**: T002
**Acceptance**:
- The Unreal remediation and docstrings name Epic's Unreal MCP with VibeUE and `scripts/start-unreal-mcp.sh`; the e2e docstring says `UE_MCP_PORT` defaults to 8000 (AC1, AC3)

### T006: Docs, steering, and changelog

**File(s)**: `docs/mcp/unreal.md`, `docs/mcp/blender.md`, `steering/snippets/project-tech.md`, `README.md`, `CHANGELOG.md`
**Type**: Create | Modify
**Depends**: T004
**Acceptance**:
- The two MCP docs and the steering tech snippet cover everything in AC7. The steering stack table names UE 5.8, latest Blender, `mcp-for-blender`, and the native endpoint; the session-start table says port 8000; the Security "Third-party MCP trust" row says third-party tools track latest releases verified by the smoke scripts (AC7)
- `README.md` requirements list Unreal MCP + Editor Tools + VibeUE and `uv`, without Node.js (AC7)
- `CHANGELOG.md` `[Unreleased]` gets a bullet ending with `(#68)`

### T007: Guard and BDD tests

**File(s)**: `tests/_scaffold_contract.py`, `tests/unit/test_scaffold_guards.py`, `tests/unit/test_toolchain_guards.py`, `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature`, `tests/bdd/features/ue_plugin_skeleton.feature`, `tests/bdd/steps/test_scaffold.py`, `tests/bdd/**`
**Type**: Modify | Create
**Depends**: T003, T005
**Acceptance**:
- `test_mcp_json_no_floating_versions` is replaced by guards that the `unreal` entry is `type: http` at `UNREAL_MCP_URL`, `.mcp.json` has no `mcp-remote`, `8088`, or bridge wording (AC3), and the `blender` and `unreal` entries carry no version constraints with `blender` using `mcp-for-blender@latest` and the telemetry env (AC5, AC6)
- `test_toolchain_guards.py` asserts the uproject/uplugin/script 5.8 values, the four enabled fixture plugins and INI, the launcher flags, no `UE_5.7`/`5.7.0`/`Unreal Engine 5.7` outside `specs/` and `CHANGELOG.md` (AC1, AC2), and that `install-vibeue.sh` and `install-blender-mcp-addon.sh` contain no tag, commit, or version pin (AC6)
- The scaffold launcher scenario uses a UE 5.8 fake and asserts the recorded editor argv includes `-ModelContextProtocolStartServer` and `-ModelContextProtocolPort=<test port>`; the UE plugin skeleton feature names 5.8 and `EngineVersion "5.8.0"` (AC1, AC2)
- Passes under `repository.tests`, `repository.lint`, and `repository.types`

### T008: Smoke script tests

**File(s)**: `tests/unit/test_smoke_unreal_mcp.py`, `tests/unit/test_smoke_blender_mcp.py`
**Type**: Create
**Depends**: T004
**Acceptance**:
- A threaded stub HTTP MCP server (JSON and SSE responses, session header, toolset dispatch) drives `smoke-unreal-mcp.py` to exit 0, to exit 1 naming the step when the import check prints false, and to exit 2 when nothing is listening (AC4)
- A stub stdio MCP server script drives `smoke-blender-mcp.py` to exit 0, exit 1 when `execute_blender_code` is missing, and exit 2 on a "could not connect to Blender" result (AC5)
- Passes under `repository.tests`, `repository.lint`, and `repository.types`
- Live runs pass on the reference machine: `scripts/install-vibeue.sh`, then `scripts/start-unreal-mcp.sh`, then `scripts/smoke-unreal-mcp.py` against UE 5.8 at `/Users/Shared/Epic Games/UE_5.8`; and `scripts/install-blender-mcp-addon.sh`, then `BLENDER_APP="/Volumes/Fast Brick/Applications/Blender.app" scripts/start-blender-mcp.sh`, then `scripts/smoke-blender-mcp.py` (AC2, AC4, AC5)

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #68 | 2026-10-30 | Initial feature tasks |
