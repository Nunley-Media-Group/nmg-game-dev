# Tasks: Consumer onboarding — onboard-consumer skill, asset contract install, and onboarding docs

**Issue**: #7
**Date**: 2026-10-30
**Status**: Approved
**Author**: Rich Nunley

## Implementation Tasks

### T001: Onboard package foundations

**File(s)**: `src/nmg_game_dev/onboard/__init__.py`, `src/nmg_game_dev/onboard/errors.py`, `src/nmg_game_dev/onboard/paths.py`, `src/nmg_game_dev/onboard/files.py`
**Type**: Create
**Depends**: none
**Acceptance**:
- `OnboardError`, `StepResult`, `framework_root` (from `CLAUDE_PLUGIN_ROOT` or the package location), and the `fixtures` / `.mcp.json` exclusion guard behave per design (FR1, FR8, AC7)
- `sync_file` / `sync_tree` report installed, unchanged, drift, or refreshed and keep the executable bit (FR9)

### T002: Settings and agent-instruction merges

**File(s)**: `src/nmg_game_dev/onboard/settings.py`, `src/nmg_game_dev/onboard/instructions.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- SessionStart hooks from `templates/consumer/.claude/settings.json` are merged without duplicates, and unrelated keys are preserved (FR3, AC1, AC8)
- `.claude/settings.local.json` env merge sets `TEXTURE_GEN_MODELS_DIR` and `HF_HOME` (FR7, AC4)
- The marked `CLAUDE.md` / `AGENTS.md` block is added once and replaced in place (FR4, AC1, AC8)

### T003: Unreal setup

**File(s)**: `src/nmg_game_dev/onboard/unreal.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- `.uproject` merge enables `ModelContextProtocol`, `EditorToolset`, `VibeUE`, and `nmg-game-dev`, keeping other entries and fields (FR5, AC2)
- The ini merge sets `bAutoStartServer=True` and adds `ServerPortNumber=8000` only when absent (FR5, AC2)
- VibeUE is cloned at `v5.0-ue5.8`, checked against commit `bc7bc45c1e2025123778560f45c15d1f8e1be41d`, and refreshed per design (FR5, FR9, AC2, AC9)

### T004: Blender add-on link

**File(s)**: `src/nmg_game_dev/onboard/blender.py`
**Type**: Create
**Depends**: T001
**Acceptance**:
- Creates `<BLENDER_EXTENSIONS_DIR>/nmg_game_dev_blender_addon` → `plugins/nmg-game-dev-blender-addon`; a correct existing link is unchanged; a wrong target is drift and is replaced only with `--refresh` (FR6, AC3, AC8, AC9)

### T005: Texture models and volume listing

**File(s)**: `src/nmg_game_dev/onboard/textures.py`, `src/nmg_game_dev/onboard/volumes.py`
**Type**: Create
**Depends**: T001, T010
**Acceptance**:
- `TEXTURE_MODELS` is derived from `nmg_game_dev.texture.registry.REGISTRY`; `install_command(id, dir)` builds the exact `mflux-save` command (FR7, FR12, AC4)
- Missing models are installed sequentially with the exact `mflux-save` commands and `HF_HOME`; `uv tool install mflux==0.24.0` runs only when `mflux-save` is absent; installed models are skipped (FR7, AC4, AC8)
- The platform and 60 GiB free-space checks raise `onboard.unsupported_platform` / `onboard.insufficient_disk` (AC5)
- `list_volumes` returns mount, free bytes, and `fits_models` (AC6)

### T006: Onboard runner and CLI

**File(s)**: `src/nmg_game_dev/onboard/runner.py`, `src/nmg_game_dev/onboard/__main__.py`
**Type**: Create
**Depends**: T002, T003, T004, T005
**Acceptance**:
- Preflight (uproject, models dir, platform, disk, framework sources) runs before any consumer write; failures exit 1 with `ERROR [onboard.*]` and a remediation (FR2, AC5)
- Steps run in the design order, copying the start scripts, asset contract, and UE plugin, and the report lists every step with status and remediation; drift exits 0 (FR1, FR9, AC1, AC2, AC8, AC9)
- `volumes` prints the JSON list (AC6)

### T007: Skill, references, docs, and links

**File(s)**: `skills/onboard-consumer/SKILL.md`, `skills/onboard-consumer/references/install-steps.md`, `docs/onboarding/index.md`, `docs/onboarding/first-asset.md`, `docs/onboarding/first-ship.md`, `docs/onboarding/upgrading.md`, `docs/onboarding/texture-models.md`, `CLAUDE.md`, `README.md`, `templates/consumer/README.md`, `CHANGELOG.md`
**Type**: Create | Modify
**Depends**: T006, T013
**Acceptance**:
- `SKILL.md` frontmatter has `name: onboard-consumer`, a one-line `description`, `required_mcp: []`, `required_env`, and `unattended_safe: true`; its flow covers the disk question, the autopilot path, `install`, and `--refresh` (FR10, AC6, AC11)
- `references/install-steps.md` documents every consumer write from the design table
- The docs have the AC10 content, including `texture-models.md`; `CLAUDE.md`, `README.md`, and `templates/consumer/README.md` link to `docs/onboarding/index.md` / the skill (FR10, AC10)
- `CHANGELOG.md` `[Unreleased]` gets a bullet for consumer onboarding and one for local texture generation, each ending with `(#7)`
- The registered `plugin.validate` validation passes, and `markdownlint docs/ steering/ *.md` passes

### T008: Unit tests for onboarding

**File(s)**: `tests/unit/onboard/__init__.py`, `tests/unit/onboard/conftest.py`, `tests/unit/onboard/test_settings.py`, `tests/unit/onboard/test_instructions.py`, `tests/unit/onboard/test_unreal.py`, `tests/unit/onboard/test_blender.py`, `tests/unit/onboard/test_textures.py`, `tests/unit/onboard/test_runner.py`, `tests/unit/onboard/test_docs_and_skill.py`
**Type**: Create
**Depends**: T006, T007
**Acceptance**:
- `conftest.py` builds a fixture consumer (`Game.uproject`, unrelated settings, `CLAUDE.md`) in a temp dir. It also puts stub `git`, `mflux-save`, and `uv` executables on `PATH` that log argv; the stub `git clone` writes `VibeUE.uplugin`, and `rev-parse HEAD` echoes a configurable sha. Host facts and `disk_usage` are injected
- Covers AC1–AC9: files and hooks installed, exclusions, no `_API_KEY` env, UE plugin/clone/uproject/ini, Blender link, model commands (ids and order from the registry) and skips, each prerequisite failure leaving the consumer unchanged, two framework roots giving identical trees, the second run being a no-op, and drift reported then repaired by `--refresh` with `nmg-budgets.json` untouched
- `test_docs_and_skill.py` covers AC10 and AC11 (required files including `texture-models.md`, links, frontmatter)
- Passes under the `repository.tests`, `repository.lint`, and `repository.types` validations

### T009: BDD acceptance scenarios for onboarding and texture generation

**File(s)**: `tests/bdd/features/onboard_consumer.feature`, `tests/bdd/test_onboard_bdd.py`, `tests/bdd/features/texture_generation.feature`, `tests/bdd/test_texture_bdd.py`
**Type**: Create
**Depends**: T008, T015
**Acceptance**:
- `onboard_consumer.feature` contains `@SCN001`–`@SCN011` and `texture_generation.feature` contains `@SCN012`–`@SCN020` from this spec's `feature.gherkin`, each bound with `@scenario` and implemented with the T008 and T015 fixtures
- Passes under the `repository.tests` validation

### T010: Texture registry, errors, paths, and hardware checks

**File(s)**: `src/nmg_game_dev/texture/__init__.py`, `src/nmg_game_dev/texture/errors.py`, `src/nmg_game_dev/texture/registry.py`, `src/nmg_game_dev/texture/paths.py`, `src/nmg_game_dev/texture/hardware.py`, `pyproject.toml`, `uv.lock`
**Type**: Create | Modify
**Depends**: none
**Acceptance**:
- `REGISTRY` is a read-only mapping with exactly the two `BackendSpec`s from AC12 (repo, revision, license, quantization 4, steps 9 / 4, peak 14.6 / 12.9 GB) (FR12, AC12)
- `resolve` raises `texture.unknown_backend` and `texture.model_not_allowed` with the allowed backends and repos in the remediation (AC13)
- `availability` / `require_available` implement `not_installed` (remediation names `/onboard-consumer`, the `install_command` text, and the expected path), `unsupported_platform`, and `insufficient_memory` with `TEXTURE_GEN_BLENDER_RESERVE_GB` (default 8), using injected `HardwareFacts` (FR13, AC14, AC15)
- `output_root` resolves `NMG_GAME_DEV_TEXTURE_DIR`, else `<CLAUDE_PROJECT_DIR or cwd>/SourceArt/Textures/Generated` (AC20)
- `pyproject.toml` adds exact-pinned `numpy` and `pillow` to core and the `texture-ai` extra (`mflux==0.24.0`, exact `hf_transfer`); `uv.lock` is updated; nothing outside `texture/worker.py` imports mflux (FR17)

### T011: Seamless post-process and derived maps

**File(s)**: `src/nmg_game_dev/texture/seamless.py`, `src/nmg_game_dev/texture/maps.py`, `src/nmg_game_dev/texture/sheet.py`
**Type**: Create
**Depends**: T010
**Acceptance**:
- `make_seamless` implements the design's per-axis cross-fade and keeps dimensions; `seam_mad` / `interior_mad` support the AC18 threshold (FR15, AC18)
- `derive` writes `_N` (OpenGL), `_R`, `_M`, and optional `_AO` at the albedo resolution, using wrap-around operations; presets and explicit values both work; an unknown preset raises `texture.invalid_request` (FR15, AC19)
- `compare` writes a labeled side-by-side sheet (AC20)

### T012: Worker process and sequential batch runner

**File(s)**: `src/nmg_game_dev/texture/worker.py`, `src/nmg_game_dev/texture/batch.py`
**Type**: Create
**Depends**: T010
**Acceptance**:
- The worker loads one backend once with the design's mflux classes and `compute_precision=mx.float16`, generates every request in its batch file, writes PNGs, and prints one JSON line per image (FR12, FR14, AC16)
- `run_backend_batches` runs one worker per backend, waits for each to exit before the next starts, and raises `texture.worker_failed` on a non-zero exit; `spawn` is injectable (FR14, AC16, AC17)

### T013: Generate entry point, jobs, and CLI

**File(s)**: `src/nmg_game_dev/texture/generate.py`, `src/nmg_game_dev/texture/jobs.py`, `src/nmg_game_dev/texture/__main__.py`
**Type**: Create
**Depends**: T011, T012
**Acceptance**:
- `run` validates the request (`texture.invalid_request`), appends the style suffix, resolves and checks backends (expanding `both` to available backends in registry order), runs the batches, applies `make_seamless` to every PNG, writes derived maps, the comparison sheet for `both`, and `textures.json` under `<output_root>/<name>/` (FR15, FR16, AC17–AC20)
- `jobs.start` / `jobs.status` implement the design's job directory, atomic `status.json`, PID lock (`texture.job_running`, stale-lock replacement), and detached `run-job`; an unknown id raises `texture.job_not_found` (FR14, FR16, AC17, AC20)
- `python -m nmg_game_dev.texture generate|status|run-job` behave per design, printing JSON and exiting 1 with `ERROR [texture.*]` / `Remediation:` on failure (AC20)

### T014: texture-gen MCP server, MCP config, and tool validator

**File(s)**: `mcp-servers/texture-gen/pyproject.toml`, `mcp-servers/texture-gen/tools.json`, `mcp-servers/texture-gen/src/texture_gen_mcp/__init__.py`, `mcp-servers/texture-gen/src/texture_gen_mcp/server.py`, `.mcp.json`, `scripts/validate-mcp-tools.py`, `tests/_scaffold_contract.py`, `tests/bdd/features/scaffold-plugin-repo-session-start-hooks.feature`, `tests/bdd/steps/test_scaffold.py`
**Type**: Create | Modify
**Depends**: T013
**Acceptance**:
- The FastMCP server exposes `generate_textures`, `get_texture_job`, and `texture_backends` over `generate`/`jobs`/`hardware`, returns structured `{"error": {code, message, remediation}}` failures, and logs to stderr only (FR16, AC20)
- `.mcp.json` gains the `texture-gen` entry from the design; the other entries are unchanged; the file contains no `latest`, `main`, or `HEAD` substring; `REQUIRED_SERVERS` includes `texture-gen`, and the scaffold AC8 step names every required server (FR16)
- `scripts/validate-mcp-tools.py` exits 0 for the server and 1 when `tools.json` and the registered tools differ (FR18)

### T015: Texture unit tests and the opt-in real-model test

**File(s)**: `tests/unit/texture/__init__.py`, `tests/unit/texture/conftest.py`, `tests/unit/texture/test_registry.py`, `tests/unit/texture/test_hardware.py`, `tests/unit/texture/test_seamless.py`, `tests/unit/texture/test_maps.py`, `tests/unit/texture/test_batch.py`, `tests/unit/texture/test_generate.py`, `tests/unit/texture/test_jobs.py`, `tests/unit/texture/test_cli.py`, `tests/unit/texture/test_mcp_server.py`, `tests/unit/test_validate_mcp_tools.py`, `tests/e2e/test_texture_models_e2e.py`
**Type**: Create
**Depends**: T014
**Acceptance**:
- `conftest.py` provides a fake worker script that records start/exit timestamps and loads per batch and writes synthetic PNGs, a fake `BackendSpec` registry, injected `HardwareFacts`, and a temp `TEXTURE_GEN_MODELS_DIR` with or without `<id>-q4` dirs
- Covers:
  - AC12 (exactly two pinned entries, read-only mapping, generation with a fake registry)
  - AC13 (FLUX.2-klein-9B, FLUX.1-dev, and an unknown id rejected)
  - AC14 (`not_installed` and remediation text)
  - AC15 (non-Apple, low RAM, explicit request errors, `both` skipping)
  - AC16 (one load per batch, one PNG per request)
  - AC17 (non-overlapping timestamps, `texture.job_running`)
  - AC18 (seam threshold on the synthetic image)
  - AC19 (map files, resolution, and seams)
  - AC20 (CLI JSON, job states through the MCP tools, the `SourceArt/Textures/Generated/<name>/` default and override, manifest, and comparison sheet)
  - FR18 (the validator pass and fail cases)
- `test_texture_models_e2e.py` generates one 256 px texture per backend with the real models and is skipped unless both weights dirs exist and the `texture-ai` extra is importable (FR19)
- Passes under the `repository.tests`, `repository.lint`, and `repository.types` validations, and `scripts/validate-mcp-tools.py`

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #7 | 2026-10-29 | Initial feature tasks |
| #7 | 2026-10-30 | Spec revised before delivery |
