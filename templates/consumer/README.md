# templates/consumer — Consumer-onboarding templates

This directory contains files that are **templates for consumer game projects**,
not configuration used by `nmg-game-dev` itself.

## Contents

| File | Consumer destination | Purpose |
|------|----------------------|---------|
| `.claude/settings.json` | `<consumer>/.claude/settings.json` | Registers Claude Code `SessionStart` hooks that auto-launch Blender MCP and UE Editor when a session starts in the consumer project |

The Blender and Unreal MCP servers themselves need no template: they ship in the
plugin's root `.mcp.json`, which Claude Code loads automatically when the
`nmg-game-dev` plugin is enabled.

## How templates reach a consumer project

The `onboard-consumer` skill (a future v1 issue) copies or merges these templates into
each consumer game project. The consumer's `scripts/` directory must already contain
`start-blender-mcp.sh` and `start-unreal-mcp.sh` (also copied by `onboard-consumer`) for
the `SessionStart` hook entries to resolve.

## Why the hook template lives here — not at the repo root

`nmg-game-dev` is a **library**, not a game. Contributors working inside this repo launch
Blender and Unreal Engine manually when they need them for pipeline testing. Auto-launching
both tools on every Claude Code session would slow down sessions where they aren't needed.

The `SessionStart` hooks are a **consumer-project feature**. They belong in consumer repos
where a developer's entire session is spent working on a game that depends on Blender and UE.
They are also not shipped as plugin hooks, because a user-scope install would then launch
Blender and UE in every project.

See `specs/feature-scaffold-plugin-repo-session-start-hooks/requirements.md`
§ "Scope of session-start hooks — consumer-game-only" for the full rationale.

## Merging with existing Claude Code settings

If the consumer's project already has `.claude/settings.json`, `onboard-consumer` will
merge the `SessionStart` hook entries rather than overwriting existing settings. The exact
merge strategy is defined in the `onboard-consumer` skill when it lands.
