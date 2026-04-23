# Changelog

All notable changes to `nmg-game-dev` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to semver per `steering/tech.md` § Versioning.

## [Unreleased]

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
