# Requirements: Remove Meshy from the pipeline and MCP config

**Issue**: #64
**Date**: 2026-10-29
**Status**: Approved
**Author**: Rich Nunley
**Related Spec**: specs/4-pipeline-composition-core-variant-aware-stage-runner/

## User Story

**As an** internal NMG game developer
**I want** the pipeline to have Blender as its only generation source, with no Meshy route, client type, or MCP server
**So that** the pipeline, the bundled MCP config, and the tests describe one supported path and no Meshy credential is ever needed

## Background

`pipeline.run` still accepts `source="meshy"` and routes it to `stages.generate.generate_meshy`. `McpClients` has an optional `meshy` field typed by the `MeshyMcp` Protocol, and `stages/_mcp.py` lists `"meshy"` as a server with a `MESHY_API_KEY` remediation. `.mcp.json` pins a `meshy` server (`meshy-mcp-server@1.2.3`, `MESHY_API_KEY`), and the scaffold contract requires it. Unit, BDD, and e2e tests carry Meshy fakes and a Meshy-supplement scenario. The steering snippets no longer offer Meshy as a source; a guard test keeps it that way.

The `generate` stage itself stays. The pipeline reshape (#69) replaces it.

## Acceptance Criteria

### AC1: Blender is the only pipeline source

**Given** a valid `Prompt`
**When** `pipeline.run(prompt, source="blender", mcp_clients=McpClients(blender=..., unreal=...))` is called
**Then** it runs generate → texture → cleanup → variants → quality → import_ue and returns a `PipelineResult`, with no Meshy client involved

### AC2: The Meshy source is rejected

**Given** a valid `Prompt`
**When** `pipeline.run(prompt, source="meshy", ...)` is called, or any source other than `"blender"`
**Then** it raises `PipelineError` with code `pipeline.unsupported_source`, stage `pipeline`, and a remediation naming `"blender"` as the supported source
**And** no MCP client method was called and no cache entry was written

### AC3: Meshy client types are gone

**Given** the `nmg_game_dev.pipeline` package
**When** it is imported
**Then** `McpClients` has no `meshy` field, `stages._base.MeshyMcp` and `stages.generate.generate_meshy` do not exist, the `stages._mcp.Server` literal is exactly `"blender" | "unreal"`, and `pipeline.Source` is exactly `"blender"`
**And** `ruff check .`, `ruff format --check .`, and `mypy src/ tests/` pass

### AC4: The MCP configuration has no Meshy server

**Given** the repo `.mcp.json`
**When** the scaffold contract tests run
**Then** it contains no `meshy` server key and no `MESHY_API_KEY` or `meshy-mcp-server` text, the `blender` and `unreal` entries are unchanged, `REQUIRED_SERVERS` is `("blender", "unreal")`, and a guard test asserts that Meshy is absent

### AC5: Steering does not offer Meshy as a source

**Given** the Markdown files under `steering/snippets/`
**When** a guard test scans them
**Then** none contains `--source meshy`, `source="meshy"`, `meshy-mcp-server`, or `MESHY_API_KEY`

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Restrict `pipeline.Source` to `"blender"`, and have `pipeline.run` reject any other value with `PipelineError("pipeline.unsupported_source")` before any other check, MCP call, or cache write | Must |
| FR2 | Delete `generate_meshy`, `MeshyMcp`, `McpClients.meshy`, and the `meshy` member of the `_mcp.py` `Server` literal and its remediation entry; update the affected module docstrings | Must |
| FR3 | Remove the `meshy` entry from `.mcp.json`, leaving the other entries byte-for-byte unchanged; set `REQUIRED_SERVERS` to `("blender", "unreal")`; replace the Meshy env guard with an absence guard; update the scaffold feature's MCP step to two servers | Must |
| FR4 | Delete `pipeline_meshy_supplement.feature`, its scenario and steps, the e2e Meshy test, and every Meshy fake and fixture; add unit and BDD coverage for `pipeline.unsupported_source` and a unit test for AC3 | Must |
| FR5 | Add a guard test that scans `steering/snippets/*.md` for the AC5 strings | Must |

## Out of Scope

- Editing historical records under `specs/`
- Blender or Unreal MCP entry changes (the Unreal endpoint move is #68)
- Removing or reshaping the `generate` stage (#69)
- The texture stage

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #64 | 2026-10-29 | Initial feature spec |
