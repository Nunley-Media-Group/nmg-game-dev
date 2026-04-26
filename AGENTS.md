# nmg-game-dev

Blender-first, Unreal-shipped content pipeline for NMG games. Distributed as a Codex
plugin, a Blender add-on, and a UE plugin. Install through a Codex plugin marketplace
or from this repo; consumer-side artifacts land via `$onboard-consumer` regardless of
install scope. See `specs/feature-scaffold-plugin-repo-session-start-hooks/requirements.md` AC11.

## Where to start

- **Product direction**: `steering/product.md`
- **Technical standards + gates**: `steering/tech.md`
- **Code organization**: `steering/structure.md`
- **Start a new unit of work**: `$nmg-sdlc:draft-issue`

## What this file is

A pointer to steering. Don't duplicate content from steering docs here.

## Session-start hooks — consumer-only

`scripts/start-blender-mcp.sh` and `scripts/start-unreal-mcp.sh` are launcher scripts that
consumer game projects run automatically via Codex `SessionStart` hooks in their
`.codex/hooks.json`.

Inside this repo (nmg-game-dev itself), contributors invoke the scripts manually when they need
Blender or UE running for pipeline testing. There is no repo-root `.codex/hooks.json`
registering those hooks — this repo is a library, not a game.

The consumer templates live at `templates/consumer/.codex/hooks.json` and
`templates/consumer/.codex/config.toml`, and are installed into downstream projects by
`$onboard-consumer` (a future v1 issue).
