# Requirements: Consumer onboarding — onboard-consumer skill, asset contract install, and onboarding docs

**Issue**: #7
**Date**: 2026-10-30
**Status**: Approved
**Author**: Rich Nunley

## User Story

**As an** NMG game developer starting or upgrading a consumer game project (e.g., ghost1)
**I want** one idempotent `onboard-consumer` skill, a short set of onboarding docs, and local texture generation the agent can call while authoring
**So that** my project gets the start scripts, SessionStart hooks, Unreal and Blender plugins, local texture models, and the asset contract in one run, re-runs tell me what has drifted, and the agent can generate seamless material textures locally

## Background

nmg-game-dev is a Claude Code plugin; its Blender and Unreal MCP servers ship in the plugin's bundled `.mcp.json`, so consumers need no MCP config of their own. The source artifacts onboarding places already exist:

- `scripts/start-blender-mcp.sh` and `scripts/start-unreal-mcp.sh`
- `templates/consumer/.claude/settings.json` (SessionStart hooks)
- `plugins/nmg-game-dev-ue-plugin/` and `plugins/nmg-game-dev-blender-addon/`
- `docs/asset-contract.md`

`skills/` has no onboarding skill and `docs/onboarding/` is empty.

Unreal setup is two layers on UE 5.8. Epic's Unreal MCP plugin (`ModelContextProtocol`) and `EditorToolset` provide the native MCP server, which auto-starts via `UModelContextProtocolSettings.bAutoStartServer`. VibeUE (`kevinpbuckley/VibeUE`, tag `v5.0-ue5.8`) registers its tools on that server.

Local texture generation uses exactly two mflux models saved with 4-bit quantization: `z-image-turbo` (`Tongyi-MAI/Z-Image-Turbo`) and `flux2-klein-4b` (`black-forest-labs/FLUX.2-klein-4B`). Onboarding installs both on a disk the developer chooses. The texture package generates seamless albedo textures with them, one model process at a time, and derives normal, roughness, metallic, and AO maps.

Measured on an M1 Max (32 GB, mflux 0.24.0, saved 4-bit weights, `compute_precision=mx.float16`), each 1024 px texture took:

- Z-Image Turbo: ~97 s at 9 steps, with 14.6 GB peak memory;
- FLUX.2 klein 4B: ~31 s at 4 steps, with 12.9 GB peak memory.

Only one model fits beside Blender. Loading takes 20–30 s, so prompts are batched per load. Neither model tiles natively, so a per-axis cross-fade with a half-rolled copy makes the output seamless.

## Acceptance Criteria

### AC1: Fresh onboarding installs the framework files

**Given** a consumer directory with one `.uproject`, an existing `.claude/settings.json` holding unrelated settings, and an existing `CLAUDE.md`
**When** `python -m nmg_game_dev.onboard install --consumer <dir> --models-dir <dir>` runs
**Then** `scripts/start-blender-mcp.sh` and `scripts/start-unreal-mcp.sh` are copied into `<consumer>/scripts/` and are executable
**And** the template's SessionStart hook group is merged into `.claude/settings.json`, and the unrelated settings are unchanged
**And** `docs/asset-contract.md` is installed at `<consumer>/docs/nmg-game-dev/asset-contract.md`, and `CLAUDE.md` (and `AGENTS.md` when present) gains one marked block that references it
**And** no `.mcp.json` is written, nothing from `fixtures/` (including `dogfood.uproject`) is written, and no settings file gains an environment variable whose name ends in `_API_KEY`

### AC2: Unreal plugins are installed and enabled

**Given** the same consumer and a `git` executable on `PATH`
**When** onboarding runs
**Then** the nmg-game-dev UE plugin is copied to `<consumer>/Plugins/nmg-game-dev/` (without `Binaries/` or `Intermediate/`)
**And** VibeUE is cloned with `git clone --depth 1 --branch v5.0-ue5.8 https://github.com/kevinpbuckley/VibeUE.git <consumer>/Plugins/VibeUE`
**And** the `.uproject` `Plugins` list has `ModelContextProtocol`, `EditorToolset`, `VibeUE`, and `nmg-game-dev` enabled, and its other entries and fields are kept
**And** `Config/DefaultEditorPerProjectUserSettings.ini` has `bAutoStartServer=True` under `[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]`, and `ServerPortNumber=8000` unless a port is already set there

### AC3: The Blender add-on is linked into Blender's extensions

**Given** `BLENDER_EXTENSIONS_DIR` points at a Blender `extensions/user_default` directory
**When** onboarding runs
**Then** `<BLENDER_EXTENSIONS_DIR>/nmg_game_dev_blender_addon` is a symlink to the framework's `plugins/nmg-game-dev-blender-addon`

### AC4: Local texture models are installed on the chosen disk

**Given** `--models-dir <dir>` on a volume with at least 60 GiB free, on an Apple Silicon Mac
**When** onboarding runs
**Then** `mflux-save --model z-image-turbo --quantize 4 --path <dir>/z-image-turbo-q4` and `mflux-save --model flux2-klein-4b --quantize 4 --path <dir>/flux2-klein-4b-q4` run one after the other, with `HF_HOME=<dir>/hf-cache`
**And** `mflux==0.24.0` is installed with `uv tool install` first if `mflux-save` is not on `PATH`
**And** `.claude/settings.local.json` `env` has `TEXTURE_GEN_MODELS_DIR=<dir>` and `HF_HOME=<dir>/hf-cache`
**And** a model whose `<dir>/<id>-q4` directory already exists is not saved again
**And** the model ids and order come from the texture registry (AC12), not a second list

### AC5: Texture prerequisites fail before anything changes

**Given** no `--models-dir` and no `TEXTURE_GEN_MODELS_DIR`, or a models dir whose volume has less than 60 GiB free while a model is missing, or a host that is not Apple Silicon macOS
**When** onboarding runs
**Then** it exits 1 with code `onboard.models_dir_missing`, `onboard.insufficient_disk`, or `onboard.unsupported_platform` and a remediation
**And** no file in the consumer directory has been created or changed

### AC6: The skill asks which disk to use

**Given** mounted volumes
**When** `python -m nmg_game_dev.onboard volumes` runs
**Then** it prints a JSON list of volumes with mount point, free bytes, and whether each has at least 60 GiB free
**And** `skills/onboard-consumer/SKILL.md` tells the agent to present the qualifying volumes with `AskUserQuestion` and to pass `<chosen volume>/nmg-texture-models` as `--models-dir`, using `TEXTURE_GEN_MODELS_DIR` without asking when `NMG_SDLC_AUTOPILOT=1`

### AC7: Install scope does not change the result

**Given** two copies of the framework root in different directories (one standing in for a user-scope plugin cache, one for a project-scope install)
**When** each onboards an identical fresh consumer
**Then** the two consumer trees are identical apart from the Blender symlink target, and no flag selects the scope
**And** the framework root comes from `CLAUDE_PLUGIN_ROOT` when set, otherwise from the package location

### AC8: Re-running is idempotent

**Given** a consumer that onboarding has already completed
**When** onboarding runs again without `--refresh`
**Then** there are no duplicate hook groups, `.uproject` plugin entries, ini keys, or `CLAUDE.md` blocks
**And** the Blender symlink is left intact, no `git clone` runs, and no `mflux-save` runs
**And** it exits 0

### AC9: Drift is reported and `--refresh` repairs it

**Given** an onboarded consumer whose `scripts/start-blender-mcp.sh`, installed asset contract, or `Plugins/nmg-game-dev/` differs from the framework, or whose `Plugins/VibeUE` HEAD is not the pinned commit, and which has a project-root `nmg-budgets.json`
**When** onboarding runs without `--refresh`
**Then** each differing item is listed as drift with the remediation `re-run with --refresh`, its content is unchanged, and the command exits 0
**And** `nmg-budgets.json` is neither reported nor changed
**When** onboarding runs with `--refresh`
**Then** the framework-owned copies are restored, VibeUE is checked out at the pinned commit, and `nmg-budgets.json` is unchanged

### AC10: Onboarding docs exist and are linked

**Given** the repository
**When** `docs/onboarding/` is read
**Then** `index.md` links to `first-asset.md`, `first-ship.md`, `upgrading.md`, and `texture-models.md`
**And** `first-asset.md` covers prompting for an asset, the review loop, what the contract enforces, texture sources (the two local models through `texture-gen`, or procedural Blender materials), budget overrides (`nmg-budgets.json`), and import into `Content/<Category>/<Name>/{Desktop,Mobile}/`
**And** `texture-models.md` covers the hardware requirements (Apple Silicon, RAM per model minus the Blender reserve), where weights live (`TEXTURE_GEN_MODELS_DIR`, `HF_HOME`), installing through onboarding, generating with the CLI and the `texture-gen` MCP tools, `both` comparison sheets, the output folder, and derived maps
**And** `first-ship.md` walks through the `ship` skill on a fixture project, `upgrading.md` covers reviewing breaking changes, re-registering the plugin, and re-running onboarding with `--refresh`, and `CLAUDE.md` and `README.md` link to `docs/onboarding/index.md`

### AC11: The onboard-consumer skill is the entry point

**Given** the plugin checkout
**When** `skills/onboard-consumer/SKILL.md` is loaded
**Then** its frontmatter has `name: onboard-consumer`, a one-line `description`, `required_mcp: []`, `required_env`, and `unattended_safe: true`
**And** its flow runs `python -m nmg_game_dev.onboard install`, and the detailed copy/link/merge rules are in `skills/onboard-consumer/references/install-steps.md`

### AC12: The texture registry holds exactly the two pinned models

**Given** `nmg_game_dev.texture.registry`
**When** its backends are listed
**Then** it contains exactly `z-image-turbo` and `flux2-klein-4b`, each exposing id, model repo, pinned revision, license identifier, quantization (4), default steps (9 / 4), peak-memory estimate (14.6 GB / 12.9 GB), an availability check, and a batch generate call:
- `z-image-turbo`: `Tongyi-MAI/Z-Image-Turbo` at `f332072aa78be7aecdf3ee76d5c247082da564a6`, `apache-2.0`
- `flux2-klein-4b`: `black-forest-labs/FLUX.2-klein-4B` at `e7b7dc27f91deacad38e78976d1f2b499d76a294`, `apache-2.0`

**And** batch generation, ordering, and post-processing take the registry as a parameter, so a test can run them with a fake backend, while the shipped registry offers no way to add a model

### AC13: Only the pinned models load

**Given** a backend configured with a model repo or path that is not one of the two pinned entries (for example `black-forest-labs/FLUX.2-klein-9B` or `black-forest-labs/FLUX.1-dev`), or a backend id that isn't in the registry
**When** generation is requested
**Then** it raises `TextureGenError` with code `texture.model_not_allowed` (or `texture.unknown_backend`) and a remediation listing the two allowed backends and repos

### AC14: Missing weights point at onboarding

**Given** a registry backend whose quantized weights directory `<TEXTURE_GEN_MODELS_DIR>/<id>-q4` is absent or empty, or `TEXTURE_GEN_MODELS_DIR` unset
**When** availability is checked or generation is requested
**Then** availability reports `not_installed`, and generation raises `TextureGenError` with code `texture.model_not_installed` and a remediation that names `/onboard-consumer`, the exact `mflux-save --model <id> --quantize 4 --path <dir>/<id>-q4` command, and the expected path

### AC15: The hardware check refuses unfit backends

**Given** injected hardware facts for a machine that is not Apple Silicon macOS, or whose total RAM minus the Blender reserve (`TEXTURE_GEN_BLENDER_RESERVE_GB`, default 8) is below a backend's peak-memory estimate
**When** availability is checked
**Then** that backend reports `unsupported_platform` or `insufficient_memory` and is excluded from `both`
**And** requesting it explicitly raises `TextureGenError` with code `texture.unsupported_platform` or `texture.insufficient_memory` and a remediation

### AC16: Each backend batch runs in one isolated process

**Given** a batch of texture requests (prompt, seed, resolution) for one backend
**When** the batch is generated
**Then** one child process loads the model once, generates every request, writes one PNG per request, and exits
**And** a test with a fake worker records exactly one load per batch and one PNG per request

### AC17: Models never run concurrently

**Given** batches for both backends in one call (`both`)
**When** generation runs
**Then** the second backend's process starts only after the first has exited, shown by the fake worker's recorded start and exit timestamps
**And** starting a job while another texture job's process is alive raises `TextureGenError` with code `texture.job_running` naming the running job

### AC18: Outputs tile seamlessly

**Given** a synthetic 256×256 non-tiling image (diagonal gradient plus seeded noise)
**When** the seamless post-process runs
**Then** the output has the input's dimensions, and on both axes the mean absolute difference across the wrap seam is at most 1.5× the mean absolute difference between adjacent interior pixels, where the input's seam difference exceeded 5× that interior difference
**And** every generated PNG passes through this post-process

### AC19: Derived PBR maps are seamless

**Given** a seamless albedo and a material preset (named, or explicit roughness and metallic values)
**When** derived maps are requested
**Then** it writes `<stem>_N.png` (OpenGL normal from luminance height), `<stem>_R.png` and `<stem>_M.png` (the preset values), and, when requested, `<stem>_AO.png` (from height), all at the albedo's resolution and each passing the AC18 seam check

### AC20: The agent can generate textures through the CLI and MCP

**Given** a consumer project with the models installed
**When** the agent runs `python -m nmg_game_dev.texture generate --prompt P [--backend z-image-turbo|flux2-klein-4b|both] [--seed N ...] [--resolution R] [--name S] [--maps PRESET]`, or calls the `texture-gen` MCP tool `generate_textures` with the same fields
**Then** the CLI waits and prints a JSON result. `generate_textures` returns a job id immediately, and `get_texture_job(job_id)` reports `queued`, `running` (with completed/total), `succeeded` (with PNG paths, derived-map paths, and per-image timings), or `failed` (with `code`, `message`, and `remediation`)
**And** outputs go to `<project>/SourceArt/Textures/Generated/<name>/`, where the project is `CLAUDE_PROJECT_DIR` or the working directory, and `NMG_GAME_DEV_TEXTURE_DIR` overrides the root. A `textures.json` manifest records the prompt, backend, seed, steps, timing, and paths
**And** with `both`, a side-by-side comparison sheet `<name>_compare.png` labels each image with backend, seed, and seconds

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | `python -m nmg_game_dev.onboard install --consumer DIR [--uproject P] [--models-dir D] [--refresh]` and `python -m nmg_game_dev.onboard volumes` | Must |
| FR2 | Preflight (uproject resolution, texture prerequisites, framework sources) completes before any consumer write | Must |
| FR3 | Copy the start scripts; merge the SessionStart hook template into `.claude/settings.json` idempotently, preserving other settings | Must |
| FR4 | Install the asset contract and a marked reference block in `CLAUDE.md` / `AGENTS.md`; never touch `nmg-budgets.json` | Must |
| FR5 | Copy the nmg-game-dev UE plugin, clone VibeUE at the pinned tag, enable the four plugins in the `.uproject`, and set MCP auto-start in `DefaultEditorPerProjectUserSettings.ini` | Must |
| FR6 | Symlink the Blender add-on into `BLENDER_EXTENSIONS_DIR` (default `~/Library/Application Support/Blender/5.2/extensions/user_default`) | Must |
| FR7 | Install both registry models with `mflux-save --quantize 4` on the chosen disk and record `TEXTURE_GEN_MODELS_DIR` / `HF_HOME` in `.claude/settings.local.json` | Must |
| FR8 | An explicit exclusion list keeps `fixtures/` and `.mcp.json` out of every consumer write | Must |
| FR9 | Detect drift of framework-owned copies and the VibeUE pin; `--refresh` restores them | Must |
| FR10 | `skills/onboard-consumer/SKILL.md` + `references/install-steps.md`; `docs/onboarding/{index,first-asset,first-ship,upgrading,texture-models}.md`; links from `CLAUDE.md`, `README.md`, and `templates/consumer/README.md` | Must |
| FR11 | Tests onboard a fixture consumer twice, covering exclusion, merge, drift, scope, and prerequisite cases with stub `git`, `mflux-save`, and `uv` | Must |
| FR12 | `nmg_game_dev.texture` registry of exactly the two pinned backends (`ZImage` at 9 steps; `Flux2Klein` with `ModelConfig.flux2_klein_4b()` at 4 steps; both `compute_precision=mx.float16`), with allowlist enforcement and `TextureGenError(code, message, remediation)` on every failure path | Must |
| FR13 | Availability per backend: weights present under `TEXTURE_GEN_MODELS_DIR`, Apple Silicon macOS, and RAM minus `TEXTURE_GEN_BLENDER_RESERVE_GB` ≥ peak estimate | Must |
| FR14 | One child process per backend batch (load once, generate all, exit), backends strictly sequential, one active texture job at a time | Must |
| FR15 | The seamless cross-fade post-process on every output; derived normal, roughness, metallic, and optional AO maps | Must |
| FR16 | `python -m nmg_game_dev.texture generate` and the `texture-gen` MCP server (`generate_textures`, `get_texture_job`) registered in `.mcp.json`; project-local output folder, manifest, and `both` comparison sheet; a configurable style suffix appended to every prompt | Must |
| FR17 | `mflux==0.24.0` and `hf_transfer` in an optional `texture-ai` extra; NumPy and Pillow as core dependencies; core install and CI do not need mflux | Must |
| FR18 | `scripts/validate-mcp-tools.py` checks every server under `mcp-servers/` against its `tools.json` | Must |
| FR19 | Unit tests use fake workers, injected hardware facts, and synthetic images; one opt-in real-model test runs only when both models are installed | Must |

## Out of Scope

- Changing the plugin's `.mcp.json` Blender or Unreal entries, or `scripts/start-unreal-mcp.sh` defaults (#68)
- Any texture model other than Z-Image Turbo and FLUX.2 klein 4B; non-Apple-Silicon runtimes
- Automatic candidate scoring or selection, vision-model judging, and image-to-PBR estimation models
- The pipeline `texture` stage, baking onto assets, and contract texture sets (#67); contract validation, variants, and finalize (#30, #33, #69)
- Recipe or per-asset-type skills; hosted generation services

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #7 | 2026-10-29 | Initial feature spec |
| #7 | 2026-10-30 | Spec revised before delivery |
