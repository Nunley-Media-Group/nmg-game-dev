# Requirements: Upgrade toolchain to UE 5.8 with native MCP plus VibeUE, and Blender 5.2 MCP

**Issue**: #68
**Date**: 2026-10-30
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/7-consumer-onboarding-onboard-consumer-skill-asset-contract-install-and-onboarding-docs/

## User Story

**As an** NMG game developer
**I want** nmg-game-dev and its dogfood fixture to target the current Blender and Unreal releases, each driven through its MCP server
**So that** agent sessions connect to Blender and Unreal out of the box, with no hand-patched pins or stale engine paths

## Background

The repo lags the installed toolchain. It targets UE 5.7 and VibeUE's own HTTP bridge on port 8088 through `mcp-remote`, and pins `blender-mcp@1.5.6` with an extra `mcp<2` constraint. UE 5.8 ships Epic's native Unreal MCP server (`ModelContextProtocol` plugin, with `EditorToolset`) at `http://127.0.0.1:8000/mcp`. VibeUE no longer runs its own server and registers its toolsets, including `execute_python_code`, on that endpoint. The Blender MCP project now publishes as `mcp-for-blender`, which bundles a matching Blender add-on and an `install-addon` command.

Third-party toolchain components track their latest releases: the Blender MCP server, its Blender add-on, and VibeUE are never pinned to a version, tag, or commit. Smoke scripts verify that the latest versions work together.

## Acceptance Criteria

### AC1: Unreal 5.8 everywhere

**Given** the repository
**When** it is searched for engine version references outside `specs/` and `CHANGELOG.md`
**Then** `fixtures/dogfood.uproject` has `EngineAssociation` `5.8`, `nmg-game-dev.uplugin` has `EngineVersion` `5.8.0`, `scripts/start-unreal-mcp.sh` and `scripts/run-ue-tests.sh` default `UE_ROOT` to `/Users/Shared/Epic Games/UE_5.8` (still overridable by `UE_ROOT`), steering names UE 5.8, and no `UE_5.7`, `5.7.0`, or `Unreal Engine 5.7` reference remains

### AC2: Native MCP plus VibeUE on one endpoint

**Given** the dogfood fixture with VibeUE installed by `scripts/install-vibeue.sh`
**When** `scripts/start-unreal-mcp.sh` launches the editor
**Then** the editor is started with `-ModelContextProtocolStartServer -ModelContextProtocolPort=<UE_MCP_PORT, default 8000>`, so Epic's Unreal MCP server listens on `127.0.0.1:<port>/mcp` with no manual editor steps
**And** `fixtures/dogfood.uproject` enables `ModelContextProtocol`, `EditorToolset`, `VibeUE`, and `nmg-game-dev`, and `fixtures/Config/DefaultEditorPerProjectUserSettings.ini` sets `bAutoStartServer=True` and `ServerPortNumber=8000`
**And** the fixture's `Source/` and `Config/` are tracked so a fresh clone can build the `DogfoodEditor` target
**And** the launcher still exits 0 without launching when the port is already listening

### AC3: The agent host config points at the native endpoint

**Given** the plugin's bundled `.mcp.json`
**When** it is read
**Then** the `unreal` server is `{"type": "http", "url": "http://127.0.0.1:${UE_MCP_PORT:-8000}/mcp"}` with a description naming Epic's Unreal MCP plus VibeUE
**And** the file contains no `mcp-remote`, no `8088`, and no "bridge" wording
**And** guard tests assert these values

### AC4: Unreal smoke test

**Given** UE 5.8 running the dogfood fixture through the start script
**When** `scripts/smoke-unreal-mcp.py` runs
**Then** it initializes an MCP session on the endpoint, lists toolsets and finds a VibeUE toolset that provides `execute_python_code`, runs a trivial `execute_python_code` call whose output includes the engine version `5.8`, imports `fixtures/smoke/SM_SmokeCube.fbx` into `/Game/__NmgSmoke`, confirms the static mesh exists, deletes `/Game/__NmgSmoke`, confirms it is gone, and exits 0
**And** it exits 2 with a remediation naming `scripts/start-unreal-mcp.sh` when the endpoint is unreachable, and exits 1 naming the failed step when any check fails

### AC5: Blender MCP runs the latest release without workarounds

**Given** Blender with the add-on installed by `scripts/install-blender-mcp-addon.sh` and started by `scripts/start-blender-mcp.sh`
**When** the `blender` server starts from `.mcp.json` and `scripts/smoke-blender-mcp.py` runs
**Then** `.mcp.json` runs `uvx mcp-for-blender@latest` with `BLENDER_MCP_DISABLE_TELEMETRY=1` and no `--with` or `mcp<2` argument
**And** `start-blender-mcp.sh` enables the `blender_mcp` add-on ahead of legacy add-on names
**And** the smoke script initializes the server over stdio, finds `execute_blender_code`, runs a trivial `bpy` call that returns `bpy.app.version_string`, and exits 0 (2 with a remediation when Blender or the add-on isn't reachable, 1 on a failed check)

### AC6: Third-party toolchain components track latest

**Given** `.mcp.json`, `scripts/install-vibeue.sh`, and `scripts/install-blender-mcp-addon.sh`
**When** they are read
**Then** every package reference in `.mcp.json` `blender` and `unreal` entries uses `@latest` or no version, with no `==`, `@<digit>`, or `<`/`>` constraint
**And** `install-vibeue.sh` clones VibeUE's default branch (or fast-forwards an existing clone) with no tag or commit pin
**And** `install-blender-mcp-addon.sh` installs the add-on bundled with `mcp-for-blender@latest`
**And** guard tests assert all three, replacing the old floating-version ban

### AC7: Docs and steering

**Given** steering and the MCP docs
**When** they are read
**Then** `docs/mcp/unreal.md` and `docs/mcp/blender.md` describe the two-layer Unreal setup (Unreal MCP + Editor Tools, then VibeUE), the ports (`UE_MCP_PORT` 8000, `BLENDER_MCP_PORT` 9876), UE 5.8 and the latest Blender, the install and smoke scripts, the latest-version policy, and the `UE_ROOT`, `UE_PROJECT`, `BLENDER_APP`, and `BLENDER_BIN` overrides
**And** `steering/snippets/project-tech.md` describes the same setup with no 8088 or migration-pending wording, and its third-party trust rule says tools track latest releases verified by the smoke scripts instead of pinning
**And** `README.md` requirements no longer list Node.js for an Unreal bridge

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Move every UE 5.7 reference (fixture, uplugin, scripts, tests, steering, fixture README) to 5.8 | Must |
| FR2 | `start-unreal-mcp.sh`: default port 8000 and native-server launch flags; fixture enables the four plugins and auto-start config; fixture `Source/` and `Config/` tracked; `fixtures/Plugins/` ignored | Must |
| FR3 | `scripts/install-vibeue.sh [plugins_dir]`: clone or fast-forward VibeUE's default branch into `fixtures/Plugins/VibeUE` by default | Must |
| FR4 | `.mcp.json` `unreal` entry on native HTTP with `${UE_MCP_PORT:-8000}`; `blender` entry `uvx mcp-for-blender@latest` with telemetry disabled; `meshy` untouched | Must |
| FR5 | `scripts/install-blender-mcp-addon.sh` and `start-blender-mcp.sh` preferring the `blender_mcp` add-on | Must |
| FR6 | Stdlib-only `scripts/smoke-unreal-mcp.py` and `scripts/smoke-blender-mcp.py` with exit codes 0 / 1 / 2, plus `fixtures/smoke/SM_SmokeCube.fbx` | Must |
| FR7 | Guard tests for the native endpoint, latest-version policy, and 5.8 references; updated BDD scaffold and UE plugin skeleton scenarios | Must |
| FR8 | `docs/mcp/unreal.md`, `docs/mcp/blender.md`, steering tech snippet, README, fixture README, CHANGELOG | Must |

## Out of Scope

- Consumer onboarding that installs VibeUE, the Unreal plugins, and the Blender add-on into game projects (#7)
- Removing Meshy (#64)
- New pipeline stages or UE-side import logic beyond the smoke test
- Pinning versions of the project's own Python dev dependencies

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #68 | 2026-10-30 | Initial feature spec |
