# Upgrading nmg-game-dev in a project

Use this when a new nmg-game-dev release ships and the project should pick it up.

## 1. Review breaking changes

Read the new version's entry in `CHANGELOG.md`. Breaking changes are marked
`**BREAKING CHANGE:**` and have a `### Migration Notes` section. Apply the notes before you onboard,
especially for renamed skills, MCP tool names, and changed asset contract rules.

## 2. Re-register the plugin

Update the plugin from the `nmg-plugins` marketplace so the new version is active:

```text
/plugin install nmg-game-dev@nmg-plugins
```

Restart the Claude Code session so the new plugin root and `.mcp.json` load.

## 3. Re-run onboarding with `--refresh`

Run `/onboard-consumer`. A plain re-run reports drift for every framework-owned copy that has changed
and changes nothing. Run it with `--refresh` to bring the copies up to date:

```sh
uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m nmg_game_dev.onboard install --consumer "$CLAUDE_PROJECT_DIR" --models-dir <models dir> --refresh
```

`--refresh` restores the start script, the asset and design contracts, the `nmg_game_dev` add-on in
`game/addons/`, the framework keys in `game/project.godot` (renderer, editor plugin, and autoload),
and `game/export_presets.cfg`, and fixes the Blender link. Your own keys in `project.godot` are kept.
It never changes `nmg-budgets.json`, which belongs to the project.

If the project still uses the previous engine target, convert it first with `/convert-to-godot`
(see [docs/skills/convert-to-godot.md](../skills/convert-to-godot.md)).

## 4. Check the project

- Run the project's tests and the asset validation on one existing asset.
- Run `godot --headless --path game --import` and confirm it prints no `ERROR:` line.
- Open `game/` in the Godot editor and confirm the `nmg-game-dev` plugin is enabled under
  Project Settings > Plugins.
- If an asset now fails the contract, read the rule named in the failure and fix the asset.
