# Tasks: Replace Unreal Engine with Godot 4 and convert existing consumer projects

**Issue**: #249
**Date**: 2026-11-18
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Add the Godot boundary package

**File(s)**: `src/nmg_game_dev/godot/`, `tests/godot_fakes.py`, `tests/unit/godot/`
**Type**: Create
**Depends**: none
**Acceptance**:
- FR2, AC2: `resolve_godot` tries `GODOT_BIN`, then `godot` on PATH, then `/Applications/Godot.app/Contents/MacOS/Godot`, and otherwise raises `godot.not_found` with a remediation. Unit tests cover each branch.
- FR1: `SubprocessGodotRunner`, `import_project`, `run_probe`, `parse_nmg_result(output, *, error_code)`, `find_project`, the project.godot key helpers, and `render_export_presets` behave as in design.md.
- `tests/godot_fakes.py` provides `FakeGodotRunner(responses, *, import_errors=False)`. It records each argv and returns scripted `NMG_RESULT` stdout per probe script name.
- Evidence: `uv run pytest tests/unit/godot -q`.

### T002: Export `.glb` variants, clips, terrain chunks, and per-variant `nmg-asset.json` from Blender

**File(s)**: `plugins/nmg-game-dev-blender-addon/variants_core/export.py`, `plugins/nmg-game-dev-blender-addon/variants_core/sidecars.py`, `plugins/nmg-game-dev-blender-addon/finalize_core/`, `plugins/nmg-game-dev-blender-addon/terrain_core/export.py`, `plugins/nmg-game-dev-blender-addon/contract_core/`, `tests/blender/`
**Type**: Modify
**Depends**: none
**Acceptance**:
- AC1: export writes `<Variant>/<Name>.glb` plus the `T_*` PNG set, and writes `nmg-asset.json` with `meshes` (names, tris, material slots, Godot-space bounds) in both Desktop and Mobile. No `.fbx` or `_LOD<n>` file is written.
- AC3: `export_anims` writes `Animations/A_<Name>_<Clip>.glb`, one per clip; per-clip hashing is unchanged.
- AC4: terrain export writes `<Name>_Chunk_<r>_<c>.glb` chunks of 63 quads and `T_<Name>_Splat.png`. More than 4 layers raises `variants.terrain_layers_unsupported`.
- The reimport check reads the `.glb`.
- Evidence: `gate-blender-headless` (`scripts/run-blender-tests.sh`) passes.

### T003: Replace `import_ue` with `import_godot` in the finalize pipeline

**File(s)**: `src/nmg_game_dev/pipeline/`, `src/nmg_game_dev/godot/import_asset.py`, `src/nmg_game_dev/godot/gd/probe_asset.gd`, `src/nmg_game_dev/finalize/`, `mcp-servers/finalize/`, `tests/finalize_fakes.py`, `tests/unit/pipeline/`, `tests/unit/test_finalize_*.py`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- AC1, FR1: `STEP_ORDER` is `validate → bake → variants → export → export_anims → reimport → import_godot → import_anims`. `import_godot` runs `--import` once, probes each variant, writes the material-variant `.tres` files, and returns `res://` resource paths. `_STEP_VERSION == "5"`, and a test shows a cache populated under the old step name yields no hit for `import_godot`.
- AC2: tests drive `FakeGodotRunner` and an unresolvable binary to get `godot.not_found`, `import_godot.import_failed` (an `ERROR:` line or a non-zero exit) and `import_godot.mismatch` (a tris, name, slot or bounds difference). Each carries a remediation, and the runner records that `import_anims` never ran.
- `pie_mode`, `pie_wait_seconds`, the PIE preflight, and the Unreal retry settings are gone from the request, `tools.json`, and the CLI.
- Evidence: `uv run pytest tests/unit/pipeline tests/unit/test_finalize_cli.py tests/unit/test_finalize_mcp.py tests/unit/test_finalize_mcp_tools.py -q`; `gate-mcp-schema`.

### T004: Import animation clips as Godot animation libraries

**File(s)**: `src/nmg_game_dev/pipeline/anims.py`, `src/nmg_game_dev/godot/anims.py`, `src/nmg_game_dev/godot/gd/probe_anims.gd`, `tests/unit/pipeline/test_anims.py`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- AC3, FR3: each changed clip gets an `.import` with `importer="animation_library"` before import, and the probe verifies its frame count. A rerun with one changed clip hash re-exports and re-imports only that clip (the recorded runner calls name one clip).
- `import_anims.clip_mismatch`, `finalize.skeleton_mismatch` and `finalize.skeleton_not_found` are covered.
- Evidence: `uv run pytest tests/unit/pipeline/test_anims.py -q`.

### T005: Finalize terrain into a chunked scene with heightmap collision

**File(s)**: `src/nmg_game_dev/godot/terrain.py`, `src/nmg_game_dev/godot/gd/probe_terrain.gd`, `src/nmg_game_dev/pipeline/engine.py`, `tests/unit/pipeline/test_terrain_routing.py`, `tests/unit/godot/test_terrain.py`
**Type**: Create
**Depends**: T003
**Acceptance**:
- AC4, FR4: the generated `<Name>.tscn` instances every chunk `.glb`, has a `StaticBody3D`/`CollisionShape3D` `HeightMapShape3D` whose `map_data` decodes from the same 16-bit heightfield, and uses the add-on terrain shader.
- A probe height range off by more than 0.05 m raises `import_godot.terrain_height_mismatch`.
- Evidence: `uv run pytest tests/unit/godot/test_terrain.py tests/unit/pipeline/test_terrain_routing.py -q`.

### T006: Import audio as `AudioStreamWAV`

**File(s)**: `src/nmg_game_dev/audio/`, `src/nmg_game_dev/godot/gd/probe_audio.gd`, `tests/unit/audio/`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- AC5, FR5: the WAV is stored under `SourceArt/Audio/<Kind>/` and copied to `game/assets/Audio/<Name>.wav`. Its `.import` sets `edit/loop_mode=2` for a looping music file and `1` otherwise. The probe confirms `AudioStreamWAV`. `godot.not_found` returns `imported_to_godot: false` with a warning.
- `audio/unreal_import.py` is deleted.
- Evidence: `uv run pytest tests/unit/audio -q`.

### T007: List material variants from finalize-written files

**File(s)**: `src/nmg_game_dev/finalize/mcp_tools.py`, `src/nmg_game_dev/godot/material_variants.py`, `mcp-servers/finalize/tools.json`, `tests/unit/test_material_variants_host.py`
**Type**: Modify
**Depends**: T003
**Acceptance**:
- AC6, FR6: given a finalized fixture tree, `list_material_variants` returns `[{name, material, desktop, mobile}]` from `nmg-variants.json` and the `.tres` files. A `FakeGodotRunner` passed in records zero calls.
- A missing sidecar raises `finalize.material_variants_failed`.
- Evidence: `uv run pytest tests/unit/test_material_variants_host.py -q`.

### T008: Scaffold design entries as Godot files

**File(s)**: `src/nmg_game_dev/design/`, `tests/unit/design/`
**Type**: Modify
**Depends**: T001
**Acceptance**:
- AC7, FR7: regions, missions and systems are written to the paths and contents in design.md, with a terrain-scene instance when the finalized `.tscn` exists and a ground plane otherwise.
- An existing file is left byte-identical and reported `unchanged`. An unknown terrain gives a `design.unknown_reference` line, and an entry write failure gives `design.scaffold_failed`; both continue.
- `statuses` filtering works.
- Evidence: `uv run pytest tests/unit/design -q`.

### T009: Add the Godot runtime add-on, fixture project, and `gate-godot-headless`

**File(s)**: `plugins/nmg-game-dev-godot-addon/`, `tests/godot/`, `scripts/run-godot-tests.sh`, `steering/manifest.json`, `.gitignore`, `tests/unit/test_run_godot_tests.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- AC8, FR8: `NmgAssets.resolve_variant_path` and `NmgMissionDefinition` behave as in design.md. `tests/run_tests.gd` covers Desktop, Mobile (via `resolve_variant_path_for`), and each malformed case. It prints `N passed, M failed` and exits 1 on any failure.
- FR14, AC14: `steering/manifest.json` registers `gate-godot-headless` as in design.md. `scripts/run-godot-tests.sh` resolves `GODOT_BIN`, then PATH, then downloads into the git-ignored `.cache/godot/<ver>/`, and runs the fixture import, the add-on tests, and the fixture probe comparison.
- `tests/unit/test_run_godot_tests.py` drives the script with a fake `godot` on PATH and a fake `curl`/`unzip`, covering resolution order and failure exit codes.
- Evidence: `gate-godot-headless`; `gate-shellcheck`; `uv run pytest tests/unit/test_run_godot_tests.py -q`.

### T010: Rework `/ship` around Godot export presets

**File(s)**: `src/nmg_game_dev/ship/`, `src/nmg_game_dev/quality/mobile_budgets.py`, `scripts/audit-mobile-budgets.py`, `scripts/ship-smoke.sh`, `skills/ship/SKILL.md`, `tests/ship_fakes.py`, `tests/ship_shim.py`, `tests/unit/ship/`, `tests/unit/quality/`
**Type**: Modify
**Depends**: T001, T009
**Acceptance**:
- AC9, FR9: with `FakeGodotRunner`, `run_ship` runs `--check-only` per `.gd`, then `run_tests.gd` when present, then the budget gate for ios, android and web, then `--export-release <preset>`. The macOS sign and notarize scripts run on the `.app`. Every platform produces its artifact under `release/<platform>/`, and `RELEASE-NOTES.md` lists each with SHA-256.
- A web `index.pck` over 38 MiB prints `ship.web_pack_large`. Windows needs no `WINDOWS_BUILD_*`. Android keystore values reach only the child environment. The iOS preset file is restored byte-identical.
- `--dry-run` prints `DRY-RUN:` lines and runs no Godot.
- The mobile budget gate reads `game/assets/**/Mobile/nmg-asset.json`.
- Evidence: `uv run pytest tests/unit/ship tests/unit/quality -q`; `gate-ship-smoke`.

### T011: Rework `/onboard-consumer` for a Godot consumer

**File(s)**: `src/nmg_game_dev/onboard/`, `templates/consumer/`, `skills/onboard-consumer/`, `tests/onboard_fakes.py`, `tests/unit/onboard/`
**Type**: Modify
**Depends**: T001, T009
**Acceptance**:
- AC10, FR10: on an empty consumer, onboarding creates `game/project.godot` with the Compatibility renderer for mobile and web, the add-on, and `game/export_presets.cfg`, whose desktop presets exclude `assets/*/Mobile/*` and whose mobile and web presets exclude `assets/*/Desktop/*`.
- It writes only the Blender SessionStart hook and no engine plugins or engine launcher, and reports `godot_binary` found or missing.
- A second run leaves every file byte-identical and reports a changed preset or renderer key as `drift`.
- Evidence: `uv run pytest tests/unit/onboard -q`; `plugin.validate`; `plugin.session-smoke`.

### T012: Add `/convert-to-godot`

**File(s)**: `src/nmg_game_dev/convert/`, `skills/convert-to-godot/SKILL.md`, `docs/skills/convert-to-godot.md`, `tests/convert_fakes.py`, `tests/unit/convert/`
**Type**: Create
**Depends**: T003, T006, T008, T011
**Acceptance**:
- AC11, FR11: on a fixture consumer (a project file, two finalized assets, `SourceArt` sources, a Music and an SFX WAV, a scaffolded backlog, and an Unreal hook in a clean git repo), conversion does the following with injected fakes:
  - onboards and finalizes each asset from its case-insensitive `SourceArt/**/<Name>.blend` into `game/assets`;
  - imports each WAV (music looping);
  - re-scaffolds only `scaffolded` entries;
  - removes the engine hook and `UE_*` env keys;
  - writes `godot-conversion-report.md` with converted and manual-port items (`Source/**`, `.umap`, and non-finalized `.uasset`);
  - removes the listed paths through `git rm`.
- AC12: one injected failure means no deletion, a report row with code and remediation, exit 1, and a rerun that converts only the failed item.
- AC13: a dirty tree gives `convert.dirty_worktree`, and a missing project file gives `convert.not_unreal`, both with the tree snapshot unchanged. `--dry-run` prints `PLAN` lines and the snapshot is unchanged.
- `convert.source_missing` and `convert.source_ambiguous` are covered.
- Evidence: `uv run pytest tests/unit/convert -q`; `plugin.validate`.

### T013: Rewrite contracts, skills, docs, and steering for Godot

**File(s)**: `docs/`, `skills/finalize-asset/SKILL.md`, `skills/design/SKILL.md`, `skills/model-asset/`, `steering/snippets/project-product.md`, `steering/snippets/project-tech.md`, `steering/snippets/project-structure.md`, `README.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `templates/consumer/README.md`, `.claude-plugin/plugin.json`, `pyproject.toml`, `mcp-servers/finalize/pyproject.toml`, `src/nmg_game_dev/__init__.py`, `plugins/nmg-game-dev-blender-addon/utils/master_material.py`
**Type**: Modify
**Depends**: T003, T004, T005, T006, T007, T008, T009, T010, T011, T012
**Acceptance**:
- FR12: `docs/asset-contract.md` specifies `.glb` export at 1 unit = 1 m with the origin at the base centre, the PNG set beside it, Godot import-time LOD generation within the mobile polycount budget, `game/assets/<Category>/<Name>/{Desktop,Mobile}/`, terrain chunks and `.tscn`, and an error-code table listing every `import_godot.*` code.
- Skills, onboarding docs, `docs/mcp/finalize.md`, `docs/design-contract.md`, the README, and the steering snippets describe the Godot flow. That covers the gate table with `gate-godot-headless` and without `gate-ue-compile`, plus the versioning row for `plugin.cfg`.
- The onboarding docs link `docs/skills/convert-to-godot.md`.
- `tests/unit/test_steering_guards.py`, `test_finalize_docs.py`, `test_geometry_rule_docs.py`, `test_rigging_docs.py` and `test_scaffold_guards.py` assert the new content, including `plugin.cfg` in the version triangulation.
- Evidence: `uv run pytest tests/unit -q`; `plugin.validate`.

### T014: Remove Unreal from the repository

**File(s)**: `plugins/nmg-game-dev-ue-plugin/`, `src/nmg_game_dev/unreal/`, `src/nmg_game_dev/pipeline/clients/unreal_mcp.py`, `fixtures/`, `tests/ue-automation/`, `steering/extensions/ue-compile.mjs`, `steering/manifest.json`, `.mcp.json`, `.gitignore`, `scripts/`, `docs/mcp/unreal.md`, `tests/_scaffold_contract.py`, `tests/unit/test_toolchain_guards.py`, `tests/unit/test_scaffold_guards.py`, `tests/e2e/`, `tests/`
**Type**: Delete
**Depends**: T013
**Acceptance**:
- FR13, AC14: every path in the design.md "Removed" list is deleted. `.mcp.json` has no `unreal` server. `steering/manifest.json` has no `gate-ue-compile` validation and no `project.ue-compile` extension, and `gate-ship-smoke` uses the include list from design.md.
- The guard and e2e tests that referenced Unreal are rewritten for Godot or deleted with the feature they covered.
- Evidence: `repository.tests`, `repository.lint`, `repository.format`, `repository.types`; `plugin.validate`; `plugin.session-smoke`.

### T015: Guard the repository against Unreal references

**File(s)**: `tests/unit/test_no_unreal_references.py`
**Type**: Create
**Depends**: T014
**Acceptance**:
- AC14: the test lists `git ls-files -z` and asserts that no path or text outside `specs/`, `CHANGELOG.md` and `EXEMPT` matches the patterns in design.md.
- A second test asserts that `EXEMPT` equals exactly `src/nmg_game_dev/convert/`, `skills/convert-to-godot/`, `docs/skills/convert-to-godot.md`, `tests/unit/convert/`, `tests/convert_fakes.py`, `tests/bdd/features/convert_to_godot.feature`, `tests/bdd/test_convert_to_godot_bdd.py`, and `tests/unit/test_no_unreal_references.py`, and that each exists.
- A third test checks the matcher on synthetic text: `UE` matches as a whole word, `queue` does not, and `Unreal` matches in any case.
- Evidence: `uv run pytest tests/unit/test_no_unreal_references.py -q`.

### T016: BDD scenarios for the Godot engine and conversion

**File(s)**: `tests/bdd/features/godot_engine.feature`, `tests/bdd/test_godot_engine_bdd.py`, `tests/bdd/features/convert_to_godot.feature`, `tests/bdd/test_convert_to_godot_bdd.py`
**Type**: Create
**Depends**: T012, T015
**Acceptance**:
- `godot_engine.feature` binds SCN001–SCN010 and SCN014 (AC1–AC10, AC14). `convert_to_godot.feature` binds SCN011–SCN013 (AC11–AC13).
- The bindings use `FakeGodotRunner`, `FakeStepRunner`, and the convert fakes. AC14's scenario calls the guard from T015.
- Evidence: `uv run pytest tests/bdd -q`.

### T017: Record the breaking change

**File(s)**: `CHANGELOG.md`
**Type**: Modify
**Depends**: T014
**Acceptance**:
- `## [Unreleased]` gains a `**BREAKING CHANGE:**` bullet saying the engine target is now Godot 4 and that `/convert-to-godot` migrates existing consumers. It also gains bullets for Godot finalize, ship, onboarding, and the runtime add-on, plus a `### Migration Notes` sub-section.
- Every bullet ends with `(#249)`.
- Evidence: `uv run pytest tests/unit/test_changelog_structure.py -q`.

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #249 | 2026-11-18 | Initial feature tasks |
