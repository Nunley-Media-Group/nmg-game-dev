# nmg-game-dev

Blender-first, Unreal-shipped content pipeline for NMG games. Distributed as a Codex
plugin, a Blender add-on, and a UE plugin. Install through a Codex plugin marketplace
or from this repo; consumer-side artifacts land via `$onboard-consumer`
regardless of install scope. See AC11 in
`specs/feature-scaffold-plugin-repo-session-start-hooks/requirements.md`.

## Where to start

- **Product direction**: `steering/snippets/project-product.md` (registered in `steering/manifest.json`)
- **Technical standards + gates**: `steering/snippets/project-tech.md`
- **Code organization**: `steering/snippets/project-structure.md`
- **Start a new unit of work**: `$nmg-sdlc:draft-issue`

## What this file is

A pointer to steering. Don't duplicate content from steering docs here.

## Session-start hooks — consumer-only

`scripts/start-blender-mcp.sh` and `scripts/start-unreal-mcp.sh` are launcher
scripts that consumer game projects run automatically via Codex `SessionStart`
hooks in their `.codex/hooks.json`.

Inside this repo (nmg-game-dev itself), contributors invoke the scripts
manually when they need Blender or UE running for pipeline testing. There is no
repo-root `.codex/hooks.json` registering those hooks — this repo is a library,
not a game.

The consumer templates live at `templates/consumer/.codex/hooks.json` and
`templates/consumer/.codex/config.toml`, and are installed into downstream
projects by `$onboard-consumer` (a future v1 issue).

<!-- nmg-sdlc-managed: spec-context -->
## nmg-sdlc Spec Context

For SDLC work, project-root `specs/` is the canonical BDD archive. Specs use directories of the form `specs/{N}-{slug}/` where `N` is the GitHub issue number. Always identify the active spec first (leading directory number must match the issue and every file must declare singular `**Issue**: #N`), then use bounded relevant-spec discovery to load only the neighboring specs that can affect the change. Do not load the full archive by default. Legacy `.codex/specs/` directories are inputs to `/sdlc-upgrade-project` only.
<!-- /nmg-sdlc-managed -->
