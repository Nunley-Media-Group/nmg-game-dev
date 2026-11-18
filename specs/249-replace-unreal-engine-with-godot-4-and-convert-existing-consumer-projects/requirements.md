# Requirements: Replace Unreal Engine with Godot 4 and convert existing consumer projects

**Issue**: #249
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As a** NMG game developer and consumer-project maintainer
**I want** nmg-game-dev to finalize, scaffold, run, and ship games in Godot 4 instead of Unreal Engine, and to convert my existing Unreal-based project to Godot with one command
**So that** every pipeline stage runs headless and file-based, and my existing project keeps working on the new engine

## Background

Today finalize ends in `import_ue`. It exports FBX per variant and imports it through Unreal Python sent over the Unreal MCP (`src/nmg_game_dev/unreal/`), parsing an `NMG_RESULT {json}` line. Terrain, audio, material-variant listing and `/design` scaffolding also go through the Unreal MCP. The UE plugin ships `UNmgAssetResolver` and `UNmgMissionDefinition`. `/ship` packages through UAT, building Windows on a remote host. `/onboard-consumer` installs the UE plugin, VibeUE, and an Unreal SessionStart hook. The repository registers `gate-ue-compile`.

This change targets Godot 4, the latest stable 4.x and never pinned, driven only by `godot --headless` (`--import`, `--check-only`, `-s <script>`, `--export-release`). There is no live-editor bridge. Consumers keep their Godot project in `game/` (`game/project.godot`), and finalized assets land in `game/assets/<Category>/<Name>/{Desktop,Mobile}/`. Existing contracts carry over unchanged: `parse_nmg_result`, the `PipelineError` code-plus-remediation contract, and the content-keyed finalize cache.

## Acceptance Criteria

### AC1: Finalize lands both variants in Godot

**Given** a consumer project with a Godot project at `game/project.godot` and an authored collection that passes contract validation
**When** finalize runs every step
**Then** `game/assets/<Category>/<Name>/Desktop/` and `.../Mobile/` each contain the variant `<Name>.glb`, its textures, and `nmg-asset.json`; `godot --headless --path game --import` has run; and the `import_godot` step's headless import probe reports each variant's mesh names, triangle counts, material slots, and bounds matching the exported asset, with step order `validate → bake → variants → export → export_anims → reimport → import_godot → import_anims`

### AC2: Godot import failures stop finalize with a remediation

**Given** a Godot binary cannot be found, or the headless import reports an error, or the probe's results do not match the export
**When** finalize reaches `import_godot`
**Then** finalize fails with a stable error code (`godot.not_found`, `import_godot.import_failed`, or `import_godot.mismatch`) and a remediation line, and no later step runs

### AC3: Animation clips import per clip

**Given** a rigged asset with several animation clips
**When** finalize runs `export_anims` and `import_anims`
**Then** each clip is exported as its own `.glb` and imported into Godot as an animation library beside the Desktop and Mobile variants, and re-running one changed clip re-exports and re-imports only that clip

### AC4: Terrain becomes chunked meshes with collision

**Given** an authored terrain asset with a heightfield
**When** finalize runs
**Then** the variant folder contains LOD'd `.glb` mesh chunks and a `.tscn` scene that instances every chunk with `HeightMapShape3D` collision built from the same heightfield; when the probe's measured height range differs from the heightfield's, finalize fails with `import_godot.terrain_height_mismatch`

### AC5: Audio imports into Godot

**Given** a sound effect or music file passed to `import_audio`
**When** the import runs
**Then** the source is stored under `SourceArt/Audio/` as today; a sound effect is copied to `game/assets/Audio/<Name>.wav` and imported headless as an `AudioStreamWAV`; a music track is encoded with ffmpeg to Ogg Vorbis at `game/assets/Audio/<Name>.ogg` and imported headless as an `AudioStreamOggVorbis`, with `loop=true` when looping; and when ffmpeg cannot be found, a music import fails with `audio.ffmpeg_not_found` and a remediation line

### AC6: Material variants are listed without an editor

**Given** an asset finalized with material variants
**When** `list_material_variants` runs
**Then** it returns each variant's name and material slot per Desktop and Mobile folder, read from files finalize wrote, without starting Godot

### AC7: Design scaffolding writes Godot files

**Given** a design backlog with region, mission, and system entries
**When** `/design` scaffolds
**Then** each region becomes `game/levels/<Name>/<Name>.tscn` (a `Marker3D` player spawn, a `DirectionalLight3D`, a `WorldEnvironment`, and either a ground plane or an instance of the finalized terrain scene the region names); each mission becomes `game/missions/<Name>.tres`, an `NmgMissionDefinition` resource with `mission_name`, `act`, `region`, `depends_on`, and `design_doc_path`; each system becomes `game/systems/<Name>/<name>.gd`, a component script; existing files are never overwritten; and the unknown-terrain and per-entry failure behaviors stay as they are today

### AC8: The runtime add-on routes variants

**Given** the `addons/nmg_game_dev` add-on is enabled in a Godot project
**When** game code calls `NmgAssets.resolve_variant_path(path)`
**Then** it returns the Mobile variant path when the running platform has the `mobile` or `web` feature tag and the Desktop path otherwise; a malformed path is returned unchanged with a warning; and the add-on's headless test runner prints `N passed, M failed` and exits non-zero on any failure

### AC9: Ship exports every target through Godot

**Given** a consumer Godot project and the environment variables for the chosen target
**When** `/ship <target>` runs for `macos`, `ios`, `android`, `windows`, `web`, `desktop`, `mobile`, or `all`
**Then** it first runs `--check-only` on every `.gd` file, runs `game/tests/run_tests.gd` when it exists, and runs the mobile budget gate for `ios`, `android`, and `web`; then it exports with `godot --headless --path game --export-release <preset>`; signs and notarizes macOS; produces `.app`, `.ipa`, `.aab`, `.exe`, and a web folder under `release/<platform>/` listed with SHA-256 in `release/RELEASE-NOTES.md`; Mobile and Web presets exclude every `Desktop/` asset folder and desktop presets exclude every `Mobile/` folder; the web target uses the Compatibility renderer with no threads and warns when the `.pck` is larger than 38 MB; Windows exports locally and requires no `WINDOWS_BUILD_*` variables; and `--dry-run` prints each command with a `DRY-RUN:` prefix

### AC10: Onboarding sets up a Godot consumer

**Given** a game project with no nmg-game-dev setup
**When** `/onboard-consumer` runs
**Then** it creates `game/project.godot` when missing (Compatibility renderer for mobile and web), installs `addons/nmg_game_dev`, writes `game/export_presets.cfg` with the per-target presets and variant filters, installs only the Blender SessionStart hook, installs no Unreal or VibeUE artifacts, and reports the Godot binary and ffmpeg as found or missing; a second run reports drift and changes nothing that is already correct

### AC11: Converting an Unreal consumer to Godot

**Given** a consumer project with a `.uproject`, finalized `Content/<Category>/<Name>/{Desktop,Mobile}/` folders with `nmg-asset.json`, Blender sources in `SourceArt/`, WAVs in `SourceArt/Audio/`, a design backlog, and Unreal hooks and settings, in a clean git working tree
**When** the developer runs `/convert-to-godot`
**Then** it onboards the Godot project as in AC10, re-finalizes every asset listed by a `nmg-asset.json` from its Blender source into `game/assets/`, imports every audio file, re-scaffolds every scaffolded backlog entry, replaces the Unreal hooks and settings, writes `godot-conversion-report.md` listing each converted item and each manual-port item (C++ under `Source/`, `.umap` levels, and `.uasset` files that finalize did not produce), and only after every item converts removes `Content/`, `Source/`, `Config/`, `Plugins/`, the `.uproject`, and the Unreal scripts

### AC12: Partial conversion keeps Unreal and resumes

**Given** a conversion in which at least one asset, audio file, or scaffold fails
**When** `/convert-to-godot` finishes
**Then** no Unreal file is deleted, the report lists each failure with its error code and remediation, the command exits non-zero, and a rerun skips the items that already converted and retries only the rest

### AC13: Conversion guards and dry run

**Given** a consumer project whose git working tree has uncommitted changes, or that has no `.uproject`
**When** `/convert-to-godot` runs
**Then** it stops before writing anything with `convert.dirty_worktree` or `convert.not_unreal`; and with `--dry-run` on a valid project it prints every planned conversion and deletion and writes nothing

### AC14: Unreal is gone from nmg-game-dev

**Given** this repository after the change
**When** the repository test suite runs
**Then** a test proves that no tracked file outside `specs/`, `CHANGELOG.md`, and the exempt conversion files (`src/nmg_game_dev/convert/`, `skills/convert-to-godot/`, `docs/skills/convert-to-godot.md`, `tests/unit/convert/`, `tests/convert_fakes.py`, `tests/bdd/features/convert_to_godot.feature`, `tests/bdd/test_convert_to_godot_bdd.py`, and the guard test itself) references Unreal, UE, VibeUE, `.uproject`, or `.uasset` in its path or text; `plugins/nmg-game-dev-ue-plugin/`, the `unreal` server in `.mcp.json`, the Unreal scripts and fixtures, `steering/extensions/ue-compile.mjs`, and the `gate-ue-compile` validation are removed; and a `gate-godot-headless` validation runs the add-on tests and a fixture Godot project import

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Replace `import_ue` with `import_godot`: export `.glb` per variant into `game/assets/<Category>/<Name>/{Desktop,Mobile}/`, run headless import, and verify the result with a headless GDScript probe that emits `NMG_RESULT {json}` | Must |
| FR2 | Resolve the Godot binary from `GODOT_BIN`, then `godot` on PATH, then `/Applications/Godot.app`; when none is found, fail with `godot.not_found` and a remediation | Must |
| FR3 | Export each animation clip as its own `.glb`, import it as a Godot animation library, and re-export and re-import only clips whose content changed | Must |
| FR4 | Finalize terrain into LOD'd `.glb` chunks plus a `.tscn` with `HeightMapShape3D` collision, and keep the height-mismatch check | Must |
| FR5 | Import sound effects into `game/assets/Audio/` as `AudioStreamWAV` and music as Ogg Vorbis (`AudioStreamOggVorbis`, encoded with ffmpeg resolved from `FFMPEG_BIN`, then PATH), with loop settings on music | Must |
| FR6 | Read material variants from finalize-written files without starting Godot | Must |
| FR7 | Scaffold regions to `.tscn`, missions to `NmgMissionDefinition` `.tres`, and systems to component `.gd` files, writing text files directly and never overwriting an existing file | Must |
| FR8 | Ship the `addons/nmg_game_dev` GDScript runtime add-on (variant resolver autoload, `NmgMissionDefinition` resource class) with a headless test runner | Must |
| FR9 | Rework `/ship` around Godot export presets for macos, ios, android, windows, and web, with the pre-export gates, variant export filters, a local Windows export, the web pack-size warning, macOS signing and notarization, and dry run | Must |
| FR10 | Rework `/onboard-consumer` to create and maintain the Godot project, add-on, export presets, and Blender-only hooks | Must |
| FR11 | Add `/convert-to-godot` (skill plus `python -m nmg_game_dev.convert`) implementing conversion, reporting, resume, the dirty-tree and not-Unreal guards, dry run, and deletion only after every item succeeds; each asset's Blender source is the single `SourceArt/**/<Name>.blend` (case-insensitive), failing the item with `convert.source_missing` or `convert.source_ambiguous` otherwise | Must |
| FR12 | Rewrite the asset contract, skills, onboarding docs, MCP docs, README, and steering snippets for Godot, including `.glb` export rules, Godot LOD generation, and `import_godot.*` error codes | Must |
| FR13 | Remove the UE plugin, the Unreal MCP server entry, the Unreal and VibeUE scripts, the UE fixtures, the UE test fakes, the `gate-ue-compile` validation, and the ue-compile extension | Must |
| FR14 | Register a `gate-godot-headless` validation that uses `GODOT_BIN`, then PATH, then downloads the latest stable Godot into a git-ignored cache, and runs the add-on tests plus a fixture project import | Must |

## Out of Scope

- Porting a consumer's C++ game code, Blueprints, or `.umap` levels to Godot; these are listed in the conversion report as manual-port items.
- A live Godot editor bridge or Godot MCP server.
- Converting `.uasset` binaries directly; assets are re-finalized from their Blender sources.
- The Terrain3D add-on.
- Web hosting or deployment of the web build.
- Authenticode signing of Windows builds.
- Console targets.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #249 | 2026-11-18 | Initial feature spec |
