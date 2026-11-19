# Changelog

All notable changes to `nmg-game-dev` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to semver per `steering/tech.md` § Versioning.

## [Unreleased]

### Fixed

- Rigged assets are measured and exported in their rest pose: validation, the Desktop re-seat, the reduce copy step, and the GLB exports read the rest shape whatever the pose bones hold, so a leftover pose no longer fails `pivot.bottom_center` or bakes into the geometry, and clip export puts every pose bone back where it was, also when it fails. Read-only (library-linked) armature data keeps its pose. (#236)

## [0.30.0] - 2026-11-19

### Added

- `NmgLaunch` autoload in the `addons/nmg_game_dev` add-on: `get_option` and `has_option` read the same launch options on desktop (`-- --name=value`) and web (`#name=value`), a bare flag reads `"true"`, `autoplay_requested` emits once after the main scene's `_ready` with `--nmg-autoplay`, so a main scene that connects in `_ready` receives it, and `save_dir()` returns `user://nmg-test/` with `--nmg-test-saves`. (#251)
- `python -m nmg_game_dev.godot smoke`: a headless 600-frame autoplay run that fails with `smoke.runtime_error` on a script error, `Parse Error`, `ERROR:` line, or non-zero exit, and with `smoke.timeout` past the timeout. `/ship` runs it as a gate after the project tests and before the mobile budget gate and every export, failing with `ship.smoke_failed` and exporting nothing. (#251)
- `python -m nmg_game_dev.godot shot <path>` and the finalize MCP tool `game_screenshot`: save a PNG of the running game after a delay, with launch options, and return `{path, width, height}`. Failures are `shot.no_image`, `shot.invalid_after`, `shot.invalid_path`, `godot.project_missing`, and `godot.not_found`. (#251)
- `/onboard-consumer` writes, refreshes, and drift-checks the `NmgLaunch` autoload in `game/project.godot`. (#251)
- `docs/onboarding/run-and-capture.md` documents the launch options, the smoke run, and screenshots, with the ship and finalize MCP docs updated to match. (#251)

## [0.29.1] - 2026-11-19

### Fixed

- Detect and repair one-edge twist seams so geometry.normals settles (#243)

## [0.29.0] - 2026-11-19

### Added

- `import_audio` finishes the game copy before it imports it: leading silence below -50 dBFS is trimmed, `max_seconds` cuts the sound with a 20 ms fade-out, a looping sound's seam is crossfaded over `loop_crossfade_ms` (default 500 ms, capped at a quarter of the sound), and loudness is matched to BS.1770 integrated -16 LUFS for sound effects or -18 LUFS for music, with a -1 dBFS peak ceiling reported as `loudness_capped`. `SourceArt/Audio/` keeps the bytes you saved. (#252)
- The `--no-loop`, `--max-seconds`, `--loudness-lufs`, `--loop-crossfade-ms`, and `--finish` / `--no-finish` flags on `python -m nmg_game_dev.audio import`, and the matching `max_seconds`, `loudness_lufs`, `loop_crossfade_ms`, and `finish` parameters on the finalize `import_audio` tool. The result carries `finish` and `settings`. (#252)
- Per-sound `loop` and finishing settings persist in `SourceArt/Audio/audio.json`, and an omitted `loop` reuses the stored value. A re-import of the same file re-finishes the same game copy, and `python -m nmg_game_dev.audio refinish --all` (or `refinish <Name>`) re-finishes stored sounds from `SourceArt`. A name holds one sound, so importing it as the other kind fails with `audio.asset_exists`. (#252)

### Changed

- `import_audio` now finishes sound effects and music by default, so the `game/assets/Audio/` copy no longer matches the stored WAV byte for byte. Pass `finish: false` (or `--no-finish`) to import the stored WAV unchanged, as before. (#252)

## [0.28.1] - 2026-11-19

### Fixed

- Make every texture-gen map pass the bake seam rule, and stop `texture seamless` from worsening images that already tile (#238)

## [0.28.0] - 2026-11-19

### Added

- Clip names are per rig, so one .blend can hold several rigged characters that each have their own `Idle`: an action named `<Clip>@SK_<Name>` exports as clip `<Clip>`, built-in and library clip import install `<Clip>@SK_<Name>` and replace only that rig's action, and finalize stops with `finalize.clip_rig_mismatch` or `finalize.clip_name_duplicate` when an action's suffix names another rig or two actions give one clip. Unsuffixed actions export as before. (#233)

## [0.27.1] - 2026-11-19

### Fixed

- Let finalize fix or tolerate a millimetre-scale pivot.bottom_center offset on rigged meshes (#244)

## [0.27.0] - 2026-11-19

### Added

- The `/generate-audio` skill and a `PreToolUse` hook for ElevenLabs audio generation: each sound-effect, music, or speech call runs one take (`generations_count: 1`, other values denied), music is instrumental unless vocals with lyrics are requested, and prompts come only from the request and the design docs. `docs/mcp/elevenlabs.md` documents the rules. (#242)

## [0.26.0] - 2026-11-19

### Changed

- **BREAKING CHANGE:** The engine target is now Godot 4 (latest stable, never pinned) instead of Unreal Engine, driven only by `godot --headless` with no live-editor bridge. Consumers keep their Godot project in `game/`, and `/convert-to-godot` migrates an existing Unreal consumer project. (#249)
- Finalize ends in `import_godot` instead of `import_ue`: each variant exports as `<Name>.glb` into `game/assets/<Category>/<Name>/{Desktop,Mobile}/` with `nmg-asset.json` in both folders, `godot --headless --import` runs, and a headless probe checks mesh names, triangle counts, material slots and bounds (`import_godot.*` error codes). Animation clips import as animation libraries, terrain becomes LOD'd `.glb` chunks plus a `.tscn` with `HeightMapShape3D` collision, and material variants are listed from finalize-written files without starting an engine. (#249)
- `import_audio` imports sound effects as `AudioStreamWAV` and music as Ogg Vorbis `AudioStreamOggVorbis` (encoded with ffmpeg), and `/design` scaffolds regions as `.tscn` scenes, missions as `NmgMissionDefinition` resources and systems as component scripts. (#249)
- `/ship` exports every target (`macos`, `ios`, `android`, `windows`, `web`) through Godot export presets after `godot --import` (so a fresh clone has its class cache), a script check, the project tests and the mobile budget gate; Windows exports locally and the web build warns above 38 MB. (#249)
- `/onboard-consumer` creates `game/project.godot`, installs the `addons/nmg_game_dev` add-on and `export_presets.cfg` with per-variant export filters, installs only the Blender SessionStart hook, and reports the Godot and ffmpeg binaries. (#249)

### Added

- The `addons/nmg_game_dev` Godot runtime add-on (`NmgAssets.resolve_variant_path`, `NmgMissionDefinition`, the terrain splat shader) with a headless test runner, and the `gate-godot-headless` validation. (#249)
- `/convert-to-godot` (`python -m nmg_game_dev.convert`) re-finalizes every asset from its Blender source, imports audio, re-scaffolds the design backlog, replaces the Unreal hooks, writes `godot-conversion-report.md`, resumes after a partial failure, and deletes the Unreal project only after every item converts. (#249)
- `NmgVariantScene` in the add-on loads a split asset's Desktop or Mobile scene at run time and previews the Desktop variant in the editor without saving it; `/design` uses it for a region's terrain, so mobile and web builds keep their terrain. `/convert-to-godot` takes `--models-dir`, and every headless Godot run is bounded by `NMG_GODOT_TIMEOUT_S` (default 900 s) so a stalled Godot fails with a remediation instead of hanging. (#249)

### Removed

- The UE plugin, the `unreal` MCP server entry, VibeUE installation, the Unreal launcher, build and smoke scripts, the dogfood UE fixture, the `gate-ue-compile` validation and its extension. A repository test keeps Unreal references out. (#249)

### Migration Notes

- Run `/convert-to-godot` in a clean git working tree of an existing consumer project; use `--dry-run` first to see every planned conversion and deletion. C++ under `Source/`, `.umap` levels and `.uasset` files finalize did not produce are listed in `godot-conversion-report.md` for a manual port. (#249)
- Install Godot 4 (or set `GODOT_BIN`) and ffmpeg (or set `FFMPEG_BIN`); `UE_ROOT`, `UE_PROJECT`, `UE_MCP_PORT` and the `WINDOWS_BUILD_*` variables are no longer read. (#249)
- `FinalizeResult.desktop_content_path` and `mobile_content_path` become `desktop_resource_path` and `mobile_resource_path` (`res://` paths), `pie_mode` and `pie_wait_seconds` are gone, and the audio result keys `unreal_asset` and `imported_to_unreal` become `godot_asset` and `imported_to_godot`. Cached `import_ue` entries are not reused. (#249)

## [0.25.5] - 2026-11-19

### Fixed

- Bake each tiling material alone on its tile, so the asset no longer darkens the tile's AO and fails the seam check (#240)

## [0.25.4] - 2026-11-19

### Fixed

- Make mesh cleanup recalculate normals the way the geometry.normals check judges them (#232)

## [0.25.3] - 2026-11-12

### Fixed

- Build the UE compile gate with the default toolchain again (drop -NoUBA) (#227)

## [0.25.2] - 2026-11-12

### Fixed

- Restore the two-second return bound in the launcher detach scenarios (#226)

## [0.25.1] - 2026-11-12

### Fixed

- Reconcile CHANGELOG release sections after parallel delivery and guard their structure with a test (#223)

## [0.25.0] - 2026-11-12

### Changed

- Add a terrain asset class that finalizes Blender heightfields into Unreal Landscapes (#154)

## [0.24.0] - 2026-11-12

### Added

- Export and import rigged-character animation clips through finalize (#138)

### Changed

- Add a reduce-to-budget step that bakes a generated high-poly asset onto an in-budget mesh (#139)
- Add batch finalize with lock wait, Unreal MCP timeout retry, and a PIE preflight (#149)

### Fixed

- Rebuild the committed M_NmgORM master material headlessly so it carries the Tint parameter (#204)
- Judge launcher detach in the scaffold scenarios by process state, not a 2-second wall clock (#215)

## [0.23.0] - 2026-11-11

### Added

- Let one finalized asset declare several material variants (#148)

### Changed

- Report sample locations in geometry contract findings (#153)
- Add a built-in procedural clip library to import_animations (#136)

### Fixed

- Fail import_ue when Unreal refuses to rename or consolidate an imported asset (#203)
- Fix texture job queue: duplicate batch outputs, orphaned running jobs, and runner log location (#211)

## [0.22.0] - 2026-11-11

### Changed

- Add optional ElevenLabs sound-effect and music generation that imports into Unreal (#155)
- Make texture generation work from the plugin root and queue or batch texture jobs (#143)

### Fixed

- Fix naming collisions that pass validate and fail after the bake (#142)
- Fix contract UV overlap validation hanging for hours on stacked UVs (#133)
- Build the UE compile gate without UBA so parallel worktrees don't corrupt each other's objects (#202)

## [0.21.5] - 2026-11-11

### Fixed

- Fix geometry.normals rejecting correctly facing open surfaces on environment pieces (#144)
- Fix the Blender test runner repointing the user's Blender add-on link and racing across worktrees (#189)

## [0.21.4] - 2026-11-11

### Changed

- Add a contact sheet for reviewing generated tiling textures (#152)

### Fixed

- Fix plugin.session-smoke failing when the Herdr window is too short to show every /mcp server (#193)
- Fix import_ue failing multi-part static imports because UE 5.8 reports only the first mesh on the import task (#141)

## [0.21.3] - 2026-11-11

### Changed

- Add estimate_landmarks to propose rig_humanoid landmarks from the mesh (#137)
- Measure texel density per material slot and exempt trim-atlas and flat-colour slots (#151)

### Fixed

- Fix import_ue failing the Mobile variant of static assets that export as an LOD group (#146)
- Fix the tiling seam check rejecting high-frequency textures that tile correctly (#147)

## [0.21.2] - 2026-11-11

### Fixed

- The `variants` step cleans every Mobile mesh it produces with the same routine Desktop cleanup uses, so decimated LODs no longer fail the contract's zero-area, loose, normals, and pivot rules or the re-import triangle count. Desktop cleanup also removes non-manifold-edge and duplicate faces, and the Mobile variant is re-seated on the world origin after decimation (#140)
- Fix Meshy a-pose arm raise destroying legs on stylized characters (#135)
- Fix import_ue importing static meshes at 1/100 scale on UE 5.8 (#145)
- Honour nmg-budgets.json Desktop overrides in contract validation (#134)
- Fix start-unreal-mcp.sh rebuilding plugins on every launch and failing to relaunch the editor after a config change (#150)

## [0.21.1] - 2026-11-02

### Fixed

- Blender asset work routes to `/model-asset` without being asked: the skill's description names its trigger, the nmg-game-dev block in `CLAUDE.md` and `AGENTS.md` tells the agent to run it for Blender asset authoring and editing (a re-run of `/onboard-consumer` refreshes the block in place), and the plugin's `PreToolUse` hook (`hooks/hooks.json`) reminds the agent once per session before the first `execute_blender_code` call. Scene inspection and `/finalize-asset` runs are exempt (#130)

## [0.21.0] - 2026-11-01

### Added

- `/model-asset` skill models an asset freeform in Blender through the Blender MCP: it plans in metres, blocks out, runs the spatial inspection and multi-view review renders, and fixes blocking findings until they pass, with no approval waits. The add-on's `inspect_core.inspect_asset` reports each part's world bounds, floating parts, interpenetration, non-manifold edges, and Desktop triangle headroom, and the `nmggamedev.inspect_spatial` operator exposes the same report. Reference: `docs/skills/model-asset.md` and `skills/model-asset/references/blender-api.md`. (#127)

## [0.20.0] - 2026-11-01

### Changed

- Configure Git LFS for binary assets during consumer onboarding (#122)

## [0.19.0] - 2026-10-31

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
