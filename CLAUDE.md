# nmg-game-dev

Blender-first, Unreal-shipped content pipeline for NMG games. Distributed as a Claude Code
plugin, a Blender add-on, and a UE plugin. Install at user scope (`~/.claude/plugins/`) or at
project scope inside a consumer game repo — the outcome is identical in both cases
(skills, commands, and agents are the same; consumer-side artifacts land via `onboard-consumer`
regardless of install scope). See `specs/feature-scaffold-plugin-repo-session-start-hooks/requirements.md` AC11.

## Where to start

- **Product direction**: `steering/product.md`
- **Technical standards + gates**: `steering/tech.md`
- **Code organization**: `steering/structure.md`
- **Start a new unit of work**: `/draft-issue` (nmg-sdlc entry point)

## What this file is

A pointer to steering. Don't duplicate content from steering docs here.

## Session-start hooks — consumer-only

`scripts/start-blender-mcp.sh` and `scripts/start-unreal-mcp.sh` are launcher scripts that
consumer game projects run automatically via `SessionStart` hooks in their `.claude/settings.json`.

Inside this repo (nmg-game-dev itself), contributors invoke the scripts manually when they need
Blender or UE running for pipeline testing. There is no `.claude/settings.json` at this repo's
root registering those hooks — this repo is a library, not a game.

The consumer `SessionStart` template lives at `templates/consumer/.claude/settings.json` and is
installed into downstream projects by `onboard-consumer` (a future v1 issue).
