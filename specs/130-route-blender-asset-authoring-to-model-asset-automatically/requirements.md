# Defect Report: Route Blender asset authoring to /model-asset automatically

**Issue**: #130
**Date**: 2026-11-01
**Status**: Approved
**Author**: Rich Nunley

## Reproduction

1. In an onboarded consumer project with the Blender MCP connected, start a new Claude Code session.
2. Ask: "Model a wooden crate in Blender."
3. Claude calls `execute_blender_code` without loading `/model-asset`.

## Expected vs Actual

| | Description |
|---|-------------|
| **Expected** | Any request to create or change an asset's geometry or materials in Blender runs through `/model-asset`. Scene inspection and `/finalize-asset` runs are not redirected. |
| **Actual** | Claude authors the asset ad hoc through `execute_blender_code`; `/model-asset` runs only when invoked by name. |

## Acceptance Criteria

### AC1: Skill description states its trigger

**Given** `skills/model-asset/SKILL.md`
**When** its frontmatter is read
**Then** the one-line `description` says the skill is used whenever creating or changing an asset's geometry or materials in Blender, and still contains `freeform` and `Blender MCP`

### AC2: Consumer agent instructions route Blender asset work to the skill

**Given** a consumer project onboarded with `/onboard-consumer`
**When** the marked nmg-game-dev block is written to `CLAUDE.md` (and `AGENTS.md` when present)
**Then** the block instructs the agent to run `/model-asset` for any Blender asset authoring or editing and exempts scene inspection and `/finalize-asset`, and a re-run on a file holding the previous (0.21.0) block text replaces it in place and reports `refreshed`

### AC3: Plugin hook reminds once per session on execute_blender_code

**Given** the nmg-game-dev plugin's `hooks/hooks.json`
**When** the first `execute_blender_code` call (Blender MCP) in a session reaches the `PreToolUse` hook
**Then** the hook exits 0 and prints JSON whose `hookSpecificOutput.additionalContext` tells Claude to use `/model-asset` for asset authoring or editing and that inspection and `/finalize-asset` are exempt, with no `permissionDecision` and no `decision: block`

### AC4: Hook stays silent after the first reminder

**Given** the hook has already reminded for a session id
**When** a later `execute_blender_code` call for that session id reaches the hook
**Then** the hook exits 0 with no output, and a different session id receives the reminder

### AC5: Existing behavior is preserved and the hook fails open

**Given** the existing `/model-asset`, `/finalize-asset`, and onboarding tests
**When** the repository test suite runs
**Then** they pass, the onboarding block still links the asset- and design-contract pointers, and the hook exits 0 with no output when its input is not valid JSON, has no session id, or its state directory cannot be written

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Rewrite the `/model-asset` `description` as a single line with an explicit trigger for creating or changing asset geometry or materials in Blender, keeping `freeform` and `Blender MCP` | Must |
| FR2 | Extend the onboarding agent-instructions block with a line routing Blender asset authoring/editing to `/model-asset`, exempting scene inspection and `/finalize-asset` | Must |
| FR3 | Ship a plugin-level `PreToolUse` hook (`hooks/hooks.json`) whose matcher covers the Blender MCP `execute_blender_code` tool under both the `blender` and plugin-scoped server names; it emits the routing reminder as `additionalContext`, never denies or blocks, and fires once per session id | Must |
| FR4 | The hook fails open: any error reading input or session state results in a silent exit 0 | Must |
| FR5 | Update `docs/skills/model-asset.md`, `docs/onboarding/index.md`, and `CHANGELOG.md` `[Unreleased]` to describe the routing | Should |

## Out of Scope

- Changing the Blender MCP server's own instructions.
- Routing `/finalize-asset`, `/design`, or Unreal MCP work through hooks.
- Blocking `execute_blender_code` calls made outside `/model-asset`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #130 | 2026-11-01 | Initial defect report |
