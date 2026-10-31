# nmg-game-dev

Blender-first, Unreal-shipped content pipeline for Nunley Media Group games, delivered as a
Claude Code plugin with a Blender add-on and an Unreal Engine plugin.

Assets are authored freeform: you describe what you want, and Claude builds it in Blender
through the Blender MCP, iterating with you. What makes the result shippable is the
[asset contract](docs/asset-contract.md), which defines what "done" means: scene layout,
pivots, UVs, FBX-safe materials, Desktop and Mobile variants, budgets, export, and a
validate / proof / re-import routine. Finished assets are imported into Unreal through the
Unreal MCP (VibeUE), where levels are composed.

## Install

The plugin is listed in the [`nmg-plugins`](https://github.com/Nunley-Media-Group/nmg-plugins)
marketplace. In a Claude Code session:

```
/plugin marketplace add Nunley-Media-Group/nmg-plugins
/plugin install nmg-game-dev@nmg-plugins
```

Enabling the plugin also brings its MCP servers (Blender MCP and the Unreal MCP endpoint),
declared in [`.mcp.json`](.mcp.json). Third-party toolchain pieces track their latest releases;
see [`docs/mcp/`](docs/mcp/) for the setup and the smoke tests.

## Requirements

- Claude Code
- Blender 5.2 with the Blender MCP add-on (`scripts/install-blender-mcp-addon.sh`)
- Unreal Engine 5.8 with Epic's Unreal MCP server and the VibeUE plugin (`scripts/install-vibeue.sh`)
- `uv` (for the Blender MCP server, `uvx mcp-for-blender@latest`)

Set `BLENDER_APP` or `BLENDER_BIN`, and `UE_ROOT`, when Blender or Unreal aren't at their
default install paths.

## Consumer game projects

Start with [`docs/onboarding/index.md`](docs/onboarding/index.md): run `/onboard-consumer` in your
game project, then follow the first-asset and first-ship guides.



Game projects run `scripts/start-blender-mcp.sh` and `scripts/start-unreal-mcp.sh` as
Claude Code `SessionStart` hooks so Blender and Unreal are up when a session starts. The
hook template is [`templates/consumer/.claude/settings.json`](templates/consumer/.claude/settings.json);
see [`templates/consumer/README.md`](templates/consumer/README.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and the steering docs under `steering/snippets/`.
Changes are recorded in [CHANGELOG.md](CHANGELOG.md).
