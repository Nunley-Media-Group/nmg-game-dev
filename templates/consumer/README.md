# templates/consumer — Consumer-onboarding templates

Onboarding guide for consumer projects: [`docs/onboarding/index.md`](../../docs/onboarding/index.md).
The `onboard-consumer` skill installs these templates (see `skills/onboard-consumer/SKILL.md`).

This directory contains files that are **templates for consumer game projects**,
not configuration used by `nmg-game-dev` itself.

## Contents

| File | Consumer destination | Purpose |
|------|----------------------|---------|
| `.claude/settings.json` | `<consumer>/.claude/settings.json` | Registers the Claude Code `SessionStart` hook that auto-launches Blender with its MCP server when a session starts in the consumer project |

The Blender MCP server itself needs no template: it ships in the plugin's root `.mcp.json`,
which Claude Code loads automatically when the `nmg-game-dev` plugin is enabled. Godot needs
no hook or MCP server: every Godot stage runs `godot --headless` on demand.

## How templates reach a consumer project

`/onboard-consumer` merges these templates into each consumer game project. It also copies
`scripts/start-blender-mcp.sh` into the consumer's `scripts/` directory, so the `SessionStart`
hook entry resolves.

## Why the hook template lives here — not at the repo root

`nmg-game-dev` is a **library**, not a game. Contributors working inside this repo launch
Blender manually when they need it for pipeline testing. Auto-launching it on every Claude Code
session would slow down sessions where it isn't needed.

The `SessionStart` hook is a **consumer-project feature**. It belongs in consumer repos, where a
developer's entire session is spent working on a game that depends on Blender. It is also not
shipped as a plugin hook, because a user-scope install would then launch Blender in every
project.

See `specs/feature-scaffold-plugin-repo-session-start-hooks/requirements.md`
§ "Scope of session-start hooks — consumer-game-only" for the full rationale.

## Merging with existing Claude Code settings

If the consumer's project already has `.claude/settings.json`, `/onboard-consumer` merges the
`SessionStart` hook entry into it rather than overwriting existing settings. Hooks and keys the
consumer already has are kept.
