# Design: Replace Unreal Engine with Godot 4 and convert existing consumer projects

**Issue**: #249
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Overview

A new `src/nmg_game_dev/godot/` package becomes the only engine boundary. It resolves the Godot binary, runs `godot --headless` through an injectable runner, and parses the `NMG_RESULT {json}` lines that GDScript probes print. It also writes Godot text resources (`.tscn`, `.tres`, `.import`, `export_presets.cfg`) directly from Python. These callers move onto it from the Unreal MCP: finalize (`import_godot`, `import_anims`, terrain), audio, material-variant listing, `/design` scaffolding, `/ship`, and `/onboard-consumer`. The Blender exporters switch from FBX to `.glb`. A GDScript runtime add-on replaces the UE plugin. `/convert-to-godot` composes onboarding, finalize, audio, and scaffold to migrate a consumer. Every Unreal artifact is then deleted, and a repository guard keeps them out.

## Architecture

### Godot boundary — `src/nmg_game_dev/godot/`

| Module | Contents |
|--------|----------|
| `binary.py` | `resolve_godot(env=os.environ, which=shutil.which) -> Path`: `GODOT_BIN` (must be executable), then `which("godot")`, then `/Applications/Godot.app/Contents/MacOS/Godot`. Otherwise raises `PipelineError("godot.not_found", …, remediation="Install Godot 4 (latest stable) or set GODOT_BIN to its executable.", stage="godot")`. |
| `runner.py` | `GodotRunner` Protocol: `run(args: Sequence[str], *, project: Path, timeout: float \| None = None) -> CommandResult` (`returncode, stdout, stderr`). `SubprocessGodotRunner(binary: Path)` runs `[binary, "--headless", "--audio-driver", "Dummy", "--path", project, *args]`. Helpers: `import_project(runner, project)` runs `["--import"]` and raises `import_godot.import_failed` when the exit code is non-zero or any output line starts with `ERROR:`, putting the first such line in the message. `run_probe(runner, project, script, params) -> dict` writes `params` to a temp JSON file, runs `["-s", str(script), "--", params_path]`, and returns `parse_nmg_result(stdout, error_code=...)`. |
| `result.py` | `parse_nmg_result(output: str, *, error_code: str) -> dict`: moved from `unreal/import_asset.py` without the VibeUE envelope decoding. It returns the last `NMG_RESULT ` line's JSON; a missing or malformed line raises `error_code`. |
| `project.py` | `find_project(export_root) -> Path`: the nearest ancestor of `export_root` holding `project.godot`, else `import_godot.project_missing`. `res_path(project, path) -> str` builds `res://…`. Also project.godot key helpers: read, `ensure_keys(text, required) -> (text, added, drifted)`, and a minimal INI-style section/key writer for Godot `ConfigFile` text. |
| `gd/probe_asset.gd`, `gd/probe_anims.gd`, `gd/probe_terrain.gd`, `gd/probe_audio.gd` | `extends SceneTree` probes. Each reads the params JSON path after `--`, loads resources, prints exactly one `NMG_RESULT {json}` line, and calls `quit(0)`. |
| `presets.py` | `PRESETS = {"macos": "macOS", "ios": "iOS", "android": "Android", "windows": "Windows Desktop", "web": "Web"}`. `render_export_presets(project_name) -> str` writes `[preset.N]` / `[preset.N.options]` sections. Mobile and web presets get `exclude_filter="assets/*/Desktop/*"`, desktop presets get `exclude_filter="assets/*/Mobile/*"`. Web sets `variant/thread_support=false`. Windows sets `binary_format/embed_pck=true`. macOS sets `codesign/codesign=0`, because ship signs. Android sets `gradle_build/use_gradle_build=true` and `gradle_build/export_format=1` (AAB). |

### Finalize

- `pipeline/steps.py`: `STEP_ORDER = ("validate","bake","variants","export","export_anims","reimport","import_godot","import_anims")`; `StepKind = Literal["blender","godot"]`; `import_godot` replaces `import_ue` in `STEPS` and `DEPENDS`; `_STEP_VERSION` goes from `"4"` to `"5"`. A new key salt plus the new step name mean no cached `import_ue` entry can satisfy `import_godot`. The `import_godot` settings hash covers collection, category, and export_root. `ue_destination` and `desktop_skeleton_path` are replaced by `variant_dir(req, variant)` and `glb_path(req, variant)` (`<export_root>/<Category>/<Name>/<Variant>/<Name>.glb`).
- `pipeline/request.py`: drops `pie_mode` and `pie_wait_seconds`, along with their tools.json and CLI inputs. The PIE preflight and the `NMG_GAME_DEV_UE_RETRIES` retry loop are removed with `unreal/`.
- `pipeline/engine.py`: the `UnrealPythonRunner` protocol is replaced by `godot: GodotRunner | None` in `FinalizeClients`. `_run_import` resolves the binary (`godot.not_found`), finds the project, calls `godot.import_asset.import_variants(...)` (mesh) or `godot.terrain.import_terrain(...)` (terrain), and returns outputs `{desktop_resource_path, mobile_resource_path, imports:{Desktop,Mobile}}`. `FinalizeResult.desktop_content_path` and `.mobile_content_path` are renamed `desktop_resource_path` and `mobile_resource_path` (`res://assets/<C>/<N>/<V>/<N>.glb`).
- `godot/import_asset.py`:
  1. Writes material-variant materials (see Data).
  2. Runs `import_project`.
  3. Runs `probe_asset.gd` once per variant with `{glb: res path}`. The probe instantiates the `PackedScene` and walks every `MeshInstance3D`, returning `{meshes:[{name, tris, material_slots, bounds:{min,max}}]}`. `tris` is the sum over surfaces of index count / 3 (vertex count / 3 when a surface has no indices). `bounds` is the node-space AABB transformed to the scene root.
  4. Compares the probe result with the variant's `nmg-asset.json` `meshes`: same names, equal `tris`, equal `material_slots`, and bounds within 0.001 m. Any difference raises `import_godot.mismatch`, naming the mesh and field.
- Blender side (`plugins/nmg-game-dev-blender-addon/`):
  - `variants_core/export.py` replaces `bpy.ops.export_scene.fbx` with `bpy.ops.export_scene.gltf(export_format="GLB", export_yup=True, export_apply=True, use_selection=True)` and writes `<Variant>/<Name>.glb`. Rigged exports add `export_skins=True, export_animations=False`. The rigged Mobile `_LOD1`/`_LOD2` exports are removed, because Godot's import-time `meshes/generate_lods` produces LODs. The baked `T_<Name>_<Part>_{BC,N,ORM}.png` set is still written beside each `.glb`.
  - `variants_core/sidecars.py` writes `nmg-asset.json` into **both** `Desktop/` and `Mobile/`: `{class, tris, max_texture_px, materials, meshes:[{name, tris, material_slots, bounds:{min:[x,y,z], max:[x,y,z]}}]}`. Bounds are in Godot space: Blender `(x, y, z)` becomes `(x, z, -y)`, in metres. The `nmg-variants.json` paths become `Desktop/<Name>.glb` and `Mobile/<Name>.glb`.
  - `finalize_core/anims.py` exports each clip as `Animations/A_<Name>_<Clip>.glb` (armature only, `export_animations=True`, the single action, `export_force_sampling=True`). Clip hashing and per-clip caching are unchanged.
- `godot/anims.py` (called from `pipeline/anims.py::run_import_anims`) works on changed clips only:
  1. Writes `A_<Name>_<Clip>.glb.import` with `importer="animation_library"` before `import_project`.
  2. Runs `probe_anims.gd`, which loads each `res://…/Animations/A_<Name>_<Clip>.glb` as an `AnimationLibrary` and reports `{clips:{name:{animation, frame_count}}}` (frame count = `round(length * fps)`).
  - A wrong or absent clip raises `import_anims.clip_mismatch`; a probe failure raises `import_anims.failed`.
  - `compatible_with` keeps its meaning: every bone track in the clip must exist in each compatible asset's Desktop skeleton. The probe reads the `Skeleton3D` bone names from that asset's Desktop `.glb`; a missing bone raises `finalize.skeleton_mismatch` and a missing asset raises `finalize.skeleton_not_found`.
- Terrain:
  - `terrain_core/export.py` cuts the variant heightfield into square chunks of 63 quads (`CHUNK_QUADS = 63`, which divides every `VALID_SIZES - 1`). It writes `<Variant>/<Name>_Chunk_<row>_<col>.glb`, plus a `T_<Name>_Splat.png` RGBA weightmap (layer *i* in channel *i*; more than 4 layers raises `variants.terrain_layers_unsupported`) and the per-layer `T_<Name>_<Layer>_{BC,N,ORM}.png`. The 16-bit `T_<Name>_Height.png` stays for the reimport check.
  - `godot/terrain.py` writes `<Variant>/<Name>.tscn`. The root is a `Node3D` named `<Name>`. It has one instance per chunk `.glb`, and a material override `ShaderMaterial` using `res://addons/nmg_game_dev/terrain/nmg_terrain.gdshader` with the splat and layer textures. It also has a `StaticBody3D` with a `CollisionShape3D` whose `HeightMapShape3D` has `map_width = map_depth = heightmap_px` and `map_data` = the decoded heights in metres. That shape is scaled `(spacing_m, 1, spacing_m)` and centred like the mesh.
  - Godot generates the chunk LODs on import (`meshes/generate_lods=true`).
  - `probe_terrain.gd` loads the scene and reports `{chunks, height_min, height_max}` from `map_data`, and the union of the chunk AABB Y extents.
  - Either range differing from the sidecar's `height_min_m`/`height_max_m` by more than 0.05 m raises `import_godot.terrain_height_mismatch`. A missing chunk raises `import_godot.mismatch`.

### Audio — `src/nmg_game_dev/audio/`

`core.import_audio(file, name, kind, loop=False, *, project_root=None, godot: GodotRunner | None = None)`:
1. Validates the request and stores `SourceArt/Audio/<SFX|Music>/<Name>.wav` as today.
2. Calls `godot_import.import_wav(project_root, wav, name, loop, runner)`. That function copies the WAV to `game/assets/Audio/<Name>.wav` (an existing target raises `audio.asset_exists`) and writes `<Name>.wav.import` with `importer="wav"`, `edit/loop_mode=2` (Forward), `edit/loop_begin=0` and `edit/loop_end=-1` when `loop` is true, otherwise `edit/loop_mode=1`.
3. Runs `import_project` and `probe_audio.gd`. The probe must report class `AudioStreamWAV` and the expected `loop_mode`, otherwise it raises `audio.import_failed`.

`godot.not_found` keeps today's soft path: the result has `imported_to_godot: false` and a `warning`. Result keys rename `unreal_asset` to `godot_asset` (`res://assets/Audio/<Name>.wav`) and `imported_to_unreal` to `imported_to_godot`. `import_wav` is public so conversion can import WAVs that are already stored.

### Material variants

During `import_godot`, `godot/import_asset.py` writes `<Variant>/M_<Name>_<Part>_<VariantName>.tres` for each declared variant. Each file is a `StandardMaterial3D` with `albedo_texture` set to the variant BC, `normal_texture` to the base N, ORM through `orm` texture channels, and `albedo_color` set to the `Tint` parameter (white by default). The declaration then records `material_resource` in `nmg-variants.json`.

`finalize/mcp_tools.list_material_variants(*, category, collection, export_root=None)` reads only `<export_root or $CLAUDE_PROJECT_DIR/game/assets>/<Category>/<Name>/nmg-variants.json`. It returns `[{name, material, desktop, mobile}]` sorted by `(material, name)`, where `desktop`/`mobile` is the `res://` path of the `.tres` when that file exists, else `null`. A missing or invalid sidecar raises `finalize.material_variants_failed`. It never runs Godot.

### Design scaffold — `src/nmg_game_dev/design/scaffold.py`

`run_scaffold(root, report, *, statuses=None)` writes text files and takes no client:
- **Region:** `game/levels/<N>/<N>.tscn` (`format=3`). It contains a `Node3D` root, `Marker3D` `PlayerSpawn`, a `DirectionalLight3D`, and a `WorldEnvironment` with an `Environment` sub-resource. When the region's terrain names a terrain entry whose `game/assets/<Category>/<T>/Desktop/<T>.tscn` exists, the scene instances it as an `ext_resource`. Otherwise it gets a ground: a `MeshInstance3D` with a 200 m `PlaneMesh` and a `StaticBody3D`/`BoxShape3D`.
- **Mission:** `game/missions/<N>.tres`, a `[gd_resource type="Resource" script_class="NmgMissionDefinition" format=3]` whose `ext_resource` script is `res://addons/nmg_game_dev/nmg_mission_definition.gd`. It sets `mission_name`, `act`, `region`, `depends_on` (`Array[StringName]`) and `design_doc_path`.
- **System:** `game/systems/<N>/<snake_n>.gd` with `class_name <N>Component` / `extends Node`.

An existing file reports `unchanged` and is still marked `scaffolded`. An unknown terrain reference keeps the `design.unknown_reference` error line with no write, and the run continues. An `OSError` on one entry gives a `design.scaffold_failed` line and `report.failed`, and the loop continues. A missing `game/project.godot` raises `design.godot_project_missing` (exit 1). `statuses` filters entries by backlog status; conversion passes `{"scaffolded"}`. The CLI drops `--url` and exit code 2.

### Runtime add-on — `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/`

| File | Contents |
|------|----------|
| `plugin.cfg` | name `nmg-game-dev`, `version` = `VERSION`, script `plugin.gd` |
| `plugin.gd` | `@tool` `EditorPlugin`: registers the `NmgAssets` autoload in `_enter_tree` and removes it in `_exit_tree` |
| `nmg_assets.gd` | `resolve_variant_path(path: String) -> String` calls `resolve_variant_path_for(path, OS.has_feature("mobile") or OS.has_feature("web"))`. The well-formed shape is `<dir>/<Folder>/<File>` with `File.get_basename() == Folder`, which returns `<dir>/<Folder>/<Mobile\|Desktop>/<File>`. A path is malformed when it is empty, already contains `/Desktop/` or `/Mobile/`, has no parent folder, or its stem ≠ folder; it is returned unchanged after `push_warning`. |
| `nmg_mission_definition.gd` | `class_name NmgMissionDefinition extends Resource` with `@export` `mission_name: String`, `act: int`, `region: StringName`, `depends_on: Array[StringName]`, `design_doc_path: String` |
| `terrain/nmg_terrain.gdshader` | Four-layer splat shader |
| `tests/run_tests.gd`, `tests/test_nmg_assets.gd`, `tests/test_mission_definition.gd` | `extends SceneTree` runner. It discovers `test_*` methods, prints `N passed, M failed`, and calls `quit(1)` on any failure. |

### Ship — `src/nmg_game_dev/ship/`

CLI: `python -m nmg_game_dev.ship <target> --project <game/project.godot> [--release-dir DIR] [--dry-run]`. `release-dir` defaults to `<project.parent.parent>/release`.

`targets.py`:
- `Platform = Literal["macos","ios","android","windows","web"]`; groups are `desktop=(macos,windows)`, `mobile=(ios,android)`, and `all=(macos,windows,ios,android,web)`.
- `REQUIRED_ENV`:
  - macOS: the notarization variables as today.
  - iOS: `IOS_PROVISIONING_PROFILE`, `IOS_TEAM_ID`.
  - Android: `ANDROID_KEYSTORE`, `ANDROID_KEYSTORE_PASSWORD`.
  - Windows and web: none.

`runner.run_ship(target, project, release_dir, dry_run, env, *, godot: GodotRunner | None, scripts_dir)` order:
1. Expand the target, check the project, run env preflight, and resolve the signing identity for macOS. A dry run without a Godot binary prints the literal `godot`.
2. `ship.script_check_failed` — `--check-only -s res://<path>` for every `.gd` under the project, skipping `.godot/`.
3. `ship.tests_failed` — `-s res://tests/run_tests.gd` when that file exists.
4. Mobile budget gate for any of ios, android, or web. `quality/mobile_budgets.check_mobile_budgets(assets_root, overrides_path)` reads `game/assets/**/Mobile/nmg-asset.json` and `<consumer root>/nmg-budgets.json`. It also runs in a dry run.
5. For each platform:
   - iOS first patches the iOS preset's `application/app_store_team_id` (`IOS_TEAM_ID`) and `application/provisioning_profile_uuid_release` in `export_presets.cfg`. The UUID comes from `security cms -D -i <profile>`, and the file is restored byte-for-byte in a `finally`.
   - Android runs `--install-android-build-template` first when `game/android/build/` is missing. It passes `GODOT_ANDROID_KEYSTORE_RELEASE_{PATH,USER,PASSWORD}` from `ANDROID_KEYSTORE`, `ANDROID_KEYSTORE_ALIAS` (default `upload`) and `ANDROID_KEYSTORE_PASSWORD`, only in the child environment and never printed.
   - Export with `--export-release "<preset>" <out>`. Outputs: `release/macos/<App>.app`, `ios/<App>.ipa`, `android/<App>.aab`, `windows/<App>.exe`, `web/index.html`. `<App>` is `application/config/name` with non-alphanumerics removed (fallback `Game`). A non-zero exit raises `ship.export_failed`.
   - macOS then runs the existing `sign-macos.sh` and `notarize-macos.sh`.
   - Web prints `WARNING [ship.web_pack_large]: index.pck is <n> MB, over 38 MB` when `index.pck` > 38 × 1024 × 1024 bytes.
6. Write `RELEASE-NOTES.md` (existing `release_notes.py` and `artifact_sha256`; the web folder is hashed as a folder).

Dry run prints every Godot, sign and notarize command as `DRY-RUN: <argv>`, with secrets shown as `***`. It runs no Godot and writes `release/<platform>/DRY-RUN.txt`.

`scripts/ship-smoke.sh` dry-runs `all` against `tests/godot/fixture/project.godot`.

### Onboard — `src/nmg_game_dev/onboard/`

Steps, in order:
1. `scripts/start-blender-mcp.sh`
2. `settings_hooks` (the template has only the Blender hook)
3. `asset_contract`
4. `design_contract`
5. `design_dir`
6. `agent_instructions:*`
7. `godot_project`: create `game/project.godot` with `config/name`, `rendering/renderer/rendering_method.mobile="gl_compatibility"`, `rendering/renderer/rendering_method.web="gl_compatibility"`, `[editor_plugins] enabled=PackedStringArray("res://addons/nmg_game_dev/plugin.cfg")` and `[autoload] NmgAssets="*res://addons/nmg_game_dev/nmg_assets.gd"`. On an existing file, missing keys are added (`refreshed`); a key with a different value is `drift` and is left alone unless `--refresh`.
8. `godot_addon`: `sync_tree` from `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev` to `game/addons/nmg_game_dev`, excluding `tests/`.
9. `export_presets`: written from `render_export_presets` when missing; a byte difference is `drift` unless `--refresh`.
10. `godot_binary`: `unchanged` "found at <path>", or `skipped` with remediation "Install Godot 4 or set GODOT_BIN".
11. `blender_addon`
12. `texture_models`
13. `texture_env`
14. `gitignore_env`: also ensures `game/.godot/` is ignored.
15. `gitattributes_lfs`: the pattern list drops the Unreal binaries and adds `*.glb`.
16. `git_lfs_hooks`

The `--uproject` flag, the project-file resolution codes, and `onboard/unreal.py` are removed. `--game-dir` defaults to `game`.

### Convert — `src/nmg_game_dev/convert/` (exempt from the AC14 guard)

| Module | Contents |
|--------|----------|
| `__main__.py` | `python -m nmg_game_dev.convert [--project DIR] [--dry-run] [--json]`. Exit 0 = all converted, 1 = a guard or item failure, 2 = argument error. |
| `plan.py` | `discover(root) -> ConversionPlan`. **Assets:** every `Content/<Category>/<Name>/Mobile/nmg-asset.json`, with `asset_class` from its `class`, and the source = the single `SourceArt/**/<Name>.blend` compared case-insensitively. **Audio:** `SourceArt/Audio/SFX/*.wav` (loop false) and `SourceArt/Audio/Music/*.wav` (loop true). **Scaffolds:** backlog entries of type region/mission/system with status `scaffolded`. **Manual port:** `Source/**`, `Content/**/*.umap`, and every `Content/**/*.uasset` outside a finalized `Content/<Category>/<Name>/` folder. **Deletions:** `Content/`, `Source/`, `Config/`, `Plugins/`, `*.uproject`, `scripts/start-unreal-mcp.sh` (only those that exist). |
| `state.py` | `game/.nmg-convert.json` = `{"version": 1, "done": ["asset:<Category>/<Name>", "audio:<Kind>/<Name>", "scaffold:<type>/<Name>"]}`, written after each item succeeds |
| `report.py` | Writes `godot-conversion-report.md` with sections Converted, Failed (item, code, remediation), Manual port (path, reason), and Deletions (done or "kept: N items failed") |
| `runner.py` | `run_convert(root, *, dry_run, git: Runner, onboard, finalize, import_wav, scaffold, out)`. The collaborators default to `run_onboard`, `pipeline.finalize` (a `FinalizeRequest` with `blend=<source>`, `collection=<Name>`, `category`, `asset_class`, `export_root=game/assets`), `audio.godot_import.import_wav`, and `design.scaffold.run_scaffold(statuses={"scaffolded"})`. |

`run_convert` flow:
1. **Guards, before any write.** `convert.not_unreal` when the root has no `*.uproject`. When no state file exists, `convert.dirty_worktree` when `git status --porcelain` prints anything. A state file means the run is a resume.
2. `godot.not_found` / `finalize.blender_not_found` preflight.
3. A dry run prints `PLAN convert <item>` and `PLAN delete <path>` lines and returns without writing.
4. Onboard, then each item not in `done`, recording failures with their `PipelineError` code and remediation.
5. Replace hooks and settings: remove every SessionStart hook whose command contains `start-unreal-mcp.sh` (dropping emptied groups) and every `env` key starting with `UE_` from `.claude/settings.json`.
6. Write the report.
7. Only with zero failures: `git rm -r -q -- <deletions>`, then remove any untracked remainder of those paths.

### Repository changes

| Kind | Paths |
|------|-------|
| Removed | `plugins/nmg-game-dev-ue-plugin/`; `src/nmg_game_dev/unreal/`; `src/nmg_game_dev/pipeline/clients/unreal_mcp.py`; `src/nmg_game_dev/audio/unreal_import.py`; `src/nmg_game_dev/onboard/unreal.py`; `scripts/start-unreal-mcp.sh`, `install-vibeue.sh`, `smoke-unreal-mcp.py`, `run-ue-tests.sh`, `build-{macos,ios,android,windows}.sh`, `verify-cook-manifest.sh`, `scripts/unreal/`; `fixtures/` (the UE dogfood project); `tests/ue-automation/`; `steering/extensions/ue-compile.mjs`; `docs/mcp/unreal.md`; the UE-only tests and fakes (`tests/start_unreal_fakes.py`, `tests/unit/fake_unreal*.py`, `tests/unit/test_unreal_*.py`, `test_ue_*.py`, `test_start_unreal_mcp.py`, `test_smoke_unreal_mcp.py`, `test_pie_preflight.py`, `test_build_master_material.py`, and the `import_ue_*`, `start_unreal_*`, `ue_plugin_skeleton`, `master_material` features with their bindings) |
| Rewritten | The `.mcp.json` `unreal` server is removed. `steering/manifest.json` loses `gate-ue-compile` and the `project.ue-compile` extension and gains `gate-godot-headless`. |
| Added | `gate-godot-headless`: `builtin.command`, program `scripts/run-godot-tests.sh`, env `["GODOT_BIN"]`, changed_paths `plugins/nmg-game-dev-godot-addon/**`, `src/nmg_game_dev/godot/**`, `tests/godot/**`, `scripts/run-godot-tests.sh` |
| Updated | `gate-ship-smoke` includes become `skills/ship/**`, `src/nmg_game_dev/ship/**`, `scripts/sign-macos.sh`, `scripts/notarize-macos.sh`, `scripts/ship-smoke.sh` |

`scripts/run-godot-tests.sh`:
1. Resolves Godot from `GODOT_BIN`, then `godot` on PATH. Otherwise it downloads the latest stable release: the tag comes from `https://api.github.com/repos/godotengine/godot/releases/latest`, and the asset is `Godot_v<ver>_macos.universal.zip` on Darwin or `Godot_v<ver>_linux.x86_64.zip` on Linux. It unpacks to `.cache/godot/<ver>/` (git-ignored) and reuses that copy on later runs.
2. Copies `tests/godot/fixture/` and the add-on into a `mktemp -d` project and runs `--import`, which must exit 0 with no `ERROR:` lines.
3. Runs the add-on `tests/run_tests.gd`.
4. Runs `probe_asset.gd` on the fixture `Crate.glb` and compares the result with `tests/godot/fixture/expected-probe.json`.

`tests/unit/test_no_unreal_references.py` lists tracked files with `git ls-files -z`. It skips `specs/`, `CHANGELOG.md` and `EXEMPT` (the eight entries in AC14), then checks each path and each text body against case-insensitive `unreal|vibeue|\.uproject|\.uasset` and case-sensitive `\bUE\b`. A second test asserts that `EXEMPT` equals that exact list and that every entry exists.

## API / Interface Changes

| Interface | Input | Output / Error | Behavior |
|-----------|-------|----------------|----------|
| finalize step `import_godot` (MCP `finalize_asset`/`run_finalize_step`, CLI `--step import_godot`) | `FinalizeRequest` without `pie_mode`/`pie_wait_seconds` | `desktop_resource_path`, `mobile_resource_path`; `godot.not_found`, `import_godot.project_missing`, `import_godot.import_failed`, `import_godot.mismatch`, `import_godot.terrain_height_mismatch` | Headless import plus probe |
| MCP `list_material_variants` | `category`, `collection`, optional `export_root` | `[{name, material, desktop, mobile}]`; `finalize.material_variants_failed` | File read only |
| MCP `import_audio` / `python -m nmg_game_dev.audio import` | unchanged (`--url` removed) | `godot_asset`, `imported_to_godot` | AudioStreamWAV import |
| `python -m nmg_game_dev.design scaffold` | `--project` | exit 0/1; `design.godot_project_missing` | Writes Godot files |
| `python -m nmg_game_dev.ship` | `<target> --project game/project.godot` | `ship.script_check_failed`, `ship.tests_failed`, `ship.export_failed`, existing budget/sign/notarize codes | Godot export |
| `python -m nmg_game_dev.onboard install` | `--consumer`, `--game-dir` (no `--uproject`) | step report | Godot consumer setup |
| `python -m nmg_game_dev.convert` / `/convert-to-godot` | `--project`, `--dry-run`, `--json` | exit 0/1/2; `convert.dirty_worktree`, `convert.not_unreal`, `convert.source_missing`, `convert.source_ambiguous` | Conversion |
| `NmgAssets.resolve_variant_path(path)` | `String` | `String` | Variant routing |

## Data / Storage Changes

- `nmg-asset.json` is now written to both variant folders and adds `meshes` (names, tris, material slots, Godot-space bounds).
- `nmg-variants.json` paths point at `.glb`, and its material variants carry `material_resource`.
- The finalize cache salt changes from `"4"` to `"5"`.
- `game/.nmg-convert.json` holds the conversion resume state.
- `.gitignore` adds `.cache/godot/` and drops the UE build-output block.
- The versioning table replaces the `.uplugin` row with `plugins/nmg-game-dev-godot-addon/addons/nmg_game_dev/plugin.cfg` `version`.

## Alternatives Considered

| Option | Decision | Reason |
|--------|----------|--------|
| Godot MCP / live editor bridge | Rejected | The issue's out-of-scope list excludes it; headless CLI keeps every stage file-based |
| GLB with external texture URIs | Rejected | Blender's GLB writer embeds images; the contract PNG set beside each `.glb` stays the reimport-check input |
| Keep Blender-generated Mobile LOD files | Rejected | Godot generates LODs at import, per the issue's technical notes |
| Terrain3D add-on | Rejected | Out of scope; chunked meshes plus `HeightMapShape3D` need no third-party add-on |
| Blender source from a developer-written map file | Rejected | A name search resolves all 218 ghost1 assets uniquely and needs no extra file |

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #249 | 2026-11-18 | Initial feature design |
