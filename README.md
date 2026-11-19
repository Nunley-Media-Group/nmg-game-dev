# nmg-game-dev

Blender-first, Godot-shipped content pipeline for Nunley Media Group games, delivered as a
Claude Code plugin with a Blender add-on and a Godot add-on.

Assets are authored freeform: you describe what you want, and Claude builds it in Blender
through the Blender MCP, iterating with you. What makes the result shippable is the
[asset contract](docs/asset-contract.md), which defines what "done" means: scene layout,
pivots, UVs, glTF-safe materials, Desktop and Mobile variants, budgets, `.glb` export, and a
validate / proof / re-import routine. Finished assets are imported into the game's Godot 4
project (`game/project.godot`) by running `godot --headless`, and levels are composed in Godot.
There is no live editor bridge and no engine MCP server: every Godot stage is headless and
file-based.

## Install

The plugin is listed in the [`nmg-plugins`](https://github.com/Nunley-Media-Group/nmg-plugins)
marketplace. In a Claude Code session:

```
/plugin marketplace add Nunley-Media-Group/nmg-plugins
/plugin install nmg-game-dev@nmg-plugins
```

Enabling the plugin also brings its MCP servers (the Blender MCP, finalize, texture-gen, and
meshy), declared in [`.mcp.json`](.mcp.json). Third-party toolchain pieces track their latest
releases; see [`docs/mcp/`](docs/mcp/) for the setup and the smoke tests.

## Requirements

- Claude Code
- Blender 5.2 with the Blender MCP add-on (`scripts/install-blender-mcp-addon.sh`)
- Godot 4, the latest stable release (never pinned)
- ffmpeg, to import music as Ogg Vorbis
- `uv` (for the Blender MCP server, `uvx mcp-for-blender@latest`)

Set `BLENDER_APP` or `BLENDER_BIN` when Blender isn't at its default install path, `GODOT_BIN`
when Godot is not `godot` on `PATH` or at `/Applications/Godot.app`, and `FFMPEG_BIN` when ffmpeg
is not on `PATH`.

## Consumer game projects

Start with [`docs/onboarding/index.md`](docs/onboarding/index.md): run `/onboard-consumer` in your
game project, then follow the first-asset and first-ship guides. Onboarding creates the Godot
project in `game/`, installs the `addons/nmg_game_dev` add-on and the export presets, and wires
the Blender session-start hook. A project that still uses an older engine project can migrate
with [`/convert-to-godot`](docs/skills/convert-to-godot.md).

Game projects run `scripts/start-blender-mcp.sh` as a Claude Code `SessionStart` hook so Blender
is up when a session starts. Godot needs no hook, because it only runs headless. The hook
template is [`templates/consumer/.claude/settings.json`](templates/consumer/.claude/settings.json);
see [`templates/consumer/README.md`](templates/consumer/README.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and the steering docs under `steering/snippets/`.
Changes are recorded in [CHANGELOG.md](CHANGELOG.md).
