# Requirements: Register the project verification gates and a UE compile extension in steering

**Issue**: #123
**Date**: 2026-11-01
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As an** nmg-game-dev contributor running `/sdlc-verify-code` or `/sdlc-execute`
**I want** every project gate that the tech steering lists to be registered in `steering/manifest.json`
**So that** verification runs the Blender, Unreal, MCP schema, shellcheck, ship-smoke, and format checks rather than only the `repository.*` checks

## Background

`/sdlc-verify-code` runs only the validations that `steering/manifest.json` registers. Before this change the manifest registered `repository.tests`, `repository.lint`, `repository.types`, `plugin.validate`, and `plugin.session-smoke`, while `steering/snippets/project-tech.md` listed older `gate-*` names and a `verify-skip` rule that the manifest runtime does not honor.

## Acceptance Criteria

### AC1: The manifest registers every project gate

**Given** `steering/manifest.json`
**When** it is loaded
**Then** it registers the required validations `repository.format`, `gate-blender-headless`, `gate-ue-compile`, `gate-mcp-schema`, `gate-shellcheck`, and `gate-ship-smoke`, each with the `changed_paths` condition (or `always` for `repository.format`) and command listed in the tech steering table

### AC2: A project extension compiles the UE plugin

**Given** the `project.ue-compile` extension at `steering/extensions/ue-compile.mjs`
**When** `gate-ue-compile` applies
**Then** it runs the engine `Build.sh DogfoodEditor Mac Development -Project=<absolute fixtures/dogfood.uproject>` and returns `passed` on exit 0, `failed` with the error lines otherwise, and `incomplete` when the host is not macOS, `Build.sh` is missing, or the project file is missing

### AC3: The tech steering table mirrors the manifest

**Given** `steering/snippets/project-tech.md`
**When** a contributor reads `## Verification Gates`
**Then** it lists every registered validation id with its condition, command, and host prerequisite, has no `verify-skip` rule, and names UE Automation and the E2E pipeline as not yet gated

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Register the six validations in `steering/manifest.json` as required. | Must |
| FR2 | Add `steering/extensions/ue-compile.mjs` exporting the `project.ue-compile` provider, registered under `extensions`, importing only Node built-ins. | Must |
| FR3 | Rewrite the `## Verification Gates` section of `steering/snippets/project-tech.md` to mirror the manifest. | Must |

## Out of Scope

- Registering `gate-ue-automation` (its reports are written into tracked files) and the E2E pipeline.
- Changing any gate script itself.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #123 | 2026-11-01 | Initial feature spec |
