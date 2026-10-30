# Changelog

All notable changes to `nmg-game-dev` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to semver per `steering/tech.md` § Versioning.

## [Unreleased]

### Changed

- The toolchain targets Unreal Engine 5.8 with Epic's native Unreal MCP server on `127.0.0.1:8000/mcp`, with VibeUE's toolsets registered on it. The Node.js `mcp-remote` bridge and port 8088 are removed, and the Blender MCP server runs `uvx mcp-for-blender@latest` with telemetry disabled. Third-party tools (Blender MCP, its add-on, VibeUE) track latest releases instead of pins. (#68)

### Added

- `scripts/install-vibeue.sh` and `scripts/install-blender-mcp-addon.sh` fetch the latest VibeUE and Blender add-on. `scripts/smoke-unreal-mcp.py` and `scripts/smoke-blender-mcp.py` verify the MCP endpoints end to end. (#68)

## [0.6.0] - 2026-10-30

### Changed

- Steering describes freeform Blender authoring checked by the asset contract, a finalize pipeline (validate → bake → variants → export → re-import → UE import), local AI texture models, scene composition in Unreal, Blender 5.2 and UE 5.8 with Epic's native MCP plus VibeUE, and no Meshy or recipe library.
- nmg-game-dev is now a Claude Code plugin only, installed from the `nmg-plugins` marketplace: the Codex manifest (`.codex-plugin/`), Codex marketplace (`.agents/`), project Codex config (`.codex/`), and Codex consumer templates are removed; consumers get Claude Code `SessionStart` hooks from `templates/consumer/.claude/settings.json`, and MCP servers from the plugin's bundled `.mcp.json`. Docs, steering, and scaffold tests use Claude Code and `/sdlc-*` command names.
- Asset generation is freeform Blender authoring checked against an asset contract; the recipe-library plan and the `docs/decisions/` ADRs are removed, and the scaffold contract no longer requires `docs/decisions/`.
- Project instructions moved from `AGENTS.md` to `CLAUDE.md`; scaffold tests now check the `steering/snippets/` paths.
- `.gitignore` ignores `.nmg-sdlc/` runtime state in place of the legacy `.omp/sdlc/` rule.
- The Meshy pipeline source, MCP client types, and `meshy` MCP server are removed; `pipeline.run` accepts only `source="blender"` and rejects any other source with `pipeline.unsupported_source`. (#64)

### Added

- Steering registers required verification gates: pytest (unit + BDD), ruff, and mypy on every change; `claude plugin validate .` and a plugin-session smoke on plugin-surface changes. The smoke (`steering/extensions/plugin-session-smoke.mjs`) starts `claude --plugin-dir <checkout>` in a Herdr tab inside an ephemeral project, with the installed `nmg-game-dev@nmg-plugins` turned off for that session only, and passes when the plugin's Blender MCP server connects.
- `README.md` with install instructions, and `repository`/`keywords` in `.claude-plugin/plugin.json`.
- `docs/asset-contract.md`: what "done" means for any Blender-generated asset (layout, pivots, UVs, FBX-safe materials, Desktop/Mobile variants, budgets, export, validation).
- `.claude-plugin/plugin.json` so nmg-game-dev also installs as a Claude Code plugin; version-managed alongside `.codex-plugin/plugin.json`.

## [0.5.0] - 2026-04-23

### Added

- Pipeline composition core: variant-aware stage runner with cacheable, idempotent `pipeline.run()` orchestrator; six stage modules (generate, texture, cleanup, variants, quality, import_ue); content-addressed `ArtifactCache`; `variants/` path helpers; `quality/` budget + manifest gates; BDD coverage for AC1–AC4; unit + e2e scaffolding. (#4)

## [0.4.0] - 2026-04-22

### Added

- Blender add-on skeleton: operator/panel/property-group stubs, mcp_server integration seam, headless test harness. (#3)

## [0.3.0] - 2026-04-22

### Added

- UE plugin skeleton: Runtime and Editor modules, AssetResolver, automation test runner. (#2)

## [0.2.0] - 2026-04-22

### Added

- Initial scaffolding: plugin manifest, directory layout, session-start launcher scripts,
  MCP config, Python package, consumer SessionStart template. (#1)
