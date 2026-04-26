# templates/consumer — Consumer-onboarding templates

This directory contains files that are **templates for consumer game projects**,
not configuration used by `nmg-game-dev` itself.

## Contents

| File | Consumer destination | Purpose |
|------|----------------------|---------|
| `.codex/hooks.json` | `<consumer>/.codex/hooks.json` | Registers `SessionStart` hooks that auto-launch Blender MCP and UE Editor when the consumer opens their project in Codex |
| `.codex/config.toml` | `<consumer>/.codex/config.toml` | Enables Codex hooks and declares the pinned MCP server launchers used by the consumer project |

## How templates reach a consumer project

The `onboard-consumer` skill (a future v1 issue) copies or merges these templates into
each consumer game project. The consumer's `scripts/` directory must already contain
`start-blender-mcp.sh` and `start-unreal-mcp.sh` (also copied by `onboard-consumer`) for
the `SessionStart` hook entries to resolve.

## Why the hook template lives here — not at the repo root

`nmg-game-dev` is a **library**, not a game. Contributors working inside this repo launch
Blender and Unreal Engine manually when they need them for pipeline testing. Auto-launching
both tools on every Codex session would slow down sessions where they aren't needed.

The `SessionStart` hooks are a **consumer-project feature**. They belong in consumer repos
where a developer's entire session is spent working on a game that depends on Blender and UE.

See `specs/feature-scaffold-plugin-repo-session-start-hooks/requirements.md`
§ "Scope of session-start hooks — consumer-game-only" for the full rationale.

## Merging with existing Codex config

If the consumer's project already has `.codex/hooks.json` or `.codex/config.toml`,
`onboard-consumer` will merge the `SessionStart` hook entries and `[features]` /
`[mcp_servers.*]` entries rather than overwriting existing configuration. The exact
merge strategy is defined in the `onboard-consumer` skill when it lands.
