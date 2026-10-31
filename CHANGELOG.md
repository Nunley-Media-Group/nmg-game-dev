# Changelog

All notable changes to `nmg-game-dev` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to semver per `steering/tech.md` § Versioning.

## [Unreleased]

### Added

- Design docs: `/design` reads the markdown in `docs/design/` into `docs/design/backlog.json` with `python -m nmg_game_dev.design sync`, which keeps each entry's status across re-syncs and marks removed docs `orphaned`. `scaffold` creates each region's level, each mission's `UNmgMissionDefinition` data asset, and each system's Blueprint in Unreal, and never overwrites an existing asset. `finalize_asset` takes `category` and `asset_class` from the backlog when they are omitted, and marks the entry `finalized` on success. Reference: `docs/design-contract.md` and `docs/skills/design.md`. (#112)

## [0.18.0] - 2026-10-31

### Added

- Meshy `a-pose` imports raise each arm about its shoulder until its drop is 48°, so `rig_humanoid` accepts the arms without hand reposing (its limit is 50°); the `import_glb` and generate-job results report `arm_raise` with each side's `drop_before_deg`, `drop_after_deg`, and `rotation_deg` (#106)

## [0.17.0] - 2026-10-31

### Added

- Meshy imports into the Blender session are normalized: `SM_<Name>` is welded within 1e-5 m, its origin sits at the bottom center at the world origin with identity transforms, and its normals are cleared and smoothed by 30°; the `import_glb` and generate-job results report `merged_vertices` and `origin_offset` (#105)

## [0.16.0] - 2026-10-31

### Added

- `scripts/start-unreal-mcp.sh` builds missing or stale source-only project plugin binaries before it launches the editor, logging to `/tmp/unreal-mcp-build.log`; the consumer SessionStart hook for it gets a 900-second timeout (#103)

## [0.15.3] - 2026-10-31

### Fixed

- Onboarding and `scripts/install-vibeue.sh` track VibeUE's UE 5.8 branch `5-8` instead of a frozen tag and commit, which did not compile on UE 5.8 macOS; `--refresh` moves VibeUE to the `5-8` head (#104)

## [0.15.2] - 2026-10-31

### Fixed

- Finalize keeps the rig of a character rigged with `rig_humanoid`: the Desktop FBX stays skinned to its armature, the Mobile variant ships three skinned LODs as one FBX each, and UE imports both variants as Skeletal Meshes that share the Desktop skeleton and physics asset (#102)

## [0.15.1] - 2026-10-31

### Fixed

- Fix the M_NmgORM master material so its samplers default to textures of their own sampler type and it is enabled for skeletal meshes, so finalized assets render their baked textures (#101)

## [0.15.0] - 2026-10-31

### Changed

- Add optional Meshy model generation and retexturing through the Meshy API (#98)

## [0.14.1] - 2026-10-31

### Fixed

- Fix the always-green Blender gate, re-import entry lookup, notarization secret exposure, and stale lockfiles (#95)

## [0.14.0] - 2026-10-31

### Added

- Consumer onboarding: `/onboard-consumer` runs `python -m nmg_game_dev.onboard install` to install the start scripts and SessionStart hooks, the asset contract, the nmg-game-dev and VibeUE Unreal plugins (pinned), the Blender add-on link, and the two local texture models into a game project. Re-runs are idempotent and report drift; `--refresh` repairs it. Reference: `docs/onboarding/index.md`. (#7)
- Local texture generation: `python -m nmg_game_dev.texture generate` and the `texture-gen` MCP server generate seamless albedo with the pinned Z-Image Turbo and FLUX.2 klein 4B models, derive normal, roughness, metallic, and AO maps, and write to `SourceArt/Textures/Generated/<name>/`. Reference: `docs/onboarding/texture-models.md`. (#7)

## [0.13.0] - 2026-10-30

### Added

- Ship skill: `/ship` runs `python -m nmg_game_dev.ship <target>` to build, gate, sign, notarize, and package the UE project per platform into `release/<platform>/`, with `release/RELEASE-NOTES.md` listing each artifact and its SHA-256. The mobile budget gate reads each `Mobile/nmg-asset.json` and the optional `nmg-budgets.json` overrides, and the cook-manifest gate blocks cross-variant `Content/` paths. Reference: `docs/skills/ship.md`. (#6)

## [0.12.0] - 2026-10-30

### Added

- Humanoid rigging and animation import in the Blender add-on. `rig_core` builds a deform-only UE5 Mannequin armature `SK_<Name>` from agent-supplied landmarks with automatic weights, retargets clips from a local `library.json` library (FBX or BVH, Mixamo or Manny bones) onto it, and exports a rigged FBX with `nmg-animations.json`. Three operators wrap it: `nmggamedev.rig_humanoid`, `nmggamedev.import_animations`, and `nmggamedev.export_rigged`. Reference: `docs/rigging-and-animation.md`. (#32)

## [0.11.0] - 2026-10-30

### Changed

- **BREAKING CHANGE:** The pipeline finalizes a collection the agent authored in Blender instead of generating one from a prompt. `pipeline.run(prompt, source)` is replaced by `pipeline.finalize(request)` and `pipeline.run_step(step, request)` over a `FinalizeRequest`. A run is `validate → bake → variants → export → reimport → import_ue`, and the Blender steps run headless against a checkpoint of the open session and load back into it. (#69)

### Added

- `finalize` MCP server (`finalize_asset`, `run_finalize_step`, `get_finalize_job`), the `python -m nmg_game_dev.finalize` CLI, and the `finalize-asset` skill share one implementation. Each step has a content-addressed cache with an alias index, and `M_NmgORM` is the plugin-owned master material for imported textures. Reference: `docs/mcp/finalize.md`. (#69)

### Removed

- `pipeline.prompt` (`Prompt`), the `generate`, `texture`, `cleanup`, `variants`, `quality`, and `import_ue` stage modules, the `source` argument with its Meshy and unsupported-source routing, and `PipelineResult`. (#69)

### Migration Notes

- Replace `pipeline.run(prompt, source="blender")` with `pipeline.finalize(request)`. Author the asset in Blender first, then build `FinalizeRequest(collection="Crate", category="Props", asset_class="standard_prop", export_root=...)` from the collection's name. Drop the `Prompt` and `source` arguments.
- `PipelineResult.desktop_path` and `mobile_path` become `FinalizeResult.desktop_content_path` and `mobile_content_path`.
- The test seams change: `mcp_clients=` becomes `clients=`, and `stage_overrides=` is replaced by `runner=`.
- Single-stage calls become `pipeline.run_step(step, request)`, where `step` is one of `validate`, `bake`, `variants`, `export`, `reimport`, or `import_ue`.
- Cache entries written by the old stage runner are not reused, because the keys now cover the step and the asset content. Delete `by-key/` under the cache root to reclaim the space.

## [0.10.0] - 2026-10-30

### Added

- `nmggamedev.bake_materials` bakes whatever materials the agent authored on an asset into contract-compliant UV texture sets: BC (sRGB), N, and ORM at Desktop and Mobile size, with materials merged into one `M_<Name>_Body` set above the Mobile limit, a seamless tiling mode for environment pieces, and a pre-bake and baked three-quarter proof gated by a tolerance. The same `bake_core.bake_asset` backs the Blender MCP call and the pipeline `texture` stage, which replaces its placeholder. Repeat runs are cache hits. (#67)

## [0.9.0] - 2026-10-30

### Added

- Asset contract tooling shared by three entry points: `nmggamedev.validate_contract` checks asset-contract sections 1-6 and reports each violated rule, `nmggamedev.reimport_check` compares an exported FBX with the pre-export report in a fresh headless Blender, and `nmggamedev.render_review` writes front, back, side, and three-quarter renders plus the labeled texture proof sheet. `python -m nmg_game_dev.contract validate|reimport|render` runs the same code headless, and `nmg_game_dev.quality.contract.gate` stops the finalize pipeline on a failing report. (#30)

## [0.8.0] - 2026-10-30

### Added

- Blender add-on variant operators replace the stubs: `nmggamedev.cleanup_desktop` removes duplicate, loose, and zero-area geometry with no decimation, `nmggamedev.optimize_mobile` decimates to the contract budget with LOD1 and LOD2 under an FBX LodGroup, and `nmggamedev.generate_variants` exports identically named Desktop and Mobile FBX with PNG textures and sidecar metrics. Mobile budgets honor `nmg-budgets.json` overrides. (#33)

## [0.7.0] - 2026-10-30

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
